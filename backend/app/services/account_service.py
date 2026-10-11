"""An account's standing: is its email address confirmed, and is it closed.

* **A confirmed address.** What is sent to a person by email address (a family allocation and
  its returns, a gift, a beneficiary's share, a claim) is tied to the account registered with
  that address only once the account CONFIRMED the address. Anyone can type any address at
  sign-up and signing in does not ask for the confirmation, so an unconfirmed address says
  nothing about who opened the account. ``confirmed_by_address`` is the one lookup for it,
  and ``release_waiting`` hands over what waits once the address is confirmed.
* **A closed account** cannot sign in or act (``ensure_open``; the API's money and staff
  gates re-check it at action time). Staff close and reopen accounts in the admin panel; an
  approved claim about a holder's death, or about a holder who can no longer manage the
  account, closes the holder's: what remains in it waits for the other claims, whoever
  knows its password.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models.identity import RefreshToken, User

log = logging.getLogger("capimax.account")

CLOSED_MESSAGE = "This account is closed. Contact support if you believe this is a mistake."


# --- the address ------------------------------------------------------------- #
async def by_address(session: AsyncSession, email: str | None) -> User | None:
    """The account registered with this address, confirmed or not."""
    if not email:
        return None
    return (
        await session.execute(select(User).where(func.lower(User.email) == email.strip().lower()))
    ).scalar_one_or_none()


async def confirmed_by_address(session: AsyncSession, email: str | None) -> User | None:
    """The account this address belongs to for certain: registered with it, and the address
    confirmed in it. None while it is unconfirmed: nothing is tied to that account by
    address until then."""
    user = await by_address(session, email)
    return user if user is not None and user.email_verified else None


async def release_waiting(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Hand over what waits for this account: what was addressed to its confirmed email, and
    what is already tied to it. Called when the identity is verified and when the address
    is confirmed, whichever comes last; each part checks both and repeats nothing."""
    # imported here: these services reach back to this module
    from app.services import estate_service, family_service, gift_service

    closed = await session.scalar(select(User.closed_at).where(User.id == user_id))
    if closed is not None:
        return  # nothing is handed to a closed account
    await family_service.materialize_for_user(session, user_id=user_id)
    await estate_service.materialize_for_user(session, user_id=user_id)
    await gift_service.materialize_for_user(session, user_id=user_id)


async def release_after_confirmation(session: AsyncSession, user_id: uuid.UUID) -> None:
    """``release_waiting`` for the moment an address is confirmed. Whatever goes wrong in a
    handover stays there: the confirmation itself is never undone by it."""
    try:
        async with session.begin_nested():
            await release_waiting(session, user_id)
    except Exception:  # noqa: BLE001 - the confirmation stands; the next trigger retries
        log.exception("could not release what waits for account %s", user_id)


# --- open or closed ---------------------------------------------------------- #
def ensure_open(user: User) -> None:
    if user.closed_at is not None:
        raise AppError("ACCOUNT_CLOSED", CLOSED_MESSAGE, status_code=403)


async def ensure_open_id(session: AsyncSession, user_id: uuid.UUID) -> None:
    """The same check when only the id is at hand (the API's action-time gates)."""
    closed = await session.scalar(select(User.closed_at).where(User.id == user_id))
    if closed is not None:
        raise AppError("ACCOUNT_CLOSED", CLOSED_MESSAGE, status_code=403)


async def close(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    reason: str,
    actor_id: uuid.UUID | None,
) -> bool:
    """Close an account: it can no longer sign in, its sessions end now, and the money and
    staff gates refuse it at once. Nothing it holds is touched. False when it was closed
    already. The caller commits."""
    # imported here: the notification service is not needed to check an account
    from app.services import notification_service

    user = (
        await session.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()
    if user is None:
        raise AppError("NOT_FOUND", "User not found", status_code=404)
    if user.closed_at is not None:
        return False
    now = dt.datetime.now(dt.UTC)
    user.closed_at = now
    user.closed_reason = reason.strip()[:300] or "Closed by staff"
    user.closed_by = actor_id
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await write_audit(
        session,
        action="account.closed",
        entity_type="user",
        entity_id=str(user_id),
        actor_id=actor_id,
        after={"reason": user.closed_reason},
    )
    # the account's own address is told: a holder who is there to read it can object
    await notification_service.notify(
        session,
        user_id=user_id,
        type="security",
        title="Your account was closed",
        message=(
            f"Your Capimax PropShare account was closed ({user.closed_reason}). It can no "
            "longer be signed in to, and nothing in it was changed. If you are the account "
            "holder and this is a mistake, contact support now."
        ),
        email_category="security",
        force_email=True,
    )
    return True


async def reopen(session: AsyncSession, *, user_id: uuid.UUID, actor_id: uuid.UUID | None) -> bool:
    """Reopen a closed account (staff). False when it was not closed. The caller commits."""
    from app.services import notification_service

    user = (
        await session.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()
    if user is None:
        raise AppError("NOT_FOUND", "User not found", status_code=404)
    if user.closed_at is None:
        return False
    before = {"closed_at": user.closed_at.isoformat(), "reason": user.closed_reason}
    user.closed_at = None
    user.closed_reason = None
    user.closed_by = None
    await write_audit(
        session,
        action="account.reopened",
        entity_type="user",
        entity_id=str(user_id),
        actor_id=actor_id,
        before=before,
    )
    await notification_service.notify(
        session,
        user_id=user_id,
        type="security",
        title="Your account was reopened",
        message="Your Capimax PropShare account was reopened by our team. You can sign in again.",
        email_category="security",
        force_email=True,
    )
    return True
