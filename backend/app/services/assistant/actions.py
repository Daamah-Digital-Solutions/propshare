"""Confirmed actions (plan §4): the ONLY things the assistant can cause to happen.

    model  -> propose_action tool  -> proposal row + one-time token (card to the user)
    user   -> POST .../actions/{id}/confirm {token}  -> verify -> executor -> audit
    server -> system note in the conversation so the next turn knows the real outcome

Executors reuse the platform's own services; nothing here bypasses their rules. Phase 1 has
three executors; adding one is a new entry in ``EXECUTORS`` plus an entry in the tool's
``ACTIONS`` list (and a test).
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import AssistantActionProposal
from app.services import (
    auth_service,
    gift_service,
    liquidity_service,
    notification_service,
    secondary_service,
    ticket_service,
)
from app.services.assistant import agent, guard
from app.services.assistant.tools.actions import PREF_KEYS

log = logging.getLogger(__name__)

Executor = Callable[[AsyncSession, uuid.UUID, AssistantActionProposal], Awaitable[dict[str, Any]]]


async def _resend_verification_email(
    session: AsyncSession, user_id: uuid.UUID, proposal: AssistantActionProposal
) -> dict[str, Any]:
    await auth_service.resend_verification(session, user_id=user_id)
    return {"sent": True}


async def _mark_all_notifications_read(
    session: AsyncSession, user_id: uuid.UUID, proposal: AssistantActionProposal
) -> dict[str, Any]:
    marked = await notification_service.mark_all_read(session, user_id)
    return {"marked": marked}


async def _create_support_ticket(
    session: AsyncSession, user_id: uuid.UUID, proposal: AssistantActionProposal
) -> dict[str, Any]:
    params = proposal.params or {}
    handoff = await ticket_service.build_handoff_summary(
        session,
        conversation_id=proposal.conversation_id,
        category=str(params.get("category") or "other"),
        priority=str(params.get("priority") or "normal"),
        refs=params.get("refs") or {},
    )
    ticket = await ticket_service.create_from_handoff(session, user_id=user_id, handoff=handoff)
    return {"ticket_no": ticket.ticket_no, "ticket_id": str(ticket.id)}


async def _cancel_secondary_listing(
    session: AsyncSession, user_id: uuid.UUID, proposal: AssistantActionProposal
) -> dict[str, Any]:
    listing_id = uuid.UUID(str((proposal.params or {}).get("listing_id")))
    out = await secondary_service.cancel_listing(session, seller_id=user_id, listing_id=listing_id)
    return {"listing_id": str(listing_id), "status": str(out.get("status", "cancelled"))}


async def _cancel_liquidity_exit_request(
    session: AsyncSession, user_id: uuid.UUID, proposal: AssistantActionProposal
) -> dict[str, Any]:
    request_id = uuid.UUID(str((proposal.params or {}).get("request_id")))
    out = await liquidity_service.cancel_exit_request(
        session, seller_id=user_id, request_id=request_id
    )
    return {"request_id": str(request_id), "status": str(out.get("status", "cancelled"))}


async def _cancel_scheduled_gift(
    session: AsyncSession, user_id: uuid.UUID, proposal: AssistantActionProposal
) -> dict[str, Any]:
    gift_id = uuid.UUID(str((proposal.params or {}).get("gift_id")))
    out = await gift_service.cancel_gift(session, giver_id=user_id, gift_id=gift_id)
    return {"gift_id": str(gift_id), "status": str(out.get("status", "cancelled"))}


async def _update_notification_preferences(
    session: AsyncSession, user_id: uuid.UUID, proposal: AssistantActionProposal
) -> dict[str, Any]:
    changes = (proposal.params or {}).get("preferences") or {}
    allowed = {k: bool(v) for k, v in changes.items() if k in PREF_KEYS}
    if not allowed:
        raise AppError("INVALID_INPUT", "Nothing to change.", status_code=422)
    prefs = await notification_service.update_preferences(session, user_id, **allowed)
    return {"preferences": prefs}


EXECUTORS: dict[str, Executor] = {
    "resend_verification_email": _resend_verification_email,
    "mark_all_notifications_read": _mark_all_notifications_read,
    "create_support_ticket": _create_support_ticket,
    "cancel_secondary_listing": _cancel_secondary_listing,
    "cancel_liquidity_exit_request": _cancel_liquidity_exit_request,
    "cancel_scheduled_gift": _cancel_scheduled_gift,
    "update_notification_preferences": _update_notification_preferences,
}


def _note(action: str, ok: bool, result: dict[str, Any]) -> str:
    if not ok:
        return f"Action {action} FAILED: {result.get('message', 'unknown error')}"
    if action == "create_support_ticket":
        return f"Action {action} executed: ticket {result.get('ticket_no')} was opened."
    if action == "mark_all_notifications_read":
        return f"Action {action} executed: {result.get('marked', 0)} notifications marked read."
    return f"Action {action} executed successfully."


async def confirm(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    proposal_id: uuid.UUID,
    token: str,
    ip: str | None = None,
) -> AssistantActionProposal:
    """Verify the one-time token, run the executor, record the outcome. Any executor failure
    is recorded on the proposal (status ``failed``) and in the conversation; the proposal
    can never be retried with the same token."""
    proposal = await guard.verify_confirmation(
        session, user_id=user_id, proposal_id=proposal_id, token=token
    )
    executor = EXECUTORS.get(proposal.action)
    if executor is None:
        proposal.status = "failed"
        proposal.result = {"error": "UNKNOWN_ACTION"}
        raise AppError("UNKNOWN_ACTION", "This action is not available.", status_code=422)
    try:
        async with session.begin_nested():
            result = await executor(session, user_id, proposal)
        proposal.status = "executed"
        proposal.result = result
        ok = True
    except AppError as exc:
        proposal.status = "failed"
        proposal.result = {"error": exc.code, "message": exc.message}
        result, ok = proposal.result, False
    except Exception:
        log.exception("assistant action %s crashed", proposal.action)
        proposal.status = "failed"
        proposal.result = {"error": "ACTION_FAILED", "message": "The action could not run."}
        result, ok = proposal.result, False
    proposal.decided_at = dt.datetime.now(dt.UTC)
    await write_audit(
        session,
        action=f"assistant.action.{'executed' if ok else 'failed'}",
        entity_type="assistant_action_proposal",
        entity_id=str(proposal.id),
        actor_id=user_id,
        after={"action": proposal.action, "result": result},
        ip=ip,
    )
    await agent.add_system_note(
        session, proposal.conversation_id, _note(proposal.action, ok, result)
    )
    await session.flush()
    return proposal


async def cancel(
    session: AsyncSession, *, user_id: uuid.UUID, proposal_id: uuid.UUID
) -> AssistantActionProposal:
    proposal = await session.get(AssistantActionProposal, proposal_id)
    if proposal is None or proposal.user_id != user_id:
        raise AppError("NOT_FOUND", "Proposal not found.", status_code=404)
    if proposal.status != "awaiting_user_confirmation":
        raise AppError("PROPOSAL_USED", "This action was already decided.", status_code=409)
    proposal.status = "cancelled"
    proposal.decided_at = dt.datetime.now(dt.UTC)
    await agent.add_system_note(
        session, proposal.conversation_id, f"Action {proposal.action} was cancelled by the user."
    )
    await session.flush()
    return proposal
