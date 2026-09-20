"""OpenAI Responses API adapter (plan §1/§2). Translates the neutral request into one
streamed ``responses.create`` call and maps the provider's events back to neutral events.

Privacy and cost rules baked in:
  * ``store=False`` — the provider keeps no response history for us; reasoning items come
    back encrypted and are replayed verbatim as ``ProviderOpaque`` items;
  * ``safety_identifier`` is the caller-supplied HMAC (never a user id);
  * ``prompt_cache_key`` is a constant routing key so the byte-stable prefix (instructions +
    tools) is cached; per-user data never lives in that prefix;
  * every provider exception becomes a ``Failed`` event, never an exception in the agent.

The SDK client is injectable so the mapping is unit-tested without network access.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import get_settings
from app.services.llm.types import (
    AssistantMessage,
    Completed,
    Failed,
    LLMRequest,
    LLMStreamEvent,
    LLMUsage,
    ProviderOpaque,
    Started,
    StopReason,
    TextDelta,
    ToolCall,
    ToolCallDelta,
    ToolCallDone,
    ToolCallStarted,
    ToolResult,
    UserMessage,
)

log = logging.getLogger("capimax.assistant.openai")

# Reasoning items must be replayed next turn when store=False; ask for their encrypted form.
INCLUDE = ["reasoning.encrypted_content"]


def to_input_items(items: tuple) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in items:
        if isinstance(it, UserMessage):
            out.append({"role": "user", "content": it.text})
        elif isinstance(it, AssistantMessage):
            out.append({"role": "assistant", "content": it.text})
        elif isinstance(it, ToolCall):
            out.append(
                {
                    "type": "function_call",
                    "call_id": it.call_id,
                    "name": it.name,
                    "arguments": it.arguments_json,
                }
            )
        elif isinstance(it, ToolResult):
            out.append({"type": "function_call_output", "call_id": it.call_id, "output": it.output})
        elif isinstance(it, ProviderOpaque):
            out.append(dict(it.raw))
        else:  # pragma: no cover - the union is closed
            raise TypeError(f"unsupported item {type(it).__name__}")
    return out


def to_tools(tools: tuple) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters_schema,
            "strict": t.strict,
        }
        for t in tools
    ]


def build_params(req: LLMRequest) -> dict[str, Any]:
    """Exactly what is sent (tests pin it). Order of keys is irrelevant to the API."""
    params: dict[str, Any] = {
        "model": req.model,
        "instructions": req.instructions,
        "input": to_input_items(req.items),
        "tools": to_tools(req.tools),
        "reasoning": {"effort": req.effort},
        "max_output_tokens": req.max_output_tokens,
        "store": False,
        "include": INCLUDE,
        "parallel_tool_calls": True,
        "stream": True,
    }
    if req.cache_key:
        params["prompt_cache_key"] = req.cache_key
    if req.user_key:
        params["safety_identifier"] = req.user_key
    return params


def _usage_of(response: Any) -> LLMUsage:
    u = getattr(response, "usage", None)
    if u is None:
        return LLMUsage()
    cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
    reasoning = getattr(getattr(u, "output_tokens_details", None), "reasoning_tokens", None)
    return LLMUsage(
        int(getattr(u, "input_tokens", 0) or 0),
        int(cached),
        int(getattr(u, "output_tokens", 0) or 0),
        None if reasoning is None else int(reasoning),
    )


def _error_code(exc: Exception) -> str:
    try:
        import openai
    except ImportError:  # pragma: no cover
        return "PROVIDER_ERROR"
    if isinstance(exc, openai.RateLimitError):
        return "RATE_LIMIT"
    if isinstance(exc, openai.AuthenticationError):
        return "AUTH"
    if isinstance(exc, openai.APITimeoutError):
        return "TIMEOUT"
    if isinstance(exc, openai.APIConnectionError):
        return "CONNECTION"
    if isinstance(exc, openai.BadRequestError):
        return "BAD_REQUEST"
    if isinstance(exc, openai.APIStatusError):
        return f"HTTP_{getattr(exc, 'status_code', 'ERR')}"
    return "PROVIDER_ERROR"


class OpenAIResponsesAdapter:
    provider = "openai"

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI

            s = get_settings()
            self._client = AsyncOpenAI(
                api_key=s.openai_api_key, timeout=s.assistant_timeout_seconds
            )
        return self._client

    async def stream(self, req: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        try:
            events = await self._get_client().responses.create(**build_params(req))
        except Exception as exc:  # noqa: BLE001 — every provider failure becomes an event
            log.warning("openai request failed: %s: %s", type(exc).__name__, exc)
            yield Failed(_error_code(exc), str(exc)[:300])
            return
        try:
            async for ev in self._map(events):
                yield ev
        except Exception as exc:  # noqa: BLE001
            log.warning("openai stream failed: %s: %s", type(exc).__name__, exc)
            yield Failed(_error_code(exc), str(exc)[:300])

    async def _map(self, events: Any) -> AsyncIterator[LLMStreamEvent]:
        """Provider events -> neutral events. Tool-call deltas arrive keyed by item id, so the
        item id is mapped to the call id announced by ``output_item.added``."""
        call_ids: dict[str, str] = {}
        names: dict[str, str] = {}
        opaque: list[ProviderOpaque] = []
        saw_tool_call = False
        refused = False
        terminal = False
        async for ev in events:
            kind = getattr(ev, "type", "")
            if kind == "response.created":
                yield Started(getattr(getattr(ev, "response", None), "id", "") or "")
            elif kind == "response.output_text.delta":
                yield TextDelta(ev.delta)
            elif kind == "response.output_item.added":
                item = ev.item
                if getattr(item, "type", "") == "function_call":
                    call_ids[item.id] = item.call_id
                    names[item.id] = item.name
                    saw_tool_call = True
                    yield ToolCallStarted(item.call_id, item.name)
            elif kind == "response.function_call_arguments.delta":
                cid = call_ids.get(ev.item_id, ev.item_id)
                yield ToolCallDelta(cid, ev.delta)
            elif kind == "response.function_call_arguments.done":
                cid = call_ids.get(ev.item_id, ev.item_id)
                yield ToolCallDone(cid, names.get(ev.item_id, ""), ev.arguments)
            elif kind == "response.output_item.done":
                item = ev.item
                if getattr(item, "type", "") == "reasoning":
                    raw = _item_dict(item)
                    if raw.get("encrypted_content"):
                        opaque.append(ProviderOpaque(raw))
            elif kind == "response.refusal.done":
                refused = True
            elif kind == "response.completed":
                stop: StopReason = (
                    "refusal" if refused else "tool_calls" if saw_tool_call else "end"
                )
                terminal = True
                yield Completed(_usage_of(ev.response), stop, tuple(opaque))
            elif kind == "response.incomplete":
                reason = (
                    getattr(getattr(ev.response, "incomplete_details", None), "reason", "") or ""
                )
                stop = "max_tokens" if reason == "max_output_tokens" else "incomplete"
                terminal = True
                yield Completed(_usage_of(ev.response), stop, tuple(opaque))
            elif kind == "response.failed":
                err = getattr(ev.response, "error", None)
                terminal = True
                yield Failed(
                    str(getattr(err, "code", "") or "PROVIDER_FAILED"),
                    str(getattr(err, "message", "") or "The model response failed."),
                )
            elif kind == "error":
                terminal = True
                yield Failed(
                    str(getattr(ev, "code", "") or "PROVIDER_ERROR"),
                    str(getattr(ev, "message", "") or "Provider error."),
                )
            # everything else (in_progress, content_part, reasoning summaries...) is ignored
            if terminal:
                return
        yield Failed("STREAM_ENDED", "The provider stream ended without completing.")


def _item_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(exclude_none=True)
    if isinstance(item, dict):
        return dict(item)
    return {k: v for k, v in vars(item).items() if v is not None}
