"""Support tickets and the structured handoff (plan §4, rev 3).

A ticket created from an assistant conversation carries a ``HandoffSummary``: category,
reference ids, attempted actions, tool names, account facts, and a LINK to the encrypted
transcript. It never carries a message body, a quoted sentence or a title derived from the
chat. Staff who need the words open the admin transcript view, which decrypts on demand
and writes ``assistant.transcript_viewed`` to the audit log.

The support inbox email is queued through the existing email outbox (sent by the cron
drainer, never inline) and contains the same structured summary plus the admin link.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    AssistantActionProposal,
    AssistantConversation,
    AssistantMessage,
    EmailOutbox,
    KycVerification,
    SupportTicket,
    SupportTicketMessage,
    User,
)
from app.services import auth_service, notification_service

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
STATUSES = ("open", "in_progress", "waiting_user", "resolved", "closed")
REF_KEYS = ("payment_id", "investment_id", "listing_id", "plan_id", "withdrawal_id")
MAX_BODY = 4000


def transcript_url(conversation_id: uuid.UUID) -> str:
    return f"/admin/assistant-conversation/details/{conversation_id}"


# --------------------------------------------------------------------------- #
# Handoff summary: typed, structured, no chat text
# --------------------------------------------------------------------------- #
@dataclasses.dataclass(frozen=True)
class HandoffSummary:
    category: str
    priority: str
    refs: dict[str, str]
    attempted_actions: list[dict[str, str]]
    tool_calls_made: list[str]
    kyc_status: str
    roles: list[str]
    active_role: str | None
    email_verified: bool
    lang: str
    conversation_id: str
    transcript_url: str
    turns: int

    def render(self) -> str:
        """Fixed template, labels + values only. Nothing here came from the chat text."""
        refs = ", ".join(f"{k}={v}" for k, v in sorted(self.refs.items())) or "none"
        actions = (
            "; ".join(f"{a['action']} ({a['status']}, {a['at']})" for a in self.attempted_actions)
            or "none"
        )
        tools = ", ".join(self.tool_calls_made) or "none"
        return (
            f"Category: {self.category}\n"
            f"Priority: {self.priority}\n"
            f"References: {refs}\n"
            f"Attempted actions: {actions}\n"
            f"Tools used in the conversation: {tools}\n"
            f"KYC status: {self.kyc_status}\n"
            f"Roles: {', '.join(self.roles) or 'investor'}"
            f" (active: {self.active_role or 'investor'})\n"
            f"Email verified: {'yes' if self.email_verified else 'no'}\n"
            f"Language: {self.lang}\n"
            f"Conversation turns: {self.turns}\n"
            f"Transcript (admin panel, audited): {self.transcript_url}"
        )

    def as_context(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


async def build_handoff_summary(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    category: str,
    priority: str,
    refs: dict[str, str] | None = None,
) -> HandoffSummary:
    conv = await session.get(AssistantConversation, conversation_id)
    if conv is None:
        raise AppError("NOT_FOUND", "Conversation not found.", status_code=404)
    messages = (
        (
            await session.execute(
                select(AssistantMessage)
                .where(AssistantMessage.conversation_id == conversation_id)
                .order_by(AssistantMessage.created_at)
            )
        )
        .scalars()
        .all()
    )
    # tool NAMES only (never arguments, never outputs)
    tools: list[str] = []
    for m in messages:
        if m.role == "assistant" and isinstance(m.tool_calls, list):
            for call in m.tool_calls:
                if isinstance(call, dict) and call.get("name") and call["name"] not in tools:
                    tools.append(str(call["name"]))
    proposals = (
        (
            await session.execute(
                select(AssistantActionProposal)
                .where(AssistantActionProposal.conversation_id == conversation_id)
                .order_by(AssistantActionProposal.created_at)
            )
        )
        .scalars()
        .all()
    )
    attempted = [
        {"action": p.action, "status": p.status, "at": p.created_at.strftime("%Y-%m-%d %H:%M")}
        for p in proposals
    ]
    kyc_status, roles, active_role, email_verified = "none", [], None, False
    if conv.user_id is not None:
        user = await session.get(User, conv.user_id)
        if user is not None:
            roles = list(await auth_service.get_roles(session, user.id))
            active_role = str(user.active_role) if user.active_role is not None else None
            email_verified = bool(user.email_verified)
            kyc_status = str(
                await session.scalar(
                    select(KycVerification.status).where(KycVerification.user_id == user.id)
                )
                or "pending"
            )
    clean_refs = {}
    for k, v in (refs or {}).items():
        if k in REF_KEYS and v:
            clean_refs[k] = str(uuid.UUID(str(v)))  # ids only; anything else is rejected
    return HandoffSummary(
        category=category if category in TICKET_CATEGORIES else "other",
        priority=priority if priority in PRIORITIES else "normal",
        refs=clean_refs,
        attempted_actions=attempted,
        tool_calls_made=tools,
        kyc_status=kyc_status,
        roles=roles,
        active_role=active_role,
        email_verified=email_verified,
        lang=conv.lang,
        conversation_id=str(conv.id),
        transcript_url=transcript_url(conv.id),
        turns=sum(1 for m in messages if m.role == "user"),
    )


# --------------------------------------------------------------------------- #
# Creating tickets
# --------------------------------------------------------------------------- #
def _subject_for(category: str) -> str:
    return f"Support request: {category.replace('_', ' ')}"


async def _queue_support_email(
    session: AsyncSession, ticket: SupportTicket, body: str
) -> EmailOutbox | None:
    inbox = get_settings().support_inbox_email
    if not inbox:
        return None
    row = EmailOutbox(
        user_id=None,
        to_email=inbox,
        subject=f"[{ticket.ticket_no}] {ticket.subject or 'Support ticket'} ({ticket.priority})",
        body=body,
        category="support",
        status="pending",
    )
    session.add(row)
    return row


async def create_from_handoff(
    session: AsyncSession, *, user_id: uuid.UUID | None, handoff: HandoffSummary
) -> SupportTicket:
    """The assistant's confirmed ``create_support_ticket``: structured summary only."""
    ticket = SupportTicket(
        kind="support",
        user_id=user_id,
        conversation_id=uuid.UUID(handoff.conversation_id),
        category=handoff.category,
        priority=handoff.priority,
        subject=_subject_for(handoff.category),
        summary=handoff.render(),
        context=handoff.as_context(),
        source="assistant",
    )
    session.add(ticket)
    await session.flush()
    await session.refresh(ticket)
    conv = await session.get(AssistantConversation, ticket.conversation_id)
    if conv is not None and conv.ticket_id is None:
        conv.ticket_id = ticket.id
    await _queue_support_email(
        session, ticket, f"New ticket {ticket.ticket_no} from the assistant.\n\n{ticket.summary}"
    )
    if user_id is not None:
        await notification_service.notify(
            session,
            user_id=user_id,
            type="support_ticket",
            title=f"Ticket {ticket.ticket_no} opened",
            message="A member of the team will follow up on your request.",
        )
    await write_audit(
        session,
        action="ticket.created",
        entity_type="support_ticket",
        entity_id=str(ticket.id),
        actor_id=user_id,
        after={"ticket_no": ticket.ticket_no, "source": "assistant", "category": ticket.category},
    )
    return ticket


async def create_from_form(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    contact_email: str | None,
    category: str,
    subject: str,
    body: str,
    priority: str = "normal",
) -> SupportTicket:
    """The LLM-free support form (also the fallback when the assistant is off)."""
    if category not in TICKET_CATEGORIES:
        raise AppError("INVALID_INPUT", "Unknown category.", status_code=422)
    if priority not in PRIORITIES:
        raise AppError("INVALID_INPUT", "Unknown priority.", status_code=422)
    subject, body = subject.strip()[:200], body.strip()[:MAX_BODY]
    if not subject or not body:
        raise AppError("INVALID_INPUT", "Subject and message are required.", status_code=422)
    if user_id is None and not contact_email:
        raise AppError("INVALID_INPUT", "An email address is required.", status_code=422)
    ticket = SupportTicket(
        kind="support",
        user_id=user_id,
        contact_email=None if user_id else contact_email,
        category=category,
        priority=priority,
        subject=subject,
        summary=None,
        context={},
        source="form",
    )
    session.add(ticket)
    await session.flush()
    await session.refresh(ticket)
    session.add(
        SupportTicketMessage(
            ticket_id=ticket.id, author_type="user", author_id=user_id, body=body, internal=False
        )
    )
    await _queue_support_email(
        session,
        ticket,
        f"New ticket {ticket.ticket_no} from the support form.\n\nCategory: {category}\n"
        f"Subject: {subject}\n\n{body}",
    )
    await write_audit(
        session,
        action="ticket.created",
        entity_type="support_ticket",
        entity_id=str(ticket.id),
        actor_id=user_id,
        after={"ticket_no": ticket.ticket_no, "source": "form", "category": category},
    )
    return ticket


# --------------------------------------------------------------------------- #
# Reading / replying (ticket owner)
# --------------------------------------------------------------------------- #
async def get_my_ticket(
    session: AsyncSession, *, user_id: uuid.UUID, ticket_id: uuid.UUID
) -> SupportTicket:
    ticket = await session.get(SupportTicket, ticket_id)
    if ticket is None or ticket.user_id != user_id or ticket.kind != "support":
        raise AppError("NOT_FOUND", "Ticket not found.", status_code=404)
    return ticket


async def list_my_tickets(
    session: AsyncSession, *, user_id: uuid.UUID, limit: int = 50
) -> list[SupportTicket]:
    stmt = (
        select(SupportTicket)
        .where(SupportTicket.user_id == user_id, SupportTicket.kind == "support")
        .order_by(SupportTicket.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_messages(
    session: AsyncSession, *, ticket_id: uuid.UUID, include_internal: bool
) -> list[SupportTicketMessage]:
    stmt = (
        select(SupportTicketMessage)
        .where(SupportTicketMessage.ticket_id == ticket_id)
        .order_by(SupportTicketMessage.created_at)
    )
    if not include_internal:
        stmt = stmt.where(SupportTicketMessage.internal.is_(False))
    return list((await session.execute(stmt)).scalars().all())


async def user_reply(
    session: AsyncSession, *, user_id: uuid.UUID, ticket_id: uuid.UUID, body: str
) -> SupportTicketMessage:
    ticket = await get_my_ticket(session, user_id=user_id, ticket_id=ticket_id)
    if ticket.status == "closed":
        raise AppError("TICKET_CLOSED", "This ticket is closed.", status_code=409)
    body = body.strip()[:MAX_BODY]
    if not body:
        raise AppError("INVALID_INPUT", "A message is required.", status_code=422)
    msg = SupportTicketMessage(
        ticket_id=ticket.id, author_type="user", author_id=user_id, body=body, internal=False
    )
    session.add(msg)
    ticket.status = "open" if ticket.status in ("waiting_user", "resolved") else ticket.status
    ticket.updated_at = dt.datetime.now(dt.UTC)
    await session.flush()
    return msg


# --------------------------------------------------------------------------- #
# Staff side (admin panel)
# --------------------------------------------------------------------------- #
async def staff_reply(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    ticket_id: uuid.UUID,
    body: str,
    internal: bool = False,
    new_status: str | None = None,
) -> SupportTicketMessage:
    ticket = await session.get(SupportTicket, ticket_id)
    if ticket is None:
        raise AppError("NOT_FOUND", "Ticket not found.", status_code=404)
    body = body.strip()[:MAX_BODY]
    if not body:
        raise AppError("INVALID_INPUT", "A message is required.", status_code=422)
    msg = SupportTicketMessage(
        ticket_id=ticket.id,
        author_type="staff",
        author_id=actor_id,
        body=body,
        internal=internal,
    )
    session.add(msg)
    now = dt.datetime.now(dt.UTC)
    if new_status:
        await set_status(session, actor_id=actor_id, ticket_id=ticket_id, status=new_status)
    elif not internal and ticket.status in ("open", "in_progress"):
        ticket.status = "waiting_user"
    ticket.updated_at = now
    if not internal and ticket.user_id is not None:
        await notification_service.notify(
            session,
            user_id=ticket.user_id,
            type="support_ticket",
            title=f"Reply on ticket {ticket.ticket_no}",
            message="Support replied to your ticket. Open it to read the answer.",
            email_category="security",
            email_subject=f"[{ticket.ticket_no}] Support replied",
            email_body=f"Support replied to your ticket {ticket.ticket_no}:\n\n{body}",
        )
    await write_audit(
        session,
        action="ticket.replied",
        entity_type="support_ticket",
        entity_id=str(ticket.id),
        actor_id=actor_id,
        after={"internal": internal, "status": ticket.status},
    )
    await session.flush()
    return msg


async def set_status(
    session: AsyncSession, *, actor_id: uuid.UUID | None, ticket_id: uuid.UUID, status: str
) -> SupportTicket:
    if status not in STATUSES:
        raise AppError("INVALID_INPUT", "Unknown status.", status_code=422)
    ticket = await session.get(SupportTicket, ticket_id)
    if ticket is None:
        raise AppError("NOT_FOUND", "Ticket not found.", status_code=404)
    before = ticket.status
    ticket.status = status
    now = dt.datetime.now(dt.UTC)
    ticket.updated_at = now
    if status in ("resolved", "closed") and ticket.resolved_at is None:
        ticket.resolved_at = now
    await write_audit(
        session,
        action="ticket.status_changed",
        entity_type="support_ticket",
        entity_id=str(ticket.id),
        actor_id=actor_id,
        before={"status": before},
        after={"status": status},
    )
    await session.flush()
    return ticket
