"""Proactive nudges (Batch B, client doc §22/§31): the platform reaches out BEFORE the user
asks — through the existing notification feed + email outbox, never through a new channel.

Each nudge kind has a trigger (a state that has lasted N days), a cooldown (never repeat
within M days) and a fixed, honest message with the page to go to. Nothing here promises
returns or pushes a purchase; every nudge is about finishing something the user started.

Idempotent sweep: ``run_all`` can be called every hour by cron. Deduplication uses the
notifications table itself (``type = 'nudge:<kind>'``), so no extra state is kept.

Installment due-date reminders already live in ``installment_service.run_due`` and
distribution notices in ``distribution_service``; they are not duplicated here.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Investment,
    KycVerification,
    Notification,
    SupportTicket,
    Transaction,
    User,
    Wallet,
)
from app.services import notification_service


@dataclasses.dataclass(frozen=True)
class Nudge:
    kind: str
    after_days: int  # the state must have lasted at least this long
    cooldown_days: int  # do not repeat within this window
    title: str
    message: str
    email_category: str | None  # None = in-app only


NUDGES: dict[str, Nudge] = {
    "email_unverified": Nudge(
        "email_unverified",
        1,
        3,
        "Confirm your email address",
        "Your account is almost ready: confirm your email address to unlock verification and "
        "investing. Ask the assistant to resend the link if you cannot find it.",
        "security",
    ),
    "kyc_not_started": Nudge(
        "kyc_not_started",
        3,
        7,
        "Finish your identity verification",
        "Investing and withdrawals open once your identity verification (KYC) is complete. "
        "It takes a few minutes from Account → Verification.",
        "investment_updates",
    ),
    "kyc_in_review": Nudge(
        "kyc_in_review",
        5,
        7,
        "Your verification is still being reviewed",
        "Your identity verification has been with the review team for a few days. No action "
        "is needed from you; we will notify you as soon as it is decided.",
        None,
    ),
    "funded_not_invested": Nudge(
        "funded_not_invested",
        7,
        14,
        "Your wallet balance is waiting",
        "You added funds but have not chosen a property yet. Browse the marketplace whenever "
        "you are ready; the assistant can explain any listing's fees and exit options.",
        "new_properties",
    ),
    "ticket_waiting_user": Nudge(
        "ticket_waiting_user",
        3,
        3,
        "Support is waiting for your reply",
        "A support ticket of yours has a reply from the team and is waiting for you. Open "
        "Support to answer or close it.",
        "security",
    ),
}


def _cutoff(days: int, now: dt.datetime) -> dt.datetime:
    return now - dt.timedelta(days=days)


def _already_nudged(kind: str, cooldown_days: int, now: dt.datetime):
    """EXISTS clause: a nudge of this kind for the user inside the cooldown window."""
    return exists().where(
        and_(
            Notification.user_id == User.id,
            Notification.type == f"nudge:{kind}",
            Notification.created_at >= _cutoff(cooldown_days, now),
        )
    )


async def _candidates_email_unverified(session: AsyncSession, now: dt.datetime) -> list[User]:
    n = NUDGES["email_unverified"]
    stmt = select(User).where(
        User.email_verified.is_(False),
        User.password_hash.is_not(None),  # OAuth sign-ups are verified by the provider
        User.created_at <= _cutoff(n.after_days, now),
        ~_already_nudged(n.kind, n.cooldown_days, now),
    )
    return list((await session.execute(stmt)).scalars().all())


async def _candidates_kyc_not_started(session: AsyncSession, now: dt.datetime) -> list[User]:
    n = NUDGES["kyc_not_started"]
    stmt = (
        select(User)
        .join(KycVerification, KycVerification.user_id == User.id)
        .where(
            User.email_verified.is_(True),
            KycVerification.status == "pending",
            KycVerification.submitted_at.is_(None),
            User.created_at <= _cutoff(n.after_days, now),
            ~_already_nudged(n.kind, n.cooldown_days, now),
        )
    )
    return list((await session.execute(stmt)).scalars().all())


async def _candidates_kyc_in_review(session: AsyncSession, now: dt.datetime) -> list[User]:
    n = NUDGES["kyc_in_review"]
    stmt = (
        select(User)
        .join(KycVerification, KycVerification.user_id == User.id)
        .where(
            # a started verification is "submitted" (kyc_service); "pending" = not started
            KycVerification.status == "submitted",
            KycVerification.submitted_at.is_not(None),
            KycVerification.submitted_at <= _cutoff(n.after_days, now),
            ~_already_nudged(n.kind, n.cooldown_days, now),
        )
    )
    return list((await session.execute(stmt)).scalars().all())


async def _candidates_funded_not_invested(session: AsyncSession, now: dt.datetime) -> list[User]:
    n = NUDGES["funded_not_invested"]
    has_investment = exists().where(Investment.user_id == User.id)
    # "idle since": the last wallet movement (wallets.updated_at is trigger-maintained and
    # bumps on every balance touch, so the ledger's last row is the honest anchor)
    last_movement = (
        select(func.max(Transaction.created_at))
        .where(Transaction.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    stmt = (
        select(User)
        .join(Wallet, Wallet.user_id == User.id)
        .join(KycVerification, KycVerification.user_id == User.id)
        .where(
            Wallet.balance > 0,
            func.coalesce(last_movement, User.created_at) <= _cutoff(n.after_days, now),
            KycVerification.status == "verified",
            ~has_investment,
            ~_already_nudged(n.kind, n.cooldown_days, now),
        )
    )
    return list((await session.execute(stmt)).scalars().all())


async def _candidates_ticket_waiting_user(session: AsyncSession, now: dt.datetime) -> list[User]:
    n = NUDGES["ticket_waiting_user"]
    waiting = exists().where(
        and_(
            SupportTicket.user_id == User.id,
            SupportTicket.kind == "support",
            SupportTicket.status == "waiting_user",
            SupportTicket.updated_at <= _cutoff(n.after_days, now),
        )
    )
    stmt = select(User).where(waiting, ~_already_nudged(n.kind, n.cooldown_days, now))
    return list((await session.execute(stmt)).scalars().all())


CANDIDATES: dict[str, Callable[[AsyncSession, dt.datetime], Awaitable[list[User]]]] = {
    "email_unverified": _candidates_email_unverified,
    "kyc_not_started": _candidates_kyc_not_started,
    "kyc_in_review": _candidates_kyc_in_review,
    "funded_not_invested": _candidates_funded_not_invested,
    "ticket_waiting_user": _candidates_ticket_waiting_user,
}


async def run_kind(
    session: AsyncSession, kind: str, *, now: dt.datetime | None = None, limit: int = 500
) -> int:
    now = now or dt.datetime.now(dt.UTC)
    nudge = NUDGES[kind]
    users = (await CANDIDATES[kind](session, now))[:limit]
    for user in users:
        await notification_service.notify(
            session,
            user_id=user.id,
            type=f"nudge:{kind}",
            title=nudge.title,
            message=nudge.message,
            email_category=nudge.email_category,
            email_subject=nudge.title if nudge.email_category else None,
        )
    await session.flush()
    return len(users)


async def run_all(session: AsyncSession, *, now: dt.datetime | None = None) -> dict[str, int]:
    """One sweep over every nudge kind. Safe to repeat: cooldowns make it idempotent."""
    now = now or dt.datetime.now(dt.UTC)
    return {kind: await run_kind(session, kind, now=now) for kind in NUDGES}


async def last_nudges(session: AsyncSession, user_id: uuid.UUID) -> dict[str, dt.datetime]:
    """Most recent nudge per kind for one user (for the assistant/admin to explain)."""
    rows = await session.execute(
        select(Notification.type, func.max(Notification.created_at))
        .where(Notification.user_id == user_id, Notification.type.like("nudge:%"))
        .group_by(Notification.type)
    )
    return {t.split(":", 1)[1]: ts for t, ts in rows.all()}
