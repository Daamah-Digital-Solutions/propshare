"""Proposals and knowledge gaps (plan §4).

``propose_action`` never executes anything: it records a proposal with a one-time token that
only the user's browser receives (as a card), and the confirmation is a separate authenticated
HTTP call that runs the executor. The tool's own output deliberately omits the token, so the
model can neither see nor replay it.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import SupportTicket
from app.services import gift_service, liquidity_service, secondary_service
from app.services.assistant import guard
from app.services.assistant.context import AgentContext
from app.services.assistant.tools.base import ToolOutput, ToolSpec, register

ACTIONS: dict[str, str] = {
    "resend_verification_email": "Send the email-verification link again.",
    "mark_all_notifications_read": "Mark all notifications as read.",
    "create_support_ticket": "Open a support ticket for a person to follow up.",
    "cancel_secondary_listing": "Cancel one of your active secondary-market listings.",
    "cancel_liquidity_exit_request": "Cancel one of your open liquidity exit requests.",
    "cancel_scheduled_gift": "Cancel one of your scheduled gifts.",
    "update_notification_preferences": "Change which email notifications you receive.",
}
PREF_KEYS = (
    "email_investment_updates",
    "email_returns",
    "email_security_alerts",
    "email_new_properties",
)
TICKET_CATEGORIES = (
    "payments",
    "withdrawals",
    "kyc",
    "investment",
    "installments",
    "secondary_market",
    "liquidity",
    "account",
    "listing",
    "other",
)
PRIORITIES = ("normal", "high")


class ProposeActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal[
        "resend_verification_email",
        "mark_all_notifications_read",
        "create_support_ticket",
        "cancel_secondary_listing",
        "cancel_liquidity_exit_request",
        "cancel_scheduled_gift",
        "update_notification_preferences",
    ]
    # ticket params: enums + ids only, never free text (the handoff summary is built server-side)
    category: str | None = Field(default=None, description="Ticket category (enum)")
    priority: str | None = Field(default=None, description="normal | high")
    payment_id: str | None = None
    investment_id: str | None = None
    listing_id: str | None = Field(
        default=None, description="Secondary listing id (cancel_secondary_listing / ticket ref)"
    )
    plan_id: str | None = None
    withdrawal_id: str | None = None
    request_id: str | None = Field(
        default=None, description="Liquidity exit request id (cancel_liquidity_exit_request)"
    )
    gift_id: str | None = Field(
        default=None, description="Scheduled gift id (cancel_scheduled_gift)"
    )
    # update_notification_preferences: only the keys given change; null = leave as is
    email_investment_updates: bool | None = None
    email_returns: bool | None = None
    email_security_alerts: bool | None = None
    email_new_properties: bool | None = None


class ProposeActionOut(ToolOutput):
    proposal_id: str
    action: str
    summary: str
    status: str


def _uuid_or_none(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise AppError("INVALID_INPUT", f"{field} is not a valid id.", status_code=422) from exc


async def _propose_action(session: AsyncSession, ctx: AgentContext, args) -> dict:
    a: ProposeActionIn = args
    params: dict = {}
    if a.action == "create_support_ticket":
        category = a.category or "other"
        if category not in TICKET_CATEGORIES:
            raise AppError(
                "INVALID_INPUT",
                f"category must be one of {', '.join(TICKET_CATEGORIES)}.",
                status_code=422,
            )
        priority = a.priority or "normal"
        if priority not in PRIORITIES:
            raise AppError("INVALID_INPUT", "priority must be normal or high.", status_code=422)
        refs = {
            k: _uuid_or_none(getattr(a, k), k)
            for k in ("payment_id", "investment_id", "listing_id", "plan_id", "withdrawal_id")
        }
        params = {
            "category": category,
            "priority": priority,
            "refs": {k: v for k, v in refs.items() if v},
        }
        summary = f"Open a {priority} priority support ticket about {category.replace('_', ' ')}."
    elif a.action == "resend_verification_email":
        if ctx.email_verified:
            raise AppError(
                "ALREADY_DONE", "The email address is already verified.", status_code=409
            )
        summary = ACTIONS[a.action]
    elif a.action == "cancel_secondary_listing":
        listing_id = _uuid_or_none(a.listing_id, "listing_id")
        if not listing_id:
            raise AppError("INVALID_INPUT", "listing_id is required.", status_code=422)
        mine = await secondary_service.list_my_listings(session, ctx.user_id)
        row = next((x for x in mine if str(x.get("id") or x.get("listing_id")) == listing_id), None)
        if row is None or str(row.get("status")) != "active":
            raise AppError("NOT_FOUND", "No active listing of yours with that id.", status_code=404)
        params = {"listing_id": listing_id}
        summary = (
            f"Cancel your secondary-market listing of {row.get('units')} unit(s) of "
            f"{row.get('property_title') or 'the property'}."
        )
    elif a.action == "cancel_liquidity_exit_request":
        request_id = _uuid_or_none(a.request_id, "request_id")
        if not request_id:
            raise AppError("INVALID_INPUT", "request_id is required.", status_code=422)
        mine = await liquidity_service.list_my_exit_requests(session, ctx.user_id)
        row = next((x for x in mine if str(x.get("request_id")) == request_id), None)
        if row is None or str(row.get("status")) != "open":
            raise AppError(
                "NOT_FOUND", "No open exit request of yours with that id.", status_code=404
            )
        params = {"request_id": request_id}
        summary = (
            f"Cancel your open liquidity exit request for {row.get('units_remaining')} unit(s) "
            f"of {row.get('property_title') or 'the property'}."
        )
    elif a.action == "cancel_scheduled_gift":
        gift_id = _uuid_or_none(a.gift_id, "gift_id")
        if not gift_id:
            raise AppError("INVALID_INPUT", "gift_id is required.", status_code=422)
        gifts = await gift_service.list_gifts(session, ctx.user_id)
        gift = next((g for g in gifts if str(g.id) == gift_id), None)
        if gift is None or str(gift.status) not in ("scheduled", "pending", "active"):
            raise AppError(
                "NOT_FOUND", "No cancellable gift of yours with that id.", status_code=404
            )
        params = {"gift_id": gift_id}
        summary = f"Cancel the scheduled gift to {gift.recipient_name or 'the recipient'}."
    elif a.action == "update_notification_preferences":
        changes = {k: getattr(a, k) for k in PREF_KEYS if getattr(a, k) is not None}
        if not changes:
            raise AppError("INVALID_INPUT", "Say which preference to change.", status_code=422)
        params = {"preferences": changes}
        summary = "Change email notifications: " + ", ".join(
            f"{k.replace('email_', '').replace('_', ' ')} {'on' if v else 'off'}"
            for k, v in changes.items()
        )
    else:
        summary = ACTIONS[a.action]
    proposal, _token = await guard.issue_confirmation(
        session, ctx=ctx, action=a.action, params=params, summary=summary
    )
    # the token is NOT returned here: the agent attaches it to the user's card only
    return {
        "proposal_id": str(proposal.id),
        "action": a.action,
        "summary": summary,
        "status": "awaiting_user_confirmation",
    }


register(
    ToolSpec(
        "propose_action",
        "Propose an action for the user to confirm with a button: resend the verification "
        "email, mark all notifications read, or open a support ticket (category from the "
        "list, optional reference ids). Nothing happens until the user confirms.",
        ProposeActionIn,
        ProposeActionOut,
        "confirmed_action",
        _propose_action,
    )
)


class KnowledgeGapIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(description="One of: " + ", ".join(TICKET_CATEGORIES))


class KnowledgeGapOut(ToolOutput):
    recorded: bool
    ticket_no: str | None


async def _report_knowledge_gap(session: AsyncSession, ctx: AgentContext, args) -> dict:
    """The question itself stays in the encrypted conversation; the ticket holds the category
    and a link to the conversation only."""
    a: KnowledgeGapIn = args
    category = a.category if a.category in TICKET_CATEGORIES else "other"
    ticket = SupportTicket(
        kind="knowledge_gap",
        user_id=ctx.user_id,
        conversation_id=ctx.conversation_id,
        category=category,
        priority="normal",
        subject=f"Assistant could not answer a {category.replace('_', ' ')} question",
        summary="The assistant lacked approved knowledge. Read the conversation transcript "
        "in the admin panel; no message text is copied here.",
        context={
            "conversation_id": str(ctx.conversation_id) if ctx.conversation_id else None,
            "transcript_url": f"/admin/assistant-conversation/details/{ctx.conversation_id}"
            if ctx.conversation_id
            else None,
            "lang": ctx.lang,
        },
        source="assistant",
    )
    session.add(ticket)
    await session.flush()
    await session.refresh(ticket)
    return {"recorded": True, "ticket_no": ticket.ticket_no}


register(
    ToolSpec(
        "report_knowledge_gap",
        "Call this when the approved knowledge base and the tools cannot answer the question. "
        "It records the gap for the team; then tell the user you will pass it on and offer "
        "the support link.",
        KnowledgeGapIn,
        KnowledgeGapOut,
        "informational",
        _report_knowledge_gap,
    )
)
