"""The agent loop (plan §2): one user message in, a stream of events out.

    persist user message  ->  build request (cached prefix + history + context-tagged user item)
    -> stream the model   ->  forward text deltas; on tool calls: authorise, run, allow-list,
                              sanitise, append results, go again (at most MAX_ITERATIONS)
    -> post-process text  ->  persist the assistant message (encrypted) + usage + cost
    -> "done"

Everything the model produced or consumed on a turn is stored on the assistant message as a
list of neutral items, so the next turn can replay the exact history (including a provider's
opaque reasoning items) without keeping any state at the provider (``store=false``).

Safe mode: any provider failure, an incomplete/refused/over-long answer, or hitting the
iteration cap ends the turn with a fixed, honest message and the support link. The model is
never asked to "recover" on its own, and nothing it said before the failure is presented as an
answer.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import AssistantConversation, AssistantMessage
from app.services import kb_service, settings_service
from app.services.assistant import guard, prompts
from app.services.assistant.context import AgentContext
from app.services.assistant.tools import REGISTRY, llm_tools
from app.services.assistant.tools.base import ToolSpec, call_tool, parse_args
from app.services.llm.types import (
    AssistantMessage as LLMAssistantMessage,
)
from app.services.llm.types import (
    Completed,
    Failed,
    LLMClient,
    LLMItem,
    LLMRequest,
    LLMUsage,
    ProviderOpaque,
    TextDelta,
    ToolCall,
    ToolCallDone,
    ToolCallStarted,
    ToolResult,
    UserMessage,
)

log = logging.getLogger(__name__)

MAX_ITERATIONS = 6
HISTORY_MESSAGES = 20  # stored messages replayed (user + assistant + system notes)
CACHE_KEY = "capimax-assistant-v1"  # constant: the prefix holds no user data
MAX_USER_CHARS = 4000

SAFE_MODE_TEXT = {
    "en": (
        "I couldn't complete that answer just now. Nothing was changed on your account. "
        "Please try again in a moment, or contact support and a person will help you."
    ),
    "ar": (
        "لم أتمكن من إكمال الإجابة الآن. لم يتغير أي شيء في حسابك. "
        "حاول مرة أخرى بعد قليل، أو تواصل مع الدعم وسيساعدك أحد الموظفين."
    ),
}


# --------------------------------------------------------------------------- #
# Run-time settings (DB-overridable, read once per turn)
# --------------------------------------------------------------------------- #
@dataclasses.dataclass(frozen=True)
class AssistantSettings:
    enabled: bool
    visitor_enabled: bool
    provider: str
    model: str
    effort: str
    max_output_tokens: int
    disabled_tools: frozenset[str]
    daily_message_cap: int
    daily_token_budget: int
    retention_days: int
    rollout: str
    pricing: dict[str, dict[str, float]]

    @property
    def model_configured(self) -> bool:
        return bool(self.model)


async def load_settings(session: AsyncSession) -> AssistantSettings:
    async def s(key: str) -> str:
        return (await settings_service.get_setting(session, key)).strip()

    try:
        pricing = json.loads(await s("assistant_model_pricing") or "{}")
        if not isinstance(pricing, dict):
            pricing = {}
    except ValueError:
        pricing = {}
    disabled = {t.strip() for t in (await s("assistant_disabled_tools")).split(",") if t.strip()}
    return AssistantSettings(
        enabled=(await s("assistant_enabled")).lower() == "true",
        visitor_enabled=(await s("assistant_visitor_enabled")).lower() == "true",
        provider=await s("assistant_provider") or "openai",
        model=await s("assistant_model"),
        effort=await s("assistant_reasoning_effort") or "low",
        max_output_tokens=int(await s("assistant_max_output_tokens") or 2048),
        disabled_tools=frozenset(disabled),
        daily_message_cap=int(await s("assistant_daily_message_cap") or 0),
        daily_token_budget=int(await s("assistant_daily_token_budget") or 0),
        retention_days=int(await s("assistant_retention_days") or 180),
        rollout=await s("assistant_rollout") or "admins",
        pricing=pricing,
    )


# --------------------------------------------------------------------------- #
# Cost
# --------------------------------------------------------------------------- #
def estimate_cost(usage: LLMUsage, price: dict[str, Any] | None) -> Decimal:
    """USD for one model call from the per-1M-token price list in settings. Uncached input
    is billed at the cache-write premium when nothing was served from cache (a new prefix
    was written); output includes reasoning tokens (already counted in output_tokens)."""
    if not price:
        return Decimal("0")
    million = Decimal(1_000_000)
    inp = Decimal(str(price.get("input", 0)))
    cached = Decimal(str(price.get("cached_input", 0)))
    out = Decimal(str(price.get("output", 0)))
    write_mult = Decimal(str(price.get("cache_write_multiplier", 1)))
    uncached_tokens = max(usage.input_tokens - usage.cached_input_tokens, 0)
    mult = write_mult if usage.cached_input_tokens == 0 else Decimal(1)
    cost = (
        Decimal(uncached_tokens) * inp * mult
        + Decimal(usage.cached_input_tokens) * cached
        + Decimal(usage.output_tokens) * out
    ) / million
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
# Item (de)serialisation: what we store on a message and replay next turn
# --------------------------------------------------------------------------- #
def item_to_dict(item: LLMItem) -> dict[str, Any]:
    if isinstance(item, UserMessage):
        return {"t": "user", "text": item.text}
    if isinstance(item, LLMAssistantMessage):
        return {"t": "assistant", "text": item.text}
    if isinstance(item, ToolCall):
        return {
            "t": "tool_call",
            "call_id": item.call_id,
            "name": item.name,
            "arguments_json": item.arguments_json,
        }
    if isinstance(item, ToolResult):
        return {
            "t": "tool_result",
            "call_id": item.call_id,
            "output": item.output,
            "is_error": item.is_error,
        }
    if isinstance(item, ProviderOpaque):
        return {"t": "opaque", "raw": item.raw}
    raise TypeError(f"unknown item {item!r}")


def item_from_dict(d: dict[str, Any]) -> LLMItem | None:
    t = d.get("t")
    if t == "user":
        return UserMessage(d["text"])
    if t == "assistant":
        return LLMAssistantMessage(d["text"])
    if t == "tool_call":
        return ToolCall(d["call_id"], d["name"], d["arguments_json"])
    if t == "tool_result":
        return ToolResult(d["call_id"], d["output"], bool(d.get("is_error")))
    if t == "opaque":
        return ProviderOpaque(d["raw"])
    return None


# --------------------------------------------------------------------------- #
# Conversations
# --------------------------------------------------------------------------- #
async def start_conversation(
    session: AsyncSession, ctx: AgentContext, *, title: str | None = None
) -> AssistantConversation:
    conv = AssistantConversation(
        user_id=ctx.user_id,
        visitor_key=ctx.visitor_key if ctx.is_visitor else None,
        active_role=ctx.active_role,
        lang=ctx.lang,
        title=title,
    )
    session.add(conv)
    await session.flush()
    return conv


async def get_conversation(
    session: AsyncSession, ctx: AgentContext, conversation_id: uuid.UUID
) -> AssistantConversation:
    """The caller's own conversation (user id, or visitor key for visitors)."""
    conv = await session.get(AssistantConversation, conversation_id)
    if conv is None:
        raise AppError("NOT_FOUND", "Conversation not found.", status_code=404)
    mine = (
        conv.user_id == ctx.user_id
        if not ctx.is_visitor
        else (conv.user_id is None and conv.visitor_key == ctx.visitor_key and ctx.visitor_key)
    )
    if not mine:
        raise AppError("NOT_FOUND", "Conversation not found.", status_code=404)
    return conv


async def add_system_note(
    session: AsyncSession, conversation_id: uuid.UUID, text: str, *, lang: str | None = None
) -> AssistantMessage:
    """A server-written fact for the next turn (e.g. the outcome of a confirmed action)."""
    note = AssistantMessage(
        conversation_id=conversation_id,
        role="system_note",
        text=text,
        content=[item_to_dict(UserMessage(f"[system note] {text}"))],
        lang=lang,
        enc_key_id=crypto.active_key_id(),
        created_at=dt.datetime.now(dt.UTC),
    )
    session.add(note)
    await session.flush()
    return note


async def _history_items(session: AsyncSession, conversation_id: uuid.UUID) -> list[LLMItem]:
    rows = (
        (
            await session.execute(
                select(AssistantMessage)
                .where(AssistantMessage.conversation_id == conversation_id)
                .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
                .limit(HISTORY_MESSAGES)
            )
        )
        .scalars()
        .all()
    )
    items: list[LLMItem] = []
    for row in reversed(rows):
        content = row.content if isinstance(row.content, list) else None
        if content:
            for d in content:
                item = item_from_dict(d) if isinstance(d, dict) else None
                if item is not None:
                    items.append(item)
        elif row.role == "user" and row.text:
            items.append(UserMessage(row.text))
        elif row.role == "assistant" and row.text:
            items.append(LLMAssistantMessage(row.text))
    return items


# --------------------------------------------------------------------------- #
# The turn
# --------------------------------------------------------------------------- #
def _event(event: str, **data: Any) -> dict[str, Any]:
    return {"event": event, "data": data}


def _safe_text(lang: str) -> str:
    return SAFE_MODE_TEXT["ar" if lang.startswith("ar") else "en"]


def _card_for(name: str, result: dict[str, Any], tokens: list[dict[str, Any]]) -> dict | None:
    """Server-built cards from a successful tool result. The model never authors these."""
    if name == "prepare_deep_link":
        return {"kind": "link", "path": result["path"], "label": result["label"]}
    if name == "get_property" and result.get("slug"):
        return {
            "kind": "property",
            "slug": result["slug"],
            "title": result.get("title"),
            "path": guard.make_link("property", result["slug"])["path"],
        }
    if name == "search_properties":
        items = [
            {
                "slug": p.get("slug"),
                "title": p.get("title"),
                "city": p.get("city"),
                "status": p.get("status"),
                "unit_price": p.get("unit_price"),
                "expected_yield": p.get("expected_yield"),
                "path": guard.make_link("property", p["slug"])["path"] if p.get("slug") else None,
            }
            for p in result.get("items", [])
        ]
        return {"kind": "properties", "items": items} if items else None
    if name == "propose_action":
        issued = next((t for t in tokens if t["proposal_id"] == result["proposal_id"]), None)
        card = {
            "kind": "confirm_action",
            "proposal_id": result["proposal_id"],
            "action": result["action"],
            "summary": result["summary"],
        }
        if issued:
            card["token"] = issued["token"]
            card["expires_at"] = issued["expires_at"]
        return card
    return None


def _persisted_card(card: dict[str, Any]) -> dict[str, Any]:
    # the one-time token is for the user's browser only; it is never written to the database
    return {k: v for k, v in card.items() if k != "token"}


async def _run_tool(
    session: AsyncSession, ctx: AgentContext, spec: ToolSpec | None, call: ToolCallDone
) -> tuple[str, bool, dict[str, Any] | None, list[dict[str, Any]]]:
    """(sanitised output JSON, is_error, raw allow-listed result, issued tokens)."""
    sink: list[dict[str, Any]] = []
    reset = guard.issued_tokens.set(sink)
    try:
        if spec is None:
            raise AppError("UNKNOWN_TOOL", f"No tool named {call.name!r}.", status_code=422)
        guard.authorize(spec, ctx)
        try:
            args = parse_args(spec, call.arguments_json)
        except Exception as exc:  # malformed arguments from the model are its own error
            raise AppError("INVALID_ARGUMENTS", str(exc)[:300], status_code=422) from exc
        async with session.begin_nested():
            result = await call_tool(spec, session, ctx, args)
        return guard.sanitize_result(call.name, result), False, result, sink
    except AppError as exc:
        payload = {"error": exc.code, "message": exc.message}
        return guard.sanitize_result(call.name, payload, is_error=True), True, None, sink
    except Exception:
        log.exception("assistant tool %s crashed", call.name)
        payload = {"error": "TOOL_FAILED", "message": "The tool could not run right now."}
        return guard.sanitize_result(call.name, payload, is_error=True), True, None, sink
    finally:
        guard.issued_tokens.reset(reset)


async def run_turn(
    session: AsyncSession,
    ctx: AgentContext,
    text: str,
    llm: LLMClient,
    *,
    settings: AssistantSettings | None = None,
    now: dt.datetime | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Handle one user message. Yields event dicts: started, delta, tool, card, reset, done.

    The caller owns the session; the turn commits once at the end so a crash mid-turn leaves
    no half-written message behind."""
    if ctx.conversation_id is None:
        raise AppError("NO_CONVERSATION", "A conversation is required.", status_code=422)
    settings = settings or await load_settings(session)
    if not settings.model:
        raise AppError("ASSISTANT_NOT_CONFIGURED", "No model configured.", status_code=503)
    conv = await session.get(AssistantConversation, ctx.conversation_id)
    if conv is None:
        raise AppError("NOT_FOUND", "Conversation not found.", status_code=404)

    clean_text = guard.strip_platform_context_tags(text).strip()[:MAX_USER_CHARS]
    if not clean_text:
        raise AppError("EMPTY_MESSAGE", "Say something first.", status_code=422)
    started_at = time.monotonic()
    now = now or dt.datetime.now(dt.UTC)

    history = await _history_items(session, conv.id)
    user_row = AssistantMessage(
        conversation_id=conv.id,
        role="user",
        text=clean_text,
        content=[item_to_dict(UserMessage(clean_text))],
        lang=ctx.lang,
        enc_key_id=crypto.active_key_id(),
        created_at=now,
    )
    session.add(user_row)
    await session.flush()

    instructions = prompts.build_instructions(await kb_service.render_bundle(session))
    tools = llm_tools(exclude=set(settings.disabled_tools))
    user_key = guard.safety_identifier(str(ctx.user_id or ctx.visitor_key or "anonymous"))
    prefix_items: list[LLMItem] = [
        *history,
        UserMessage(prompts.user_item_text(ctx, clean_text, now)),
    ]
    turn_items: list[LLMItem] = []  # what this turn adds (stored on the assistant message)
    tool_log: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    flags: set[str] = set()
    usage_total = LLMUsage()
    price = settings.pricing.get(settings.model) if isinstance(settings.pricing, dict) else None
    cost = Decimal(0)
    confidence = "normal"
    final_text = ""
    first_token_ms: int | None = None
    safe_mode: str | None = None
    iterations = 0

    yield _event("started", conversation_id=str(conv.id), user_message_id=str(user_row.id))

    for _iteration in range(MAX_ITERATIONS):
        iterations += 1
        req = LLMRequest(
            instructions=instructions,
            tools=tools,
            items=tuple(prefix_items + turn_items),
            model=settings.model,
            effort=settings.effort,
            max_output_tokens=settings.max_output_tokens,
            cache_key=CACHE_KEY,
            user_key=user_key,
        )
        text_buf = ""
        calls: list[ToolCallDone] = []
        completed: Completed | None = None
        failed: Failed | None = None
        async for ev in llm.stream(req):
            if isinstance(ev, TextDelta):
                if first_token_ms is None:
                    first_token_ms = int((time.monotonic() - started_at) * 1000)
                text_buf += ev.text
                yield _event("delta", text=ev.text)
            elif isinstance(ev, ToolCallStarted):
                yield _event("tool", name=ev.name, status="running")
            elif isinstance(ev, ToolCallDone):
                calls.append(ev)
            elif isinstance(ev, Completed):
                completed = ev
            elif isinstance(ev, Failed):
                failed = ev
        if failed is not None or completed is None:
            code = failed.code if failed else "NO_TERMINAL_EVENT"
            log.warning("assistant provider failure %s: %s", code, failed and failed.message)
            flags.add(f"provider_error:{code}")
            safe_mode = code
            break
        usage_total = usage_total.add(completed.usage)
        cost += estimate_cost(completed.usage, price)  # per call: the cache premium is per call
        turn_items.extend(completed.opaque_items)
        if text_buf:
            turn_items.append(LLMAssistantMessage(text_buf))
            final_text = text_buf
        if completed.stop == "tool_calls" and calls:
            for call in calls:
                turn_items.append(ToolCall(call.call_id, call.name, call.arguments_json))
            for call in calls:
                spec = REGISTRY.get(call.name)
                if spec is not None and call.name in settings.disabled_tools:
                    spec = None
                t0 = time.monotonic()
                output, is_error, raw, tokens = await _run_tool(session, ctx, spec, call)
                ms = int((time.monotonic() - t0) * 1000)
                turn_items.append(ToolResult(call.call_id, output, is_error))
                tool_log.append(
                    {
                        "name": call.name,
                        "arguments": call.arguments_json[:2000],
                        "ok": not is_error,
                        "ms": ms,
                    }
                )
                yield _event("tool", name=call.name, status="error" if is_error else "ok")
                if call.name == "report_knowledge_gap" and not is_error:
                    confidence = "low"
                    flags.add("knowledge_gap")
                if raw is not None:
                    card = _card_for(call.name, raw, tokens)
                    if card is not None:
                        cards.append(card)
                        yield _event("card", **card)
            continue
        if completed.stop == "end":
            break
        # max_tokens / incomplete / refusal: never present a half answer as an answer
        flags.add(f"stop:{completed.stop}")
        safe_mode = completed.stop
        break
    else:
        flags.add("iteration_cap")
        safe_mode = "iteration_cap"

    if safe_mode is None and not final_text:
        flags.add("empty_answer")
        safe_mode = "empty_answer"
    if safe_mode is not None:
        final_text = _safe_text(ctx.lang)
        confidence = "safe_mode"
        # history must not replay a half answer either: the turn is recorded as the safe text
        turn_items = [LLMAssistantMessage(final_text)]
        link = guard.make_link("support")
        cards.append({"kind": "link", "path": link["path"], "label": link["label"]})
        # anything already streamed is withdrawn: the client replaces it with the safe text
        yield _event("reset")
        yield _event("delta", text=final_text)
        yield _event("card", **cards[-1])
    else:
        cleaned, out_flags = guard.postprocess_output(final_text)
        flags.update(out_flags)
        if cleaned != final_text:
            # the raw text was already streamed: withdraw it and send the cleaned version
            yield _event("reset")
            yield _event("delta", text=cleaned)
        final_text = cleaned

    latency_ms = int((time.monotonic() - started_at) * 1000)
    assistant_row = AssistantMessage(
        conversation_id=conv.id,
        role="assistant",
        text=final_text,
        content=[item_to_dict(i) for i in turn_items],
        tool_calls=tool_log,
        cards=[_persisted_card(c) for c in cards],
        usage={
            "input_tokens": usage_total.input_tokens,
            "cached_input_tokens": usage_total.cached_input_tokens,
            "output_tokens": usage_total.output_tokens,
            "reasoning_tokens": usage_total.reasoning_tokens,
            "iterations": iterations,
            "cost_usd": str(cost),
        },
        latency_ms=latency_ms,
        first_token_ms=first_token_ms,
        confidence=confidence,
        guardrail_flags=sorted(flags),
        lang=ctx.lang,
        enc_key_id=crypto.active_key_id(),
        created_at=max(dt.datetime.now(dt.UTC), now + dt.timedelta(microseconds=1)),
    )
    session.add(assistant_row)
    conv.message_count = (conv.message_count or 0) + 2
    conv.total_input_tokens = (conv.total_input_tokens or 0) + usage_total.input_tokens
    conv.total_cached_input_tokens = (
        conv.total_cached_input_tokens or 0
    ) + usage_total.cached_input_tokens
    conv.total_output_tokens = (conv.total_output_tokens or 0) + usage_total.output_tokens
    conv.total_reasoning_tokens = (conv.total_reasoning_tokens or 0) + (
        usage_total.reasoning_tokens or 0
    )
    conv.est_cost_usd = (conv.est_cost_usd or Decimal(0)) + cost
    conv.model = settings.model
    conv.provider = getattr(llm, "provider", settings.provider)
    conv.last_message_at = now
    if not conv.title:
        conv.title = clean_text[:80]
    await session.flush()
    await session.commit()

    yield _event(
        "done",
        message_id=str(assistant_row.id),
        confidence=confidence,
        flags=sorted(flags),
        usage=assistant_row.usage,
        latency_ms=latency_ms,
        first_token_ms=first_token_ms,
        safe_mode=safe_mode,
    )


def timeout_seconds() -> float:
    return float(get_settings().assistant_timeout_seconds)
