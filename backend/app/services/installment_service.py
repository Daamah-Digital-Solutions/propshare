"""Installment plans (Group 6) — progressive-vesting purchase of under-construction units.

Owner-confirmed model (licensed) + owner-accepted, admin-configurable fee (DECISIONS.md):

  * The investor commits to ``units_total`` units at today's LOCKED ``unit_price`` and pays a
    down payment + N monthly installments. At plan creation the whole allocation is RESERVED
    out of ``property.available_units`` (mirrors the Phase-5 direct-pay reservation) so it
    can't be oversold; the plan holds the not-yet-vested units.
  * Each PAID payment (down payment + installments) is charged from the wallet
    (server-authoritative, atomic, idempotent) — base principal (``transaction_type
    'investment'``) + the installment fee (``'fee'``, at the snapshot rate) — and VESTS its
    proportional slice into the append-only ``ownership_ledger`` (reason ``installment_vest``,
    ``fee_rate`` stamped — Decision-2). By the final payment all units are vested and the plan
    is ``completed`` (handover).
  * Units conserve: ``available (reserved at creation) + Σ ledger (vested) + Σ plan-unvested
    (active plans) == total_units`` — the reconciliation ``property_units`` check includes the
    plan-unvested term.
  * Pre-handover protections: a plan's vested units are RESERVED (``reserved_units``) so they
    can't be listed/LP-exited/family-allocated/gifted until handover, and rental yield EXCLUDES
    them (``distribution_service._ownership``) until the plan completes.

Fee is snapshotted at plan creation, so an admin rate change never rewrites existing schedules.
"""

from __future__ import annotations

import calendar
import datetime as dt
import decimal
import uuid
from collections.abc import Hashable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import InstallmentPayment, InstallmentPlan, Property
from app.models.base import PropertyStatus, TransactionType
from app.models.investments import OwnershipLedger
from app.services import notification_service, settings_service, wallet_service
from app.services.distribution_service import hamilton
from app.services.investment_service import _recompute_progress

_CENTS = decimal.Decimal("0.01")
_HUNDRED = decimal.Decimal(100)
_REMINDER_DAYS = 3  # notify this many days before an installment is due

# Down-payment percent per duration — mirrors the frontend installmentDurations map.
_DOWN_PCT: dict[int, int] = {6: 30, 12: 25, 18: 20, 24: 15}


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _q(value: decimal.Decimal) -> decimal.Decimal:
    return value.quantize(_CENTS, rounding=decimal.ROUND_HALF_UP)


def _add_months(d: dt.date, n: int) -> dt.date:
    """Add n calendar months, clamping the day to the target month's length."""
    total = d.month - 1 + n
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


async def _holding(session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(OwnershipLedger.units), 0)).where(
            OwnershipLedger.user_id == user_id, OwnershipLedger.property_id == property_id
        )
    )
    return int(total or 0)


# --- serialization ---------------------------------------------------------- #
def serialize_payment(p: InstallmentPayment) -> dict:
    return {
        "id": p.id,
        "seq": p.seq,
        "kind": p.kind,
        "due_date": p.due_date,
        "base_amount": str(p.base_amount),
        "fee_amount": str(p.fee_amount),
        "total_amount": str(p.total_amount),
        "vest_units": p.vest_units,
        "status": p.status,
        "paid_at": p.paid_at,
    }


def serialize_plan(plan: InstallmentPlan, payments: list[InstallmentPayment]) -> dict:
    return {
        "id": plan.id,
        "property_id": plan.property_id,
        "units_total": plan.units_total,
        "unit_price": str(plan.unit_price),
        "down_payment_pct": plan.down_payment_pct,
        "duration_months": plan.duration_months,
        "fee_rate": str(plan.fee_rate),
        "vested_units": plan.vested_units,
        "status": plan.status,
        "created_at": plan.created_at,
        "completed_at": plan.completed_at,
        "payments": [serialize_payment(p) for p in sorted(payments, key=lambda x: x.seq)],
    }


async def _payments_for(session: AsyncSession, plan_id: uuid.UUID) -> list[InstallmentPayment]:
    res = await session.execute(
        select(InstallmentPayment)
        .where(InstallmentPayment.plan_id == plan_id)
        .order_by(InstallmentPayment.seq)
    )
    return list(res.scalars().all())


# --- create a plan (reserve allocation + build schedule + pay down payment) --- #
async def create_plan(
    session: AsyncSession,
    *,
    investor_id: uuid.UUID,
    property_id: uuid.UUID,
    amount: float,
    duration_months: int,
    idempotency_key: str,
) -> dict:
    # Idempotency-Key replay -> the existing plan (no double reserve / double charge).
    existing = (
        await session.execute(
            select(InstallmentPlan).where(InstallmentPlan.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return serialize_plan(existing, await _payments_for(session, existing.id))

    if duration_months not in _DOWN_PCT:
        raise AppError(
            "INVALID_DURATION",
            f"Duration must be one of {sorted(_DOWN_PCT)} months.",
            status_code=422,
        )
    amount_dec = decimal.Decimal(str(amount))
    if amount_dec <= 0:
        raise AppError("INVALID_AMOUNT", "Amount must be positive.", status_code=422)

    # Lock the property: serializes the allocation math against invests/listings/other plans.
    prop = (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    if prop.status != PropertyStatus.active:
        raise AppError(
            "PROPERTY_NOT_OPEN", "This property is not open for funding.", status_code=409
        )
    if prop.unit_price <= 0:
        raise AppError("INVALID_PROPERTY", "Property has no unit price.", status_code=409)

    units_total = int(amount_dec // prop.unit_price)  # floor to whole units at the locked price
    if units_total < 1:
        raise AppError(
            "AMOUNT_TOO_LOW",
            f"Minimum is one unit (${prop.unit_price}).",
            status_code=422,
        )
    if units_total > prop.available_units:
        raise AppError(
            "INSUFFICIENT_UNITS",
            "Not enough units available in this property.",
            status_code=409,
            details={"available_units": prop.available_units, "requested": units_total},
        )

    down_pct = _DOWN_PCT[duration_months]
    fee_rate = await settings_service.get_installment_fee_pct(session)
    mgmt_rate = await settings_service.get_management_fee_pct(session)
    principal = _q(prop.unit_price * units_total)

    # Base principal split: down payment + (duration-1) monthly installments (last absorbs
    # rounding so the parts sum EXACTLY to principal).
    n_installments = duration_months - 1
    down_base = _q(principal * decimal.Decimal(down_pct) / _HUNDRED)
    remaining = principal - down_base
    per_installment = _q(remaining / n_installments) if n_installments else decimal.Decimal("0")
    bases: list[decimal.Decimal] = [down_base]
    for i in range(1, duration_months):
        if i == duration_months - 1:  # last installment absorbs the rounding remainder
            bases.append(principal - sum(bases))
        else:
            bases.append(per_installment)

    # Vest units ∝ each payment's base principal (Hamilton — sums EXACTLY to units_total).
    weights: list[tuple[Hashable, int]] = [(str(i), int(b * 100)) for i, b in enumerate(bases)]
    vest_split = hamilton(units_total, weights)

    # Reserve the whole allocation out of the pool now (the plan holds the unvested units).
    prop.available_units -= units_total
    prop.investors_count = prop.investors_count + 1

    plan = InstallmentPlan(
        investor_id=investor_id,
        property_id=property_id,
        units_total=units_total,
        unit_price=prop.unit_price,
        down_payment_pct=down_pct,
        duration_months=duration_months,
        fee_rate=fee_rate,
        management_fee_rate=mgmt_rate,
        vested_units=0,
        status="active",
        idempotency_key=idempotency_key,
    )
    session.add(plan)
    await session.flush()

    today = _utcnow().date()
    down_payment: InstallmentPayment | None = None
    for seq, base in enumerate(bases):
        fee_amount = _q(base * fee_rate / _HUNDRED)
        kind = (
            "downpayment"
            if seq == 0
            else ("final" if seq == duration_months - 1 else "installment")
        )
        pay = InstallmentPayment(
            plan_id=plan.id,
            seq=seq,
            kind=kind,
            due_date=today if seq == 0 else _add_months(today, seq),
            base_amount=base,
            fee_amount=fee_amount,
            total_amount=base + fee_amount,
            vest_units=int(vest_split.get(str(seq), 0)),
            status="scheduled",
        )
        session.add(pay)
        if seq == 0:
            down_payment = pay
    await session.flush()

    await write_audit(
        session,
        action="installment.plan.created",
        entity_type="installment_plan",
        entity_id=str(plan.id),
        actor_id=investor_id,
        after={
            "property_id": str(property_id),
            "units_total": units_total,
            "duration_months": duration_months,
            "down_payment_pct": down_pct,
            "fee_rate": str(fee_rate),
        },
    )

    # Pay the down payment now (atomic). INSUFFICIENT_FUNDS propagates -> the whole plan
    # rolls back (no reservation left behind).
    assert down_payment is not None
    await _charge_payment(
        session, plan=plan, prop=prop, payment=down_payment, idempotency_key=f"{idempotency_key}:0"
    )

    return serialize_plan(plan, await _payments_for(session, plan.id))


# --- charge one payment (down payment or installment) ----------------------- #
async def _charge_payment(
    session: AsyncSession,
    *,
    plan: InstallmentPlan,
    prop: Property,
    payment: InstallmentPayment,
    idempotency_key: str,
) -> None:
    """Debit the wallet (base + fee) and VEST the payment's units. Caller holds the property
    lock. Raises INSUFFICIENT_FUNDS BEFORE any write (the wallet check precedes the ledger
    writes) so a caller that catches it leaves no partial state."""
    if payment.status == "paid":
        return  # idempotent

    line_items: list[tuple[TransactionType, decimal.Decimal, str | None]] = [
        (
            TransactionType.investment,
            payment.base_amount,
            f"Installment {payment.seq} — {prop.title}",
        )
    ]
    if payment.fee_amount > 0:
        line_items.append((TransactionType.fee, payment.fee_amount, "Installment fee"))
    inv_wallet = await wallet_service.debit(
        session,
        user_id=plan.investor_id,
        reference_id=plan.id,
        line_items=line_items,
        actor_id=plan.investor_id,
    )
    # Count the installment PRINCIPAL toward the investor's invested cost basis — parity with a
    # direct buy (investment_service adds the subtotal). The vested units already contribute to
    # the portfolio's current_value, so without this the portfolio reports a phantom gain.
    inv_wallet.total_invested = inv_wallet.total_invested + payment.base_amount

    # Vest this payment's units into the append-only ledger (real ownership; NAV appreciation
    # is inherent from the milestone value_index that values these rows).
    if payment.vest_units > 0:
        session.add(
            OwnershipLedger(
                user_id=plan.investor_id,
                property_id=plan.property_id,
                investment_id=None,
                units=payment.vest_units,
                unit_price=plan.unit_price,
                reason="installment_vest",
                fee_rate=plan.management_fee_rate,  # Decision-2: consented rate
            )
        )
        plan.vested_units += payment.vest_units

    # Book the real money received against the property's funding.
    prop.funded_amount = prop.funded_amount + payment.base_amount
    _recompute_progress(prop)
    if prop.available_units <= 0:
        prop.status = PropertyStatus.funded

    payment.status = "paid"
    payment.paid_at = _utcnow()
    payment.idempotency_key = idempotency_key
    plan.updated_at = _utcnow()

    # The plan completes (handover) when EVERY payment is paid — NOT when vesting hits
    # units_total, which can happen a payment or two early due to integer rounding (a tail
    # installment may vest 0 units). Count the other still-unpaid payments (exclude this row,
    # which is set 'paid' in-session but may be unflushed).
    remaining_unpaid = await session.scalar(
        select(func.count())
        .select_from(InstallmentPayment)
        .where(
            InstallmentPayment.plan_id == plan.id,
            InstallmentPayment.id != payment.id,
            InstallmentPayment.status != "paid",
        )
    )
    if int(remaining_unpaid or 0) == 0:
        # Every payment settled: force-vest any rounding remainder so ownership is exact.
        if plan.vested_units < plan.units_total:
            short = plan.units_total - plan.vested_units
            session.add(
                OwnershipLedger(
                    user_id=plan.investor_id,
                    property_id=plan.property_id,
                    investment_id=None,
                    units=short,
                    unit_price=plan.unit_price,
                    reason="installment_vest",
                    fee_rate=plan.management_fee_rate,
                )
            )
            plan.vested_units += short
        plan.status = "completed"
        plan.completed_at = _utcnow()

    await write_audit(
        session,
        action="installment.payment.paid",
        entity_type="installment_payment",
        entity_id=str(payment.id),
        actor_id=plan.investor_id,
        after={
            "plan_id": str(plan.id),
            "seq": payment.seq,
            "base": str(payment.base_amount),
            "fee": str(payment.fee_amount),
            "vested_units": payment.vest_units,
            "plan_status": plan.status,
        },
    )


# --- pay a specific installment (manual, early/catch-up) -------------------- #
async def pay_installment(
    session: AsyncSession, *, investor_id: uuid.UUID, payment_id: uuid.UUID, idempotency_key: str
) -> dict:
    payment = (
        await session.execute(
            select(InstallmentPayment).where(InstallmentPayment.id == payment_id).with_for_update()
        )
    ).scalar_one_or_none()
    if payment is None:
        raise AppError("NOT_FOUND", "Installment not found", status_code=404)
    plan = (
        await session.execute(
            select(InstallmentPlan).where(InstallmentPlan.id == payment.plan_id).with_for_update()
        )
    ).scalar_one()
    if plan.investor_id != investor_id:
        raise AppError("NOT_FOUND", "Installment not found", status_code=404)
    if payment.status == "paid":
        return serialize_plan(plan, await _payments_for(session, plan.id))
    if plan.status != "active":
        raise AppError("INVALID_STATE", "This plan is not active.", status_code=409)

    prop = (
        await session.execute(
            select(Property).where(Property.id == plan.property_id).with_for_update()
        )
    ).scalar_one()
    await _charge_payment(
        session, plan=plan, prop=prop, payment=payment, idempotency_key=idempotency_key
    )
    return serialize_plan(plan, await _payments_for(session, plan.id))


# --- reads ------------------------------------------------------------------ #
async def list_plans(session: AsyncSession, investor_id: uuid.UUID) -> list[dict]:
    plans = (
        (
            await session.execute(
                select(InstallmentPlan)
                .where(InstallmentPlan.investor_id == investor_id)
                .order_by(InstallmentPlan.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    out = []
    for plan in plans:
        out.append(serialize_plan(plan, await _payments_for(session, plan.id)))
    return out


# --- due-payment cron (admin OR X-Cron-Secret) ------------------------------ #
async def run_due(session: AsyncSession, *, now: dt.datetime | None = None) -> dict:
    """Idempotent sweep (FOR UPDATE SKIP LOCKED): send due-soon reminders, then charge due
    installments from the wallet. A payment that can't be charged (insufficient balance) is
    marked ``overdue`` and the investor is notified — GRACE + reminder, NO auto-forfeit and
    NO late fee (the UI states neither; see DECISIONS.md). Overdue rows are retried next run."""
    now = now or _utcnow()
    today = now.date()
    remind_cutoff = today + dt.timedelta(days=_REMINDER_DAYS)

    # Pass 1 — reminders for upcoming (not-yet-due) installments of active plans.
    reminders = 0
    rows = (
        await session.execute(
            select(InstallmentPayment, InstallmentPlan)
            .join(InstallmentPlan, InstallmentPayment.plan_id == InstallmentPlan.id)
            .where(
                InstallmentPayment.status == "scheduled",
                InstallmentPayment.reminder_sent_at.is_(None),
                InstallmentPayment.due_date <= remind_cutoff,
                InstallmentPayment.due_date >= today,
                InstallmentPayment.seq > 0,
                InstallmentPlan.status == "active",
            )
            .with_for_update(skip_locked=True, of=InstallmentPayment)
        )
    ).all()
    for payment, plan in rows:
        await notification_service.notify(
            session,
            user_id=plan.investor_id,
            type="installment",
            title="Upcoming installment payment",
            message=(
                f"Installment {payment.seq} of ${payment.total_amount} is due on "
                f"{payment.due_date.isoformat()}. It will be charged automatically from "
                "your wallet."
            ),
            email_category="investment_updates",
        )
        payment.reminder_sent_at = now
        reminders += 1

    # Pass 2 — charge due installments (down payments are paid at creation, so seq > 0).
    due = (
        (
            await session.execute(
                select(InstallmentPayment)
                .where(
                    InstallmentPayment.status.in_(("scheduled", "overdue")),
                    InstallmentPayment.due_date <= today,
                    InstallmentPayment.seq > 0,
                )
                .with_for_update(skip_locked=True)
                .order_by(InstallmentPayment.due_date)
            )
        )
        .scalars()
        .all()
    )
    paid = overdue = 0
    for payment in due:
        plan = (
            await session.execute(
                select(InstallmentPlan)
                .where(InstallmentPlan.id == payment.plan_id, InstallmentPlan.status == "active")
                .with_for_update()
            )
        ).scalar_one_or_none()
        if plan is None:
            continue
        prop = (
            await session.execute(
                select(Property).where(Property.id == plan.property_id).with_for_update()
            )
        ).scalar_one()
        try:
            await _charge_payment(
                session, plan=plan, prop=prop, payment=payment, idempotency_key=f"cron:{payment.id}"
            )
            paid += 1
        except AppError:
            # Insufficient balance (raised before any write) — grace + reminder, no forfeit.
            payment.status = "overdue"
            await notification_service.notify(
                session,
                user_id=plan.investor_id,
                type="installment",
                title="Installment payment missed",
                message=(
                    f"We couldn't charge installment {payment.seq} of ${payment.total_amount} "
                    "(insufficient wallet balance). Add funds — we'll retry automatically. Your "
                    "vested units are unaffected."
                ),
            )
            overdue += 1

    return {"reminders_sent": reminders, "paid": paid, "overdue": overdue}
