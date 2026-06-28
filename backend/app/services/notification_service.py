"""Notifications (in-app feed) + transactional email dispatch (Phase 12).

``notify`` is the single seam every event-producing service calls. It ALWAYS writes the
in-app ``notifications`` row (the feed the bell reads). When the caller marks an event
email-eligible (``email_category=…``), it ALSO writes an ``email_outbox`` row — in the
SAME transaction — but only if the user's email preference for that category is on (or
``force_email`` for invitations to non-users). Email is never *sent* here: a cron drainer
(``email_service.dispatch_pending``) sends outbox rows OUT of any money transaction, so a
slow/failing provider can never stall or roll back a financial transaction.

An event WITHOUT an ``email_category`` can never email — email is opt-in per call site.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmailOutbox, Notification, NotificationPreference, User

# Email category -> the preference column that gates it. "invite" is intentionally absent
# (invitations are unconditional: the recipient is usually not a user and has no prefs).
_CATEGORY_PREF: dict[str, str] = {
    "investment_updates": "email_investment_updates",
    "returns": "email_returns",
    "security": "email_security_alerts",
    "new_properties": "email_new_properties",
}


async def _email_allowed(session: AsyncSession, user_id: uuid.UUID, category: str) -> bool:
    """True if the user's email preference for ``category`` is on. A missing prefs row or
    an unknown category defaults to ON (opt-out model)."""
    col = _CATEGORY_PREF.get(category)
    if col is None:
        return True
    prefs = (
        await session.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        )
    ).scalar_one_or_none()
    if prefs is None:
        return True
    return bool(getattr(prefs, col))


async def notify(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    type: str,
    title: str,
    message: str,
    email_category: str | None = None,
    email_to: str | None = None,
    force_email: bool = False,
    email_subject: str | None = None,
    email_body: str | None = None,
) -> Notification:
    # 1) In-app row — ALWAYS written (the feed). Never gated by email prefs.
    # The id is generated client-side so callers (e.g. Phase-15c fan-out) can link the
    # created notification immediately, with no extra flush. Returning the row is purely
    # additive — every existing caller invokes this as a statement and ignores the result.
    notification = Notification(
        id=uuid.uuid4(), user_id=user_id, type=type, title=title, message=message
    )
    session.add(notification)

    # 2) Email — only when the caller opts the event in via email_category.
    if email_category is None:
        return notification
    recipient = email_to or await session.scalar(select(User.email).where(User.id == user_id))
    if not recipient:
        return notification
    if not force_email and not await _email_allowed(session, user_id, email_category):
        return notification
    session.add(
        EmailOutbox(
            # external recipients (e.g. a non-user invitee) carry no user_id
            user_id=None if email_to is not None else user_id,
            to_email=recipient,
            subject=email_subject or title,
            body=email_body or message,
            category=email_category,
            status="pending",
        )
    )
    return notification


# --- reads / mutations for the API ----------------------------------------- #
async def list_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
    unread_only: bool = False,
) -> tuple[list[Notification], int, int]:
    """Return (items, total, unread_count) for the caller's own feed."""
    from sqlalchemy import func

    base = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        base = base.where(Notification.read.is_(False))
    total = (await session.scalar(select(func.count()).select_from(base.subquery()))) or 0
    unread = (
        await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read.is_(False))
        )
    ) or 0
    rows = (
        (
            await session.execute(
                base.order_by(Notification.created_at.desc())
                .limit(min(limit, 200))
                .offset(max(offset, 0))
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total), int(unread)


async def unread_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    from sqlalchemy import func

    return int(
        (
            await session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.user_id == user_id, Notification.read.is_(False))
            )
        )
        or 0
    )


async def mark_read(
    session: AsyncSession, *, user_id: uuid.UUID, notification_id: uuid.UUID
) -> bool:
    n = await session.get(Notification, notification_id)
    if n is None or n.user_id != user_id:
        return False
    n.read = True
    return True


async def mark_all_read(session: AsyncSession, user_id: uuid.UUID) -> int:
    rows = (
        (
            await session.execute(
                select(Notification).where(
                    Notification.user_id == user_id, Notification.read.is_(False)
                )
            )
        )
        .scalars()
        .all()
    )
    for n in rows:
        n.read = True
    return len(rows)


async def get_preferences(session: AsyncSession, user_id: uuid.UUID) -> dict:
    prefs = (
        await session.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        )
    ).scalar_one_or_none()
    if prefs is None:
        return {
            "email_investment_updates": True,
            "email_returns": True,
            "email_security_alerts": True,
            "email_new_properties": True,
        }
    return {
        "email_investment_updates": prefs.email_investment_updates,
        "email_returns": prefs.email_returns,
        "email_security_alerts": prefs.email_security_alerts,
        "email_new_properties": prefs.email_new_properties,
    }


async def update_preferences(session: AsyncSession, user_id: uuid.UUID, **updates: bool) -> dict:
    """Upsert the caller's EMAIL preferences. Only the four email keys are accepted;
    any other key (e.g. a stray sms/push flag) is ignored — those channels don't exist."""
    prefs = (
        await session.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        )
    ).scalar_one_or_none()
    if prefs is None:
        prefs = NotificationPreference(user_id=user_id)
        session.add(prefs)
    for key in _CATEGORY_PREF.values():
        if key in updates and updates[key] is not None:
            setattr(prefs, key, bool(updates[key]))
    await session.flush()
    return await get_preferences(session, user_id)
