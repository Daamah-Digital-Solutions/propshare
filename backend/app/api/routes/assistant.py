"""Assistant HTTP surface (plan §4): status, consent, conversations, the SSE message stream,
action confirmation, feedback and the maintenance jobs.

Gate order for every message: deploy-level kill switch -> DB kill switch -> model configured
-> rollout (admins / all / visitors) -> consent (signed-in) -> per-user daily cap -> global
daily token budget. ``GET /status`` runs the same checks and reports the first failing one
instead of raising, so the widget can fall back without a round of errors.

The SSE stream runs on its OWN database session: the request-scoped session would end when
the handler returns, long before the model has finished.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import uuid
from collections.abc import AsyncIterator, Callable

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminOrCronDep, Principal, PrincipalDep, SessionDep, current_principal
from app.core import crypto
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import AppError
from app.core.ratelimit import ASSISTANT_LIMIT, limiter
from app.models import AssistantActionProposal, AssistantConversation, AssistantMessage
from app.schemas.assistant import (
    ConfirmIn,
    ConsentIn,
    ConsentOut,
    ConversationOut,
    FeedbackIn,
    MaintenanceOut,
    MessageIn,
    MessageOut,
    ProposalOut,
    StatusOut,
)
from app.services.assistant import actions, agent, consent
from app.services.assistant.agent import AssistantSettings
from app.services.assistant.context import AgentContext, load_context
from app.services.llm import registry
from app.services.llm.types import LLMClient

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

_VISITOR_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")

# Tests replace this with a factory returning the scripted FakeLLM.
llm_factory: Callable[[str], LLMClient] = registry.get_client


# --------------------------------------------------------------------------- #
# Who is calling: a signed-in principal, or a visitor with a browser-generated key
# --------------------------------------------------------------------------- #
async def _caller(request: Request) -> tuple[Principal | None, str | None]:
    if request.headers.get("Authorization"):
        return await current_principal(request), None
    key = request.headers.get("X-Visitor-Key", "")
    return None, key if _VISITOR_KEY_RE.match(key) else None


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# --------------------------------------------------------------------------- #
# Gate
# --------------------------------------------------------------------------- #
async def _gate(
    session: AsyncSession, principal: Principal | None, visitor_key: str | None
) -> tuple[AssistantSettings, str | None]:
    """Returns (settings, reason). ``reason`` is None when this caller may use the assistant."""
    settings = await agent.load_settings(session)
    if not get_settings().assistant_configured:
        return settings, "ASSISTANT_DISABLED"
    if not settings.enabled:
        return settings, "ASSISTANT_DISABLED"
    if not settings.model:
        return settings, "ASSISTANT_NOT_CONFIGURED"
    if principal is None:
        if not settings.visitor_enabled or settings.rollout == "admins":
            return settings, "SIGN_IN_REQUIRED"
        if not visitor_key:
            return settings, "VISITOR_KEY_REQUIRED"
        return settings, None
    if settings.rollout == "admins" and "admin" not in principal.roles:
        return settings, "NOT_IN_ROLLOUT"
    if not await consent.has_consent(session, principal.user_id):
        return settings, "CONSENT_REQUIRED"
    if settings.daily_message_cap and await _messages_today(session, principal.user_id) >= (
        settings.daily_message_cap
    ):
        return settings, "DAILY_CAP"
    if settings.daily_token_budget and await _tokens_today(session) >= settings.daily_token_budget:
        return settings, "BUDGET_EXHAUSTED"
    return settings, None


_GATE_STATUS = {
    "ASSISTANT_DISABLED": 503,
    "ASSISTANT_NOT_CONFIGURED": 503,
    "SIGN_IN_REQUIRED": 401,
    "VISITOR_KEY_REQUIRED": 400,
    "NOT_IN_ROLLOUT": 403,
    "CONSENT_REQUIRED": 428,
    "DAILY_CAP": 429,
    "BUDGET_EXHAUSTED": 503,
}
_GATE_MESSAGE = {
    "ASSISTANT_DISABLED": "The assistant is switched off.",
    "ASSISTANT_NOT_CONFIGURED": "The assistant is not configured yet.",
    "SIGN_IN_REQUIRED": "Please sign in to use the assistant.",
    "VISITOR_KEY_REQUIRED": "A visitor key is required.",
    "NOT_IN_ROLLOUT": "The assistant is not available to your account yet.",
    "CONSENT_REQUIRED": "Please accept the assistant privacy notice first.",
    "DAILY_CAP": "You have reached today's message limit. Please try again tomorrow.",
    "BUDGET_EXHAUSTED": (
        "The assistant is busy today. Please try again tomorrow or contact support."
    ),
}


def _raise_gate(reason: str) -> None:
    details = {"policy_version": consent.current_version()} if reason == "CONSENT_REQUIRED" else {}
    raise AppError(reason, _GATE_MESSAGE[reason], status_code=_GATE_STATUS[reason], details=details)


def _today() -> dt.datetime:
    now = dt.datetime.now(dt.UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def _messages_today(session: AsyncSession, user_id: uuid.UUID) -> int:
    n = await session.scalar(
        select(func.count())
        .select_from(AssistantMessage)
        .join(AssistantConversation, AssistantConversation.id == AssistantMessage.conversation_id)
        .where(
            AssistantConversation.user_id == user_id,
            AssistantMessage.role == "user",
            AssistantMessage.created_at >= _today(),
        )
    )
    return int(n or 0)


async def _tokens_today(session: AsyncSession) -> int:
    usage = AssistantMessage.usage
    total = await session.scalar(
        select(
            func.coalesce(
                func.sum(
                    cast(usage["input_tokens"].astext, Integer)
                    + cast(usage["output_tokens"].astext, Integer)
                ),
                0,
            )
        ).where(AssistantMessage.role == "assistant", AssistantMessage.created_at >= _today())
    )
    return int(total or 0)


# --------------------------------------------------------------------------- #
# Status + consent
# --------------------------------------------------------------------------- #
@router.get("/status", response_model=StatusOut)
async def status(request: Request, session: SessionDep):
    principal, visitor_key = await _caller(request)
    settings, reason = await _gate(session, principal, visitor_key)
    given = principal is not None and await consent.has_consent(session, principal.user_id)
    return StatusOut(
        enabled=reason is None,
        reason=reason,
        provider=settings.provider,
        model_configured=bool(settings.model),
        encryption="ok" if crypto.is_configured() else "missing",
        policy_version=consent.current_version(),
        consent_required=principal is not None and not given,
        consent_given=given,
        visitor_allowed=settings.visitor_enabled and settings.rollout != "admins",
        rollout=settings.rollout,
        reply_language=settings.reply_language,
    )


@router.post("/consent", response_model=ConsentOut)
async def give_consent(
    body: ConsentIn, request: Request, principal: PrincipalDep, session: SessionDep
):
    row = await consent.record(
        session, user_id=principal.user_id, policy_version=body.policy_version, ip=_ip(request)
    )
    await session.flush()
    await session.refresh(row)
    return ConsentOut(policy_version=row.policy_version, accepted_at=row.accepted_at)


# --------------------------------------------------------------------------- #
# Conversations
# --------------------------------------------------------------------------- #
async def _context(
    session: AsyncSession,
    principal: Principal | None,
    visitor_key: str | None,
    *,
    lang: str = "en",
    conversation_id: uuid.UUID | None = None,
) -> AgentContext:
    return await load_context(
        session,
        user_id=principal.user_id if principal else None,
        visitor_key=visitor_key,
        lang=lang,
        conversation_id=conversation_id,
    )


def _conv_out(c: AssistantConversation) -> ConversationOut:
    return ConversationOut(
        id=c.id,
        title=c.title,
        status=c.status,
        lang=c.lang,
        message_count=c.message_count,
        created_at=c.created_at,
        last_message_at=c.last_message_at,
    )


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(request: Request, session: SessionDep):
    principal, visitor_key = await _caller(request)
    _settings, reason = await _gate(session, principal, visitor_key)
    if reason:
        _raise_gate(reason)
    ctx = await _context(session, principal, visitor_key)
    conv = await agent.start_conversation(session, ctx)
    await session.flush()
    await session.refresh(conv)
    return _conv_out(conv)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(principal: PrincipalDep, session: SessionDep):
    rows = (
        (
            await session.execute(
                select(AssistantConversation)
                .where(AssistantConversation.user_id == principal.user_id)
                .order_by(AssistantConversation.last_message_at.desc().nulls_last())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    return [_conv_out(c) for c in rows]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(conversation_id: uuid.UUID, request: Request, session: SessionDep):
    principal, visitor_key = await _caller(request)
    ctx = await _context(session, principal, visitor_key)
    conv = await agent.get_conversation(session, ctx, conversation_id)
    rows = (
        (
            await session.execute(
                select(AssistantMessage)
                .where(
                    AssistantMessage.conversation_id == conv.id,
                    AssistantMessage.role.in_(("user", "assistant")),
                )
                .order_by(AssistantMessage.created_at)
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            text=m.text,
            cards=m.cards if isinstance(m.cards, list) else [],
            confidence=m.confidence,
            feedback=m.feedback,
            created_at=m.created_at,
        )
        for m in rows
    ]


# --------------------------------------------------------------------------- #
# The message stream (SSE)
# --------------------------------------------------------------------------- #
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def _stream(
    ctx: AgentContext, text: str, settings: AssistantSettings, llm: LLMClient
) -> AsyncIterator[str]:
    timeout = agent.timeout_seconds()
    maker = get_sessionmaker()
    async with maker() as session:
        gen = agent.run_turn(session, ctx, text, llm, settings=settings)
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(gen.__anext__(), timeout)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    yield _sse("error", {"code": "TIMEOUT", "message": agent.SAFE_MODE_TEXT["en"]})
                    break
                except AppError as exc:
                    yield _sse("error", {"code": exc.code, "message": exc.message})
                    break
                yield _sse(ev["event"], ev["data"])
        finally:
            await gen.aclose()


@router.post("/conversations/{conversation_id}/messages")
@limiter.limit(ASSISTANT_LIMIT)
async def send_message(
    conversation_id: uuid.UUID, body: MessageIn, request: Request, session: SessionDep
):
    principal, visitor_key = await _caller(request)
    settings, reason = await _gate(session, principal, visitor_key)
    if reason:
        _raise_gate(reason)
    ctx = await _context(
        session, principal, visitor_key, lang=body.lang, conversation_id=conversation_id
    )
    await agent.get_conversation(session, ctx, conversation_id)  # ownership check
    llm = llm_factory(settings.provider)
    return StreamingResponse(
        _stream(ctx, body.text, settings, llm),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------- #
# Actions: confirm / cancel
# --------------------------------------------------------------------------- #
def _proposal_out(p: AssistantActionProposal) -> ProposalOut:
    return ProposalOut(
        id=p.id,
        action=p.action,
        status=p.status,
        summary=p.summary,
        result=p.result,
        decided_at=p.decided_at,
    )


@router.post("/actions/{proposal_id}/confirm", response_model=ProposalOut)
async def confirm_action(
    proposal_id: uuid.UUID,
    body: ConfirmIn,
    request: Request,
    principal: PrincipalDep,
    session: SessionDep,
):
    proposal = await actions.confirm(
        session,
        user_id=principal.user_id,
        proposal_id=proposal_id,
        token=body.token,
        ip=_ip(request),
    )
    return _proposal_out(proposal)


@router.post("/actions/{proposal_id}/cancel", response_model=ProposalOut)
async def cancel_action(proposal_id: uuid.UUID, principal: PrincipalDep, session: SessionDep):
    return _proposal_out(
        await actions.cancel(session, user_id=principal.user_id, proposal_id=proposal_id)
    )


# --------------------------------------------------------------------------- #
# Feedback
# --------------------------------------------------------------------------- #
@router.post("/messages/{message_id}/feedback", status_code=204)
async def feedback(message_id: uuid.UUID, body: FeedbackIn, request: Request, session: SessionDep):
    principal, visitor_key = await _caller(request)
    ctx = await _context(session, principal, visitor_key)
    msg = await session.get(AssistantMessage, message_id)
    if msg is None or msg.role != "assistant":
        raise AppError("NOT_FOUND", "Message not found.", status_code=404)
    await agent.get_conversation(session, ctx, msg.conversation_id)
    msg.feedback = body.feedback
    return None


# --------------------------------------------------------------------------- #
# Maintenance (admin or cron)
# --------------------------------------------------------------------------- #
@router.post("/maintenance/purge", response_model=MaintenanceOut)
async def purge(_caller_: AdminOrCronDep, session: SessionDep):
    from app.services.assistant import maintenance

    settings = await agent.load_settings(session)
    purged = await maintenance.purge_expired(session, retention_days=settings.retention_days)
    return MaintenanceOut(purged=purged)


@router.post("/maintenance/nudges")
async def nudges(_caller_: AdminOrCronDep, session: SessionDep) -> dict[str, int]:
    """Hourly cron: proactive reminders (unverified email, KYC not started / in review,
    funded-but-idle wallet, ticket waiting for the user). Idempotent via cooldowns."""
    from app.services import nudge_service

    return await nudge_service.run_all(session)


@router.post("/maintenance/index-documents")
async def index_documents(_caller_: AdminOrCronDep, session: SessionDep) -> dict[str, int]:
    """Hourly cron: extract text from property documents that are not indexed yet."""
    from app.services import document_index_service

    return await document_index_service.index_pending(session)


@router.post("/maintenance/ops-cases")
async def ops_cases(_caller_: AdminOrCronDep, session: SessionDep) -> dict:
    """Hourly cron: open internal cases for ledger drift, stale bank claims and unpaid
    withdrawals (once per condition while the case is open)."""
    from app.services import ops_case_service

    return await ops_case_service.sweep(session)


@router.post("/maintenance/ticket-sla")
async def ticket_sla(_caller_: AdminOrCronDep, session: SessionDep) -> dict:
    """Hourly cron: escalate tickets past their first-response SLA (once each)."""
    from app.services import ticket_service

    return await ticket_service.escalate_overdue(session)


@router.post("/maintenance/daily-digest")
async def daily_digest(_caller_: AdminOrCronDep, session: SessionDep) -> dict:
    """Daily cron: queue the support & assistant digest (counts only) to the support inbox."""
    from app.services import ticket_service

    return await ticket_service.send_daily_digest(session)


@router.post("/maintenance/reencrypt", response_model=MaintenanceOut)
async def reencrypt(_caller_: AdminOrCronDep, session: SessionDep):
    from app.services.assistant import maintenance

    if not crypto.is_configured():
        raise AppError("ASSISTANT_NOT_CONFIGURED", "Encryption key missing.", status_code=503)
    out = await maintenance.reencrypt(session)
    return MaintenanceOut(**out)
