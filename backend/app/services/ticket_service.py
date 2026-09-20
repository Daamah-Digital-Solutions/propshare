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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    AssistantActionProposal,
    AssistantConversation,
    AssistantMessage,
    AuditLog,
    EmailOutbox,
    KycVerification,
    SupportTicket,
    SupportTicketMessage,
    User,
    UserRole,
)
from app.services import auth_service, notification_service, settings_service

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
    await _flag_duplicate(session, ticket)
    session.add(ticket)
    await session.flush()
    await session.refresh(ticket)
    conv = await session.get(AssistantConversation, ticket.conversation_id)
    if conv is not None and conv.ticket_id is None:
        conv.ticket_id = ticket.id
    await _queue_support_email(
        session,
        ticket,
        f"New ticket {ticket.ticket_no} from the assistant.{_dup_note(ticket)}\n\n{ticket.summary}",
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
    await _flag_duplicate(session, ticket)
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
        f"New ticket {ticket.ticket_no} from the support form.{_dup_note(ticket)}\n\n"
        f"Category: {category}\nSubject: {subject}\n\n{body}",
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


# --------------------------------------------------------------------------- #
# Batch C: duplicates, SLA / escalation, CSAT, daily digest
# --------------------------------------------------------------------------- #
DUPLICATE_WINDOW_HOURS = 24


async def _flag_duplicate(session: AsyncSession, ticket: SupportTicket) -> None:
    """A second ticket from the same person in the same category within 24h is very likely
    the same problem: link it (never block it) so staff answer once."""
    if ticket.user_id is None and not ticket.contact_email:
        return
    since = dt.datetime.now(dt.UTC) - dt.timedelta(hours=DUPLICATE_WINDOW_HOURS)
    stmt = (
        select(SupportTicket)
        .where(
            SupportTicket.kind == "support",
            SupportTicket.category == ticket.category,
            SupportTicket.status.in_(("open", "in_progress", "waiting_user")),
            SupportTicket.created_at >= since,
        )
        .order_by(SupportTicket.created_at.desc())
        .limit(1)
    )
    if ticket.user_id is not None:
        stmt = stmt.where(SupportTicket.user_id == ticket.user_id)
    else:
        stmt = stmt.where(SupportTicket.contact_email == ticket.contact_email)
    earlier = (await session.execute(stmt)).scalar_one_or_none()
    if earlier is not None:
        ticket.context = {**(ticket.context or {}), "possible_duplicate_of": earlier.ticket_no}


def _dup_note(ticket: SupportTicket) -> str:
    dup = (ticket.context or {}).get("possible_duplicate_of")
    return f" POSSIBLE DUPLICATE of {dup}." if dup else ""


async def sla_hours(session: AsyncSession, priority: str) -> int:
    key = "support_sla_hours_high" if priority == "high" else "support_sla_hours_normal"
    return int(await settings_service.get_setting(session, key) or 24)


async def _first_staff_reply_ids(session: AsyncSession) -> set[uuid.UUID]:
    rows = await session.execute(
        select(SupportTicketMessage.ticket_id)
        .where(
            SupportTicketMessage.author_type == "staff",
            SupportTicketMessage.internal.is_(False),
        )
        .distinct()
    )
    return {r[0] for r in rows.all()}


async def overdue_tickets(
    session: AsyncSession, *, now: dt.datetime | None = None
) -> list[SupportTicket]:
    """Open tickets without any public staff reply past their SLA (by priority)."""
    now = now or dt.datetime.now(dt.UTC)
    answered = await _first_staff_reply_ids(session)
    rows = (
        (
            await session.execute(
                select(SupportTicket)
                .where(
                    SupportTicket.kind == "support",
                    SupportTicket.status.in_(("open", "in_progress")),
                )
                .order_by(SupportTicket.created_at)
            )
        )
        .scalars()
        .all()
    )
    out = []
    for t in rows:
        if t.id in answered:
            continue
        limit = await sla_hours(session, t.priority)
        if t.created_at <= now - dt.timedelta(hours=limit):
            out.append(t)
    return out


async def escalate_overdue(session: AsyncSession, *, now: dt.datetime | None = None) -> dict:
    """SLA sweep (cron): every overdue ticket is escalated ONCE — priority raised to high,
    the breach recorded on the ticket, every admin notified in-app and the support inbox
    emailed a single list. Re-running is safe (already-escalated tickets are skipped)."""
    now = now or dt.datetime.now(dt.UTC)
    overdue = [
        t
        for t in await overdue_tickets(session, now=now)
        if not (t.context or {}).get("sla_breached_at")
    ]
    if not overdue:
        return {"escalated": 0, "overdue": 0}
    admins = [
        r[0]
        for r in (
            await session.execute(select(UserRole.user_id).where(UserRole.role == "admin"))
        ).all()
    ]
    lines = []
    for t in overdue:
        before = t.priority
        t.priority = "high"
        t.context = {
            **(t.context or {}),
            "sla_breached_at": now.isoformat(),
            "priority_before_sla": before,
        }
        t.updated_at = now
        age_h = round((now - t.created_at).total_seconds() / 3600, 1)
        lines.append(f"{t.ticket_no} · {t.category} · {age_h}h without a reply")
        await write_audit(
            session,
            action="ticket.sla_breached",
            entity_type="support_ticket",
            entity_id=str(t.id),
            actor_id=None,
            before={"priority": before},
            after={"priority": "high", "age_hours": age_h},
        )
    for admin_id in admins:
        await notification_service.notify(
            session,
            user_id=admin_id,
            type="ticket_sla",
            title=f"{len(overdue)} support ticket(s) past SLA",
            message="\n".join(lines[:10]),
        )
    inbox = get_settings().support_inbox_email
    if inbox:
        session.add(
            EmailOutbox(
                user_id=None,
                to_email=inbox,
                subject=f"[SLA] {len(overdue)} ticket(s) past their first-response time",
                body="These tickets have no public staff reply past their SLA and were raised "
                "to high priority:\n\n" + "\n".join(lines),
                category="support",
                status="pending",
            )
        )
    await session.flush()
    return {"escalated": len(overdue), "overdue": len(overdue)}


async def rate_ticket(
    session: AsyncSession, *, user_id: uuid.UUID, ticket_id: uuid.UUID, score: int
) -> SupportTicket:
    """CSAT: the owner rates a resolved/closed ticket 1..5 (a second call updates)."""
    ticket = await get_my_ticket(session, user_id=user_id, ticket_id=ticket_id)
    if ticket.status not in ("resolved", "closed"):
        raise AppError(
            "TICKET_NOT_RESOLVED", "You can rate a ticket once it is resolved.", status_code=409
        )
    if not 1 <= int(score) <= 5:
        raise AppError("INVALID_INPUT", "score must be 1..5.", status_code=422)
    ticket.csat = int(score)
    ticket.updated_at = dt.datetime.now(dt.UTC)
    await session.flush()
    return ticket


async def daily_digest(session: AsyncSession, *, now: dt.datetime | None = None) -> dict[str, Any]:
    """Numbers for the team's daily email (client doc §29): tickets in/out, backlog by
    category and age, SLA breaches, knowledge gaps, CSAT, assistant load and safe-mode rate.
    Counts only — no ticket bodies, no conversation text."""
    now = now or dt.datetime.now(dt.UTC)
    day_ago = now - dt.timedelta(hours=24)

    async def count(stmt) -> int:
        return int(await session.scalar(stmt) or 0)

    open_states = ("open", "in_progress", "waiting_user")
    open_by_cat = (
        await session.execute(
            select(SupportTicket.category, func.count())
            .where(SupportTicket.kind == "support", SupportTicket.status.in_(open_states))
            .group_by(SupportTicket.category)
        )
    ).all()
    oldest_open = await session.scalar(
        select(func.min(SupportTicket.created_at)).where(
            SupportTicket.kind == "support", SupportTicket.status.in_(("open", "in_progress"))
        )
    )
    csat = await session.scalar(
        select(func.avg(SupportTicket.csat)).where(
            SupportTicket.csat.is_not(None), SupportTicket.updated_at >= day_ago
        )
    )
    overdue = await overdue_tickets(session, now=now)
    return {
        "as_of": now.isoformat(),
        "tickets_new_24h": await count(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.kind == "support", SupportTicket.created_at >= day_ago)
        ),
        "tickets_resolved_24h": await count(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.kind == "support", SupportTicket.resolved_at >= day_ago)
        ),
        "tickets_open": sum(int(c) for _cat, c in open_by_cat),
        "open_by_category": {str(cat): int(c) for cat, c in open_by_cat},
        "oldest_open_hours": (
            round((now - oldest_open).total_seconds() / 3600, 1) if oldest_open else 0
        ),
        "sla_overdue_now": len(overdue),
        "sla_breaches_24h": await count(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "ticket.sla_breached", AuditLog.created_at >= day_ago)
        ),
        "knowledge_gaps_open": await count(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.kind == "knowledge_gap", SupportTicket.status == "open")
        ),
        "csat_avg_24h": round(float(csat), 2) if csat is not None else None,
        "assistant_conversations_24h": await count(
            select(func.count())
            .select_from(AssistantConversation)
            .where(AssistantConversation.created_at >= day_ago)
        ),
        "assistant_safe_mode_24h": await count(
            select(func.count())
            .select_from(AssistantMessage)
            .where(
                AssistantMessage.role == "assistant",
                AssistantMessage.confidence == "safe_mode",
                AssistantMessage.created_at >= day_ago,
            )
        ),
        "assistant_low_confidence_24h": await count(
            select(func.count())
            .select_from(AssistantMessage)
            .where(
                AssistantMessage.role == "assistant",
                AssistantMessage.confidence == "low",
                AssistantMessage.created_at >= day_ago,
            )
        ),
    }


def render_digest(d: dict[str, Any]) -> str:
    cats = ", ".join(f"{k}: {v}" for k, v in sorted(d["open_by_category"].items())) or "none"
    csat = d["csat_avg_24h"] if d["csat_avg_24h"] is not None else "no ratings"
    return (
        f"Capimax PropShare - support & assistant digest ({d['as_of'][:16]} UTC)\n\n"
        f"Tickets: {d['tickets_new_24h']} new, {d['tickets_resolved_24h']} resolved in the last "
        f"24h; {d['tickets_open']} open ({cats}); oldest open {d['oldest_open_hours']}h.\n"
        f"SLA: {d['sla_overdue_now']} overdue now, {d['sla_breaches_24h']} escalated in the "
        f"last 24h.\nKnowledge gaps open: {d['knowledge_gaps_open']}.\nCSAT (24h): {csat}.\n"
        f"Assistant: {d['assistant_conversations_24h']} conversations, "
        f"{d['assistant_safe_mode_24h']} safe-mode answers, "
        f"{d['assistant_low_confidence_24h']} low-confidence answers.\n\n"
        f"Queues: /admin/support-ticket/list - /admin/assistant-status"
    )


async def send_daily_digest(
    session: AsyncSession, *, now: dt.datetime | None = None
) -> dict[str, Any]:
    """Cron (once a day): compute the digest and queue it to the support inbox."""
    d = await daily_digest(session, now=now)
    inbox = get_settings().support_inbox_email
    if inbox:
        session.add(
            EmailOutbox(
                user_id=None,
                to_email=inbox,
                subject=(
                    f"[Digest] {d['tickets_open']} open tickets - {d['sla_overdue_now']} past "
                    f"SLA - {d['assistant_conversations_24h']} conversations"
                ),
                body=render_digest(d),
                category="support",
                status="pending",
            )
        )
        await session.flush()
    return d
