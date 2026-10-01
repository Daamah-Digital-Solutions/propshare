"""Proposals and knowledge gaps (plan §4).

``propose_action`` never executes anything: it records a proposal with a one-time token that
only the user's browser receives (as a card), and the confirmation is a separate authenticated
HTTP call that runs the executor. The tool's own output deliberately omits the token, so the
model can neither see nor replay it.
"""

from __future__ import annotations

import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.phone import normalise_phone
from app.models import SupportTicket
from app.models.identity import User
from app.services import (
    auth_service,
    email_change_service,
    gift_service,
    liquidity_service,
    secondary_service,
)
from app.services.assistant import guard
from app.services.assistant.context import AgentContext
from app.services.assistant.tools.base import ToolOutput, ToolSpec, register

ACTIONS: dict[str, str] = {
    "resend_verification_email": "Send the email-verification link again.",
    "mark_all_notifications_read": "Mark all notifications as read.",
    "create_support_ticket": "Open a customer service ticket that a person answers.",
    "cancel_secondary_listing": "Cancel one of your active secondary-market listings.",
    "cancel_liquidity_exit_request": "Cancel one of your open liquidity exit requests.",
    "cancel_scheduled_gift": "Cancel one of your scheduled gifts.",
    "update_notification_preferences": "Change which email notifications you receive.",
    "update_phone": "Change the phone number on your account.",
    "change_email": "Change the email address you sign in with (approved from your inbox).",
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
        "update_phone",
        "change_email",
    ]
    # ticket: the category and references, plus the problem as the user told it in this chat
    # (the user reads both on the confirmation card before anything is sent)
    category: str | None = Field(default=None, description="Ticket category (enum)")
    priority: str | None = Field(default=None, description="normal | high")
    subject: str | None = Field(
        default=None,
        max_length=120,
        description="create_support_ticket: a short title of the problem, in the user's words",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="create_support_ticket: what happened and what the user needs, from this "
        "chat, with the facts you know (amounts, dates, property, references). Never include "
        "passwords, card numbers or codes.",
    )
    phone: str | None = Field(
        default=None,
        max_length=40,
        description="update_phone: the new number exactly as the user gave it, with country code",
    )
    new_email: str | None = Field(
        default=None, max_length=320, description="change_email: the new address the user gave"
    )
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
    # what the confirmation card shows under the summary, as [label, value] rows
    details: list[list[str]] = []
    status: str


# long digit runs (a card or account number) never reach a ticket
_NUMBER_RUN = re.compile(r"(?:\d[ \-]?){12,}\d")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def scrub(text: str | None, limit: int) -> str:
    """Free text the model wrote for a ticket: control characters out, card-like numbers
    masked, length capped."""
    clean = _CONTROL.sub("", text or "").strip()
    return _NUMBER_RUN.sub("[number removed]", clean)[:limit]


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
    details: list[list[str]] = []
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
        subject = scrub(" ".join((a.subject or "").split()), 120)  # one line: an email header
        description = scrub(a.description, 2000)
        if not description:
            raise AppError(
                "INVALID_INPUT",
                "description is required: write what happened and what the user needs, from "
                "this chat, so the team does not have to ask again. If you do not know the "
                "problem yet, ask the user first.",
                status_code=422,
            )
        params = {
            "category": category,
            "priority": priority,
            "refs": {k: v for k, v in refs.items() if v},
            "subject": subject,
            "description": description,
        }
        label = category.replace("_", " ")
        urgent = ", high priority" if priority == "high" else ""
        summary = f"Open a customer service ticket ({label}{urgent})."
        details = [
            ["Subject", subject or f"Support request: {label}"],
            ["What happened", description],
        ]
    elif a.action == "update_phone":
        phone = normalise_phone(a.phone or "")
        user = await session.get(User, ctx.user_id)
        if user is not None and (user.phone or "") == phone:
            raise AppError(
                "ALREADY_DONE", "That is already the phone number on the account.", status_code=409
            )
        params = {"phone": phone}
        summary = "Change the phone number on your account."
        details = [["New phone number", phone]]
    elif a.action == "change_email":
        new_email = email_change_service.normalise(a.new_email or "")
        user = await session.get(User, ctx.user_id)
        if user is not None and user.email.lower() == new_email.lower():
            raise AppError(
                "SAME_EMAIL", "That is already the email address of the account.", status_code=409
            )
        if await auth_service.get_user_by_email(session, new_email) is not None:
            raise AppError(
                "EMAIL_EXISTS",
                "That email address is already used by another account.",
                status_code=409,
            )
        params = {"new_email": new_email}
        summary = "Change the email address you sign in with."
        details = [
            ["New email", new_email],
            [
                "How it works",
                "We email an approval link to your current address. Once you approve, we send a "
                "confirmation link to the new one, and the change is made when you open it.",
            ],
        ]
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
        "details": details,
        "status": "awaiting_user_confirmation",
    }


register(
    ToolSpec(
        "propose_action",
        "Propose an action for the user to confirm with a button; nothing happens until they "
        "confirm. Actions: open a customer service ticket (category, a subject and a "
        "description of the problem from this chat, optional reference ids); change the "
        "account's phone number (phone); change the sign-in email (new_email: approved from "
        "the current inbox, then confirmed from the new one); resend the verification email; "
        "mark all notifications read; change email notification preferences; cancel a "
        "secondary listing, a liquidity exit request or a scheduled gift.",
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
            "transcript_url": (
                f"/admin/assistant-conversation/details/{ctx.conversation_id}"
                if ctx.conversation_id
                else None
            ),
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
