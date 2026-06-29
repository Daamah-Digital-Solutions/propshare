"""Inter-vivos gifting (Group 5) — REAL scheduled + recurring gifts.

Owner decision: *follow the frontend and make it real.* The gifting UI promised a SCHEDULED
+ recurring gift that "executes automatically on the date" with a "7-day reminder". We build
exactly that — no fake auto-execute, no fake reminder:

  * **Schedule** reserves the gift up front so the promise is truthful:
    - ``property_shares`` → the gifted UNITS are reserved via the shared
      ``secondary_service.reserved_units`` rule (a 4th term), so they can't also be listed
      (Phase 8), LP-exited (Phase 9), family-allocated (Phase 10) or double-gifted.
    - ``wallet`` → the cash is ESCROWED via a real ``wallet_service.debit`` now; refunded on
      cancel; credited to the recipient on execution.
  * **Execute** (cron, on the date) reuses the Phase-8/10 atomic-transfer pattern: property
    ``FOR UPDATE``, ledger −N/+N (``fee_rate`` stamped — Decision-2), Σ/property conserved.
    A REAL (KYC'd) recipient receives immediately; a non-user recipient becomes ``pending``
    (units stay reserved / cash stays escrowed) and **materializes on their KYC** — the same
    real/pending hook as Phase-10 family / Group-4 estate.
  * **Recurring** re-enqueues the NEXT single occurrence only (not every future year),
    re-reserving units / re-escrowing cash then; ``UNIQUE(series_id, scheduled_for)`` makes
    re-runs idempotent. End condition = until cancelled, or an optional ``recurrence_end``.

Asset scope: property_shares + wallet are REAL; passive_income / rental_returns / tokenized
/ allocation are honest-disabled in the UI (no real backing — tokenization is the separate
BRX project) and rejected by the schema, never reaching here.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import KycVerification, Property, ScheduledGift, User
from app.models.base import TransactionType
from app.models.investments import OwnershipLedger
from app.services import (
    notification_service,
    secondary_service,
    settings_service,
    wallet_service,
)

_CENTS = decimal.Decimal("0.01")
_HUNDRED = decimal.Decimal(100)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _q(value: decimal.Decimal) -> decimal.Decimal:
    return value.quantize(_CENTS, rounding=decimal.ROUND_HALF_UP)


async def _holding(session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(OwnershipLedger.units), 0)).where(
            OwnershipLedger.user_id == user_id, OwnershipLedger.property_id == property_id
        )
    )
    return int(total or 0)


async def _wallet_balance(session: AsyncSession, user_id: uuid.UUID) -> decimal.Decimal:
    from app.models import Wallet

    bal = await session.scalar(select(Wallet.balance).where(Wallet.user_id == user_id))
    return decimal.Decimal(bal) if bal is not None else decimal.Decimal("0")


async def _resolve_recipient(
    session: AsyncSession, email: str | None
) -> tuple[uuid.UUID | None, bool]:
    """Match a recipient email to a user; ``active`` is True only when KYC-verified
    (only then can they receive a REAL move). Mirrors estate ``_resolve_user``."""
    if not email:
        return None, False
    user = (
        await session.execute(select(User).where(func.lower(User.email) == email.lower()))
    ).scalar_one_or_none()
    if user is None:
        return None, False
    status = await session.scalar(
        select(KycVerification.status).where(KycVerification.user_id == user.id)
    )
    return user.id, str(status) == "verified"


def serialize(g: ScheduledGift) -> dict:
    return {
        "id": g.id,
        "recipient_name": g.recipient_name,
        "recipient_email": g.recipient_email,
        "is_user": g.recipient_user_id is not None,
        "asset_type": g.asset_type,
        "property_id": g.property_id,
        "units": g.units,
        "amount": str(g.amount) if g.amount is not None else None,
        "occasion": g.occasion,
        "message": g.message,
        "scheduled_for": g.scheduled_for,
        "recurring": g.recurring,
        "recurrence_end": g.recurrence_end,
        "status": g.status,
        "failure_reason": g.failure_reason,
        "created_at": g.created_at,
    }


# --- schedule / cancel / list (owner-scoped) -------------------------------- #
async def schedule_gift(
    session: AsyncSession, *, giver_id: uuid.UUID, data: dict, idempotency_key: str
) -> dict:
    # Idempotency-Key replay -> the existing gift (no double reserve / double escrow).
    existing = (
        await session.execute(
            select(ScheduledGift).where(ScheduledGift.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return serialize(existing)

    email = (data.get("recipient_email") or "").strip() or None
    if email is None:
        raise AppError(
            "RECIPIENT_EMAIL_REQUIRED",
            "A recipient email is required so the gift can reach a real account.",
            status_code=422,
        )
    scheduled_for: dt.date = data["scheduled_for"]
    if scheduled_for < _utcnow().date():
        raise AppError("SCHEDULE_IN_PAST", "Schedule the gift for today or later.", status_code=422)
    recurrence_end: dt.date | None = data.get("recurrence_end")
    if recurrence_end is not None and recurrence_end < scheduled_for:
        raise AppError(
            "INVALID_RECURRENCE", "Recurrence end must be on/after the date.", status_code=422
        )

    recipient_user_id, _active = await _resolve_recipient(session, email)
    asset_type = data["asset_type"]

    # Generate the id client-side so series_id (NOT NULL) is known before the INSERT;
    # a single-gift's series is itself (recurring rows carry the same series_id).
    gift_id = uuid.uuid4()
    gift = ScheduledGift(
        id=gift_id,
        series_id=gift_id,
        giver_id=giver_id,
        recipient_user_id=recipient_user_id,
        recipient_email=email,
        recipient_name=data["recipient_name"].strip(),
        asset_type=asset_type,
        occasion=data.get("occasion"),
        message=data.get("message"),
        scheduled_for=scheduled_for,
        recurring=bool(data.get("recurring")),
        recurrence_end=recurrence_end,
        status="scheduled",
        idempotency_key=idempotency_key,
    )

    if asset_type == "property_shares":
        property_id = data["property_id"]
        units = int(data["units"])
        # Lock the property: serializes the reservation math against listings/exits/transfers.
        prop = (
            await session.execute(
                select(Property).where(Property.id == property_id).with_for_update()
            )
        ).scalar_one_or_none()
        if prop is None:
            raise AppError("NOT_FOUND", "Property not found", status_code=404)
        free = await _holding(
            session, giver_id, property_id
        ) - await secondary_service.reserved_units(session, giver_id, property_id)
        if units > free:
            raise AppError(
                "INSUFFICIENT_UNITS",
                "Not enough unreserved units to gift.",
                status_code=422,
                details={"free": free, "requested": units},
            )
        gift.property_id = property_id
        gift.units = units
        session.add(gift)  # the scheduled row now reserves the units (status='scheduled')
        await session.flush()  # populate server defaults (created_at) for the response
    else:  # wallet
        amount = _q(decimal.Decimal(str(data["amount"])))
        if amount <= 0:
            raise AppError("INVALID_AMOUNT", "Gift amount must be positive.", status_code=422)
        gift.amount = amount
        session.add(gift)
        await session.flush()
        # Escrow the cash NOW (real debit) — the only way "will execute" is truthful.
        await wallet_service.debit(
            session,
            user_id=giver_id,
            reference_id=gift.id,
            line_items=[(TransactionType.gift, amount, "Gift escrow — scheduled")],
            actor_id=giver_id,
        )

    await write_audit(
        session,
        action="gift.scheduled",
        entity_type="scheduled_gift",
        entity_id=str(gift.id),
        actor_id=giver_id,
        after={
            "asset_type": asset_type,
            "scheduled_for": scheduled_for.isoformat(),
            "recurring": gift.recurring,
        },
    )
    return serialize(gift)


async def cancel_gift(session: AsyncSession, *, giver_id: uuid.UUID, gift_id: uuid.UUID) -> dict:
    gift = (
        await session.execute(
            select(ScheduledGift).where(ScheduledGift.id == gift_id).with_for_update()
        )
    ).scalar_one_or_none()
    if gift is None or gift.giver_id != giver_id:
        raise AppError("NOT_FOUND", "Gift not found", status_code=404)
    if gift.status != "scheduled":
        raise AppError("INVALID_STATE", "Only a scheduled gift can be cancelled.", status_code=409)
    gift.status = "cancelled"
    gift.updated_at = _utcnow()
    if gift.asset_type == "wallet" and gift.amount is not None:
        # Refund the escrow (property reservation releases automatically via the status).
        await wallet_service.credit(
            session,
            user_id=giver_id,
            amount=gift.amount,
            reference_id=gift.id,
            tx_type=TransactionType.gift,
            description="Gift cancelled — escrow refunded",
            actor_id=giver_id,
        )
    await write_audit(
        session,
        action="gift.cancelled",
        entity_type="scheduled_gift",
        entity_id=str(gift.id),
        actor_id=giver_id,
    )
    return serialize(gift)


async def list_gifts(session: AsyncSession, giver_id: uuid.UUID) -> list[ScheduledGift]:
    res = await session.execute(
        select(ScheduledGift)
        .where(ScheduledGift.giver_id == giver_id)
        .order_by(ScheduledGift.scheduled_for, ScheduledGift.created_at)
    )
    return list(res.scalars().all())


# --- the executor cron (admin OR X-Cron-Secret) ----------------------------- #
async def run_due(session: AsyncSession, *, now: dt.datetime | None = None) -> dict:
    """Two idempotent passes: send the 7-day reminders, then execute due gifts. Uses
    ``FOR UPDATE SKIP LOCKED`` so a concurrent run never double-processes a row."""
    now = now or _utcnow()
    today = now.date()
    remind_cutoff = today + dt.timedelta(days=7)

    # Pass 1 — 7-day reminders (real Phase-12 notification; once per gift).
    reminders = 0
    rows = (
        (
            await session.execute(
                select(ScheduledGift)
                .where(
                    ScheduledGift.status == "scheduled",
                    ScheduledGift.reminder_sent_at.is_(None),
                    ScheduledGift.scheduled_for <= remind_cutoff,
                )
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for g in rows:
        await notification_service.notify(
            session,
            user_id=g.giver_id,
            type="gift",
            title="Upcoming scheduled gift",
            message=(
                f"Your gift to {g.recipient_name} is scheduled for "
                f"{g.scheduled_for.isoformat()}. It will execute automatically on the date."
            ),
            email_category="investment_updates",
        )
        g.reminder_sent_at = now
        reminders += 1

    # Pass 2 — execute due gifts.
    mgmt_rate = await settings_service.get_management_fee_pct(session)
    fee_pct = await settings_service.get_gift_fee_pct(session)
    due = (
        (
            await session.execute(
                select(ScheduledGift)
                .where(
                    ScheduledGift.status == "scheduled",
                    ScheduledGift.scheduled_for <= today,
                )
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    executed = pending = failed = 0
    for g in due:
        outcome = await _execute_one(session, g, now=now, mgmt_rate=mgmt_rate, fee_pct=fee_pct)
        if outcome == "executed":
            executed += 1
        elif outcome == "pending":
            pending += 1
        else:
            failed += 1

    return {"reminders_sent": reminders, "executed": executed, "pending": pending, "failed": failed}


async def _fail(session: AsyncSession, g: ScheduledGift, reason: str) -> str:
    g.status = "failed"
    g.failure_reason = reason
    g.updated_at = _utcnow()
    await notification_service.notify(
        session,
        user_id=g.giver_id,
        type="gift",
        title="Scheduled gift could not be sent",
        message=f"Your gift to {g.recipient_name} did not execute: {reason}",
    )
    await write_audit(
        session,
        action="gift.failed",
        entity_type="scheduled_gift",
        entity_id=str(g.id),
        after={"reason": reason},
    )
    return "failed"


async def _execute_one(
    session: AsyncSession,
    g: ScheduledGift,
    *,
    now: dt.datetime,
    mgmt_rate: decimal.Decimal,
    fee_pct: decimal.Decimal,
) -> str:
    """Execute one due gift. All operations that can raise (fund/unit checks, fee debit)
    run BEFORE any ledger/credit write, so catching keeps prior gifts' writes intact."""
    recipient_user_id, active = await _resolve_recipient(session, g.recipient_email)
    if recipient_user_id is not None:
        g.recipient_user_id = recipient_user_id

    if g.asset_type == "property_shares":
        if g.property_id is None or g.units is None:
            return await _fail(session, g, "Gift is missing its property/units.")
        prop = (
            await session.execute(
                select(Property).where(Property.id == g.property_id).with_for_update()
            )
        ).scalar_one_or_none()
        if prop is None:
            return await _fail(session, g, "Property no longer exists.")
        if await _holding(session, g.giver_id, g.property_id) < g.units:
            return await _fail(session, g, "You no longer hold enough units.")

        if active and recipient_user_id is not None:
            fee = _q(prop.unit_price * g.units * fee_pct / _HUNDRED)
            if fee > 0:
                try:
                    await wallet_service.debit(
                        session,
                        user_id=g.giver_id,
                        reference_id=g.id,
                        line_items=[(TransactionType.fee, fee, "Gift fee")],
                        actor_id=g.giver_id,
                    )
                except AppError:
                    return await _fail(session, g, "Insufficient wallet balance for the gift fee.")
            session.add(
                OwnershipLedger(
                    user_id=g.giver_id,
                    property_id=g.property_id,
                    investment_id=None,
                    units=-g.units,
                    unit_price=prop.unit_price,
                    reason="gift_transfer_out",
                )
            )
            session.add(
                OwnershipLedger(
                    user_id=recipient_user_id,
                    property_id=g.property_id,
                    investment_id=None,
                    units=g.units,
                    unit_price=prop.unit_price,
                    reason="gift_transfer_in",
                    fee_rate=mgmt_rate,  # Decision-2: recipient carries the fee liability
                )
            )
            g.status = "executed"
            g.executed_at = now
            g.materialized_at = now
            await _notify_received(session, g)
            await _audit_executed(session, g, real=True)
            await _reenqueue(session, g, now=now)
            return "executed"
        # Non-user recipient: units stay reserved; materialize on their KYC.
        g.status = "pending"
        g.executed_at = now
        await _notify_pending(session, g)
        await _audit_executed(session, g, real=False)
        await _reenqueue(session, g, now=now)
        return "pending"

    # wallet — cash already escrowed at schedule.
    if g.amount is None:
        return await _fail(session, g, "Gift is missing its amount.")
    if active and recipient_user_id is not None:
        await wallet_service.credit(
            session,
            user_id=recipient_user_id,
            amount=g.amount,
            reference_id=g.id,
            tx_type=TransactionType.gift,
            description="Gift received",
            actor_id=g.giver_id,
        )
        g.status = "executed"
        g.executed_at = now
        g.materialized_at = now
        await _notify_received(session, g)
        await _audit_executed(session, g, real=True)
        await _reenqueue(session, g, now=now)
        return "executed"
    # Non-user recipient: escrow stays held; credited on their KYC.
    g.status = "pending"
    g.executed_at = now
    await _notify_pending(session, g)
    await _audit_executed(session, g, real=False)
    await _reenqueue(session, g, now=now)
    return "pending"


async def _reenqueue(session: AsyncSession, g: ScheduledGift, *, now: dt.datetime) -> None:
    """Re-enqueue the NEXT single occurrence of a recurring gift (not every future year):
    re-reserve units / re-escrow cash now. Skip + notify if the giver can no longer cover it."""
    if not g.recurring:
        return
    try:
        nxt = g.scheduled_for.replace(year=g.scheduled_for.year + 1)
    except ValueError:  # Feb 29 -> non-leap year
        nxt = g.scheduled_for + dt.timedelta(days=365)
    if g.recurrence_end is not None and nxt > g.recurrence_end:
        return

    new = ScheduledGift(
        giver_id=g.giver_id,
        recipient_user_id=g.recipient_user_id,
        recipient_email=g.recipient_email,
        recipient_name=g.recipient_name,
        asset_type=g.asset_type,
        property_id=g.property_id,
        units=g.units,
        amount=g.amount,
        occasion=g.occasion,
        message=g.message,
        scheduled_for=nxt,
        recurring=True,
        recurrence_end=g.recurrence_end,
        series_id=g.series_id,
        status="scheduled",
    )

    if g.asset_type == "property_shares" and g.property_id is not None and g.units is not None:
        free = await _holding(
            session, g.giver_id, g.property_id
        ) - await secondary_service.reserved_units(session, g.giver_id, g.property_id)
        if g.units > free:
            await _notify_not_renewed(session, g, "not enough unreserved units")
            return
        session.add(new)  # the new scheduled row reserves the units for the next occurrence
    elif g.asset_type == "wallet" and g.amount is not None:
        if await _wallet_balance(session, g.giver_id) < g.amount:
            await _notify_not_renewed(session, g, "insufficient wallet balance")
            return
        session.add(new)
        await session.flush()
        await wallet_service.debit(  # escrow the next occurrence now
            session,
            user_id=g.giver_id,
            reference_id=new.id,
            line_items=[(TransactionType.gift, g.amount, "Gift escrow — recurring")],
            actor_id=g.giver_id,
        )


# --- materialization (pending -> real on recipient KYC) --------------------- #
async def materialize_for_user(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    """Link pending gifts for this newly-KYC'd user (by email) and convert their pending
    gifts to real moves. Idempotent. Mirrors family/estate ``materialize_for_user``."""
    user = await session.get(User, user_id)
    if user is None:
        return 0
    status = await session.scalar(
        select(KycVerification.status).where(KycVerification.user_id == user_id)
    )
    if str(status) != "verified":
        return 0

    if user.email:
        unlinked = (
            (
                await session.execute(
                    select(ScheduledGift).where(
                        func.lower(ScheduledGift.recipient_email) == user.email.lower(),
                        ScheduledGift.recipient_user_id.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for g in unlinked:
            g.recipient_user_id = user_id

    pendings = (
        (
            await session.execute(
                select(ScheduledGift)
                .where(
                    ScheduledGift.recipient_user_id == user_id,
                    ScheduledGift.status == "pending",
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    mgmt_rate = await settings_service.get_management_fee_pct(session)
    now = _utcnow()
    count = 0
    for g in pendings:
        if g.asset_type == "property_shares" and g.property_id is not None and g.units is not None:
            prop = (
                await session.execute(
                    select(Property).where(Property.id == g.property_id).with_for_update()
                )
            ).scalar_one_or_none()
            if prop is None or await _holding(session, g.giver_id, g.property_id) < g.units:
                continue  # defensive: units already moved away
            session.add(
                OwnershipLedger(
                    user_id=g.giver_id,
                    property_id=g.property_id,
                    investment_id=None,
                    units=-g.units,
                    unit_price=prop.unit_price,
                    reason="gift_transfer_out",
                )
            )
            session.add(
                OwnershipLedger(
                    user_id=user_id,
                    property_id=g.property_id,
                    investment_id=None,
                    units=g.units,
                    unit_price=prop.unit_price,
                    reason="gift_transfer_in",
                    fee_rate=mgmt_rate,
                )
            )
        elif g.asset_type == "wallet" and g.amount is not None:
            await wallet_service.credit(  # release the escrow to the now-real recipient
                session,
                user_id=user_id,
                amount=g.amount,
                reference_id=g.id,
                tx_type=TransactionType.gift,
                description="Gift received",
                actor_id=g.giver_id,
            )
        else:
            continue
        g.status = "executed"
        g.materialized_at = now
        count += 1
    return count


# --- notification helpers --------------------------------------------------- #
async def _notify_received(session: AsyncSession, g: ScheduledGift) -> None:
    if g.recipient_user_id is None:
        return
    await notification_service.notify(
        session,
        user_id=g.recipient_user_id,
        type="gift",
        title="You've received a gift",
        message=(
            g.message or f"A gift from a family member ({g.occasion or 'a special occasion'})."
        ),
        email_category="investment_updates",
    )


async def _notify_pending(session: AsyncSession, g: ScheduledGift) -> None:
    await notification_service.notify(
        session,
        user_id=g.giver_id,
        type="gift",
        title="Gift awaiting recipient verification",
        message=(
            f"Your gift to {g.recipient_name} is reserved and will be delivered once they "
            "register and verify their identity."
        ),
    )


async def _notify_not_renewed(session: AsyncSession, g: ScheduledGift, why: str) -> None:
    await notification_service.notify(
        session,
        user_id=g.giver_id,
        type="gift",
        title="Recurring gift not renewed",
        message=f"Next year's gift to {g.recipient_name} was not scheduled ({why}).",
    )


async def _audit_executed(session: AsyncSession, g: ScheduledGift, *, real: bool) -> None:
    await write_audit(
        session,
        action="gift.executed" if real else "gift.pending",
        entity_type="scheduled_gift",
        entity_id=str(g.id),
        actor_id=g.giver_id,
        after={
            "asset_type": g.asset_type,
            "recipient": str(g.recipient_user_id) if g.recipient_user_id else g.recipient_email,
            "real": real,
        },
    )
