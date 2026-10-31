"""Messages from the platform team to users (client, 2026-10-28, as on Capimax BRX).

The team writes a message in the admin panel (Messages) to one user, or to everyone holding a
role: investors, property owners and developers (one role here), brokers, liquidity providers,
or everyone. Sending it puts one ``PlatformMessage`` in each recipient's inbox (/messages),
writes them an in-app notification, and queues an email in the outbox (sent by the same
drainer as every other email, outside this transaction).

Emails of a message to a GROUP respect the member's "Announcements" switch in Settings; a
message to one user is always emailed, like any other message about their own account. A
closed account receives nothing. A Send carries a one-time token from the composer: sending
the same form twice (a refresh, a double click) returns the first send and sends nothing more.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import exists, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import AppRole, EmailOutbox, NotificationPreference, User, UserRole
from app.models.messages import MessageBroadcast, MessageTemplate, PlatformMessage
from app.services import notification_service

# audience -> (label, the roles of which a recipient must hold one; None = no role needed)
AUDIENCES: dict[str, tuple[str, tuple[str, ...] | None]] = {
    "user": ("One user", None),
    "investors": ("All investors", ("investor",)),
    "owners": ("All property owners & developers", ("owner",)),
    "brokers": ("All brokers", ("broker",)),
    "liquidity_providers": ("All liquidity providers", ("liquidity_provider",)),
    "staff": ("Platform staff (admins & content editors)", ("admin", "content_editor")),
    "everyone": ("Everyone", None),
}
SUBJECT_MAX = 200
BODY_MAX = 10_000
PREVIEW_LEN = 160
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: object, limit: int) -> str:
    """Typed text: control characters out (new lines kept), Windows line ends folded."""
    return _CONTROL.sub("", str(value or "").replace("\r\n", "\n")).strip()[:limit]


def _preview(body: str) -> str:
    one_line = re.sub(r"\s+", " ", body).strip()
    return one_line if len(one_line) <= PREVIEW_LEN else one_line[: PREVIEW_LEN - 1] + "…"


@dataclass
class Draft:
    audience: str
    subject: str
    body: str
    user: User | None = None


async def _find_user(session: AsyncSession, email: str) -> User | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    return (
        await session.execute(select(User).where(func.lower(User.email) == email))
    ).scalar_one_or_none()


async def check(
    session: AsyncSession, *, audience: str, user_email: str | None, subject: str, body: str
) -> Draft:
    """The composer's input, cleaned, or a message saying what to fix."""
    if audience not in AUDIENCES:
        raise AppError("INVALID_AUDIENCE", "Choose who the message is for.", status_code=422)
    subject = re.sub(r"\s+", " ", clean_text(subject, SUBJECT_MAX + 1))
    body = clean_text(body, BODY_MAX + 1)
    if len(subject) < 3:
        raise AppError(
            "SUBJECT_REQUIRED", "Write a subject (3 characters or more).", status_code=422
        )
    if len(subject) > SUBJECT_MAX:
        raise AppError(
            "SUBJECT_TOO_LONG", f"Keep the subject under {SUBJECT_MAX} characters.", status_code=422
        )
    if not body:
        raise AppError("BODY_REQUIRED", "Write the message.", status_code=422)
    if len(body) > BODY_MAX:
        raise AppError(
            "BODY_TOO_LONG", f"Keep the message under {BODY_MAX:,} characters.", status_code=422
        )
    user = None
    if audience == "user":
        user = await _find_user(session, user_email or "")
        if user is None:
            raise AppError("USER_NOT_FOUND", "No account has that email address.", status_code=404)
        if user.closed_at is not None:
            raise AppError(
                "ACCOUNT_CLOSED", "That account is closed; it gets no messages.", status_code=422
            )
    return Draft(audience=audience, subject=subject, body=body, user=user)


def _recipients_query(draft: Draft):
    q = select(User.id, User.email).where(User.closed_at.is_(None))
    if draft.audience == "user":
        return q.where(User.id == draft.user.id)  # type: ignore[union-attr]
    roles = AUDIENCES[draft.audience][1]
    if roles is not None:
        q = q.where(
            exists().where(
                UserRole.user_id == User.id, UserRole.role.in_([AppRole(r) for r in roles])
            )
        )
    return q.order_by(User.created_at)


async def preview(session: AsyncSession, draft: Draft, *, sample: int = 8) -> dict:
    """Who the message would reach, before it is sent: how many, a few of them, and how many
    of a group turned announcement emails off."""
    rows = (await session.execute(_recipients_query(draft))).all()
    opted_out = 0
    if draft.audience != "user" and rows:
        opted_out = len(await _opted_out(session, [r.id for r in rows]))
    return {
        "count": len(rows),
        "sample": [r.email for r in rows[:sample]],
        "opted_out": opted_out,
    }


async def _opted_out(session: AsyncSession, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    out: set[uuid.UUID] = set()
    for i in range(0, len(user_ids), 5000):
        chunk = user_ids[i : i + 5000]
        out.update(
            (
                await session.execute(
                    select(NotificationPreference.user_id).where(
                        NotificationPreference.user_id.in_(chunk),
                        NotificationPreference.email_announcements.is_(False),
                    )
                )
            ).scalars()
        )
    return out


def email_body(draft: Draft, message_id: uuid.UUID | None) -> str:
    """The email as it goes out; without a message id (the admin's review) the link
    shows where the inbox link goes."""
    base = get_settings().app_base_url.rstrip("/")
    lines = [
        draft.body,
        "",
        "—",
        "Read this message in your Capimax PropShare inbox: "
        + (f"{base}/messages?id={message_id}" if message_id else f"{base}/messages"),
    ]
    if draft.audience != "user":
        lines.append(
            "You receive announcements because you have a Capimax PropShare account. To stop "
            f'these emails, turn off "Announcements" in Settings: {base}/settings'
        )
    return "\n".join(lines)


async def send(
    session: AsyncSession,
    draft: Draft,
    *,
    send_email: bool,
    client_token: str,
    actor_id: uuid.UUID | None,
    template_id: uuid.UUID | None = None,
) -> tuple[MessageBroadcast, bool]:
    """Deliver the message. Returns (the broadcast, True when THIS call sent it); a token
    already used returns the earlier broadcast and False."""
    token = (client_token or "").strip()
    if not 16 <= len(token) <= 100:
        raise AppError("BAD_TOKEN", "Open the composer again and send from there.", status_code=422)
    # one sender per token at a time; the unique index is the last line of defence
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": "message:" + token}
    )
    earlier = (
        await session.execute(
            select(MessageBroadcast).where(MessageBroadcast.client_token == token)
        )
    ).scalar_one_or_none()
    if earlier is not None:
        return earlier, False

    if template_id is not None and await session.get(MessageTemplate, template_id) is None:
        template_id = None
    broadcast = MessageBroadcast(
        id=uuid.uuid4(),
        audience=draft.audience,
        user_id=draft.user.id if draft.user else None,
        subject=draft.subject,
        body=draft.body,
        send_email=send_email,
        template_id=template_id,
        client_token=token,
        created_by=actor_id,
    )
    session.add(broadcast)
    await session.flush()

    rows = (await session.execute(_recipients_query(draft))).all()
    opted_out = (
        await _opted_out(session, [r.id for r in rows])
        if send_email and draft.audience != "user"
        else set()
    )
    preview_text = _preview(draft.body)
    messages: list[PlatformMessage] = []
    queued = 0
    for r in rows:
        message = PlatformMessage(
            id=uuid.uuid4(),
            recipient_id=r.id,
            broadcast_id=broadcast.id,
            subject=draft.subject,
            body=draft.body,
        )
        if not send_email or not r.email:
            message.email_status = "no_email"
        elif r.id in opted_out:
            message.email_status = "opted_out"
        else:
            outbox = EmailOutbox(
                id=uuid.uuid4(),
                user_id=r.id,
                to_email=r.email,
                subject=draft.subject,
                body=email_body(draft, message.id),
                category="announcements" if draft.audience != "user" else "message",
                status="pending",
            )
            session.add(outbox)  # flushed before the inbox rows that point at it
            message.email_status = "queued"
            message.email_outbox_id = outbox.id
            queued += 1
        messages.append(message)
        await notification_service.notify(
            session,
            user_id=r.id,
            type="message",
            title=draft.subject,
            message=preview_text,
        )
    await session.flush()
    session.add_all(messages)
    broadcast.recipients = len(rows)
    broadcast.emails_queued = queued
    await session.flush()
    await write_audit(
        session,
        action="message.sent",
        entity_type="message_broadcast",
        entity_id=str(broadcast.id),
        actor_id=actor_id,
        after={
            "audience": draft.audience,
            "to": draft.user.email if draft.user else AUDIENCES[draft.audience][0],
            "subject": draft.subject,
            "recipients": len(rows),
            "emails": queued,
        },
    )
    return broadcast, True


# --- the admin's records ---------------------------------------------------- #
async def list_broadcasts(session: AsyncSession, *, limit: int = 200) -> list[dict]:
    read = (
        select(func.count())
        .where(
            PlatformMessage.broadcast_id == MessageBroadcast.id,
            PlatformMessage.read_at.is_not(None),
        )
        .scalar_subquery()
    )
    rows = (
        await session.execute(
            select(MessageBroadcast, User.email, read)
            .outerjoin(User, User.id == MessageBroadcast.created_by)
            .order_by(MessageBroadcast.created_at.desc())
            .limit(limit)
        )
    ).all()
    to_ids = [b.user_id for b, _e, _r in rows if b.user_id]
    to_email = {}
    if to_ids:
        to_email = dict(
            (await session.execute(select(User.id, User.email).where(User.id.in_(to_ids)))).all()
        )
    return [
        {
            "b": b,
            "sender": sender,
            "read": n_read,
            "to": to_email.get(b.user_id) if b.audience == "user" else AUDIENCES[b.audience][0],
        }
        for b, sender, n_read in rows
    ]


async def recipient_report(
    session: AsyncSession, broadcast_id: uuid.UUID, *, status: str | None = None
) -> list[dict]:
    """One row per recipient: who, whether they read it, and what happened to the email."""
    q = (
        select(
            PlatformMessage, User.email, User.full_name, EmailOutbox.status, EmailOutbox.last_error
        )
        .join(User, User.id == PlatformMessage.recipient_id)
        .outerjoin(EmailOutbox, EmailOutbox.id == PlatformMessage.email_outbox_id)
        .where(PlatformMessage.broadcast_id == broadcast_id)
        .order_by(User.email)
    )
    out = []
    for m, email, name, outbox_status, error in (await session.execute(q)).all():
        if m.email_status == "queued":
            mail = {"sent": "sent", "failed": "failed"}.get(outbox_status or "", "queued")
        else:
            mail = m.email_status
        row = {
            "email": email,
            "name": name,
            "read_at": m.read_at,
            "mail": mail,
            "error": error if mail == "failed" else None,
        }
        if (
            status in (None, "", mail)
            or (status == "unread" and m.read_at is None)
            or (status == "read" and m.read_at is not None)
        ):
            out.append(row)
    return out


def tally(rows: list[dict]) -> dict:
    t = {"read": 0, "sent": 0, "queued": 0, "failed": 0, "opted_out": 0, "no_email": 0}
    for r in rows:
        t[r["mail"]] = t.get(r["mail"], 0) + 1
        if r["read_at"] is not None:
            t["read"] += 1
    return t


# --- the member's inbox ----------------------------------------------------- #
def _row(m: PlatformMessage, full: bool = False) -> dict:
    out = {
        "id": str(m.id),
        "subject": m.subject,
        "preview": _preview(m.body),
        "read": m.read_at is not None,
        "created_at": m.created_at,
    }
    if full:
        out["body"] = m.body
    return out


async def inbox(session: AsyncSession, user_id: uuid.UUID, *, limit: int = 200) -> dict:
    rows = (
        (
            await session.execute(
                select(PlatformMessage)
                .where(PlatformMessage.recipient_id == user_id)
                .order_by(PlatformMessage.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [_row(m) for m in rows], "unread": await unread_count(session, user_id)}


async def open_message(session: AsyncSession, user_id: uuid.UUID, message_id: uuid.UUID) -> dict:
    """One of the caller's own messages, marked read; anyone else's is not found."""
    m = (
        await session.execute(
            select(PlatformMessage).where(
                PlatformMessage.id == message_id, PlatformMessage.recipient_id == user_id
            )
        )
    ).scalar_one_or_none()
    if m is None:
        raise AppError("MESSAGE_NOT_FOUND", "Message not found.", status_code=404)
    if m.read_at is None:
        m.read_at = func.now()
        await session.flush()
        await session.refresh(m)
    return _row(m, full=True)


async def read_all(session: AsyncSession, user_id: uuid.UUID) -> int:
    result = await session.execute(
        update(PlatformMessage)
        .where(PlatformMessage.recipient_id == user_id, PlatformMessage.read_at.is_(None))
        .values(read_at=func.now())
    )
    return int(result.rowcount or 0)


async def unread_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    n = await session.scalar(
        select(func.count()).where(
            PlatformMessage.recipient_id == user_id, PlatformMessage.read_at.is_(None)
        )
    )
    return int(n or 0)
