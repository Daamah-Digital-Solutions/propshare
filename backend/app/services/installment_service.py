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
from app.models import (
    InstallmentPayment,
    InstallmentPlan,
    Payment,
    Property,
    SecondaryListing,
    SecondaryTrade,
    Wallet,
)
from app.models.base import PropertyStatus, TransactionType
from app.models.identity import User
from app.models.investments import OwnershipLedger
from app.services import (
    broker_service,
    installment_pdf,
    notification_service,
    payment_service,
    settings_service,
    wallet_service,
)
from app.services.distribution_service import hamilton
from app.services.doc_lang import long_date, sheet_direction, status_text, tr
from app.services.investment_service import (
    RESERVATION_TTL,
    _recompute_progress,
    below_minimum,
    hold_lapsed,
    minimum_error,
    price_moved,
    refuse_sample,
    require_installments,
    require_price,
    retake_units,
    return_units,
)

_CENTS = decimal.Decimal("0.01")
_HUNDRED = decimal.Decimal(100)
_REMINDER_DAYS = 3  # notify this many days before an installment is due

# Down-payment percent per duration — mirrors the frontend installmentDurations map.
_DOWN_PCT: dict[int, int] = {6: 30, 12: 25, 18: 20, 24: 15}

# How the down payment is paid (0032): from the wallet at once, or through a hosted checkout —
# card (with Apple Pay / Google Pay), crypto or Pronova — whose webhook starts the plan. A Nova
# Sukuk certificate goes through ``open_plan`` + staff review instead (sukuk_service).
DIRECT_METHODS = frozenset({"card", "crypto", "pronova"})
PLAN_METHODS = frozenset({"wallet", *DIRECT_METHODS})
# A plan in one of these holds its units but has not started: nothing paid, nothing vested.
PENDING_STATUSES = ("pending_payment", "pending_review")
# How a receipt says the payment was made (None = charged from the wallet).
_PAID_WITH = {
    None: "from your wallet",
    "card": "by card",
    "crypto": "in crypto",
    "pronova": "with Pronova",
    "sukuk": "with your Nova Sukuk certificate",
}


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


# --- schedule math (plans and quotes share it) ------------------------------ #
def schedule_bases(principal: decimal.Decimal, duration_months: int) -> list[decimal.Decimal]:
    """Base principal of every payment: the down payment (seq 0) + ``duration_months - 1``
    monthly installments, the last absorbing the rounding so the parts sum EXACTLY to the
    principal. The single source of the split: plans and quotes both use it."""
    n_installments = duration_months - 1
    down_base = _q(principal * decimal.Decimal(_DOWN_PCT[duration_months]) / _HUNDRED)
    per_installment = (
        _q((principal - down_base) / n_installments) if n_installments else decimal.Decimal("0")
    )
    bases: list[decimal.Decimal] = [down_base]
    for i in range(1, duration_months):
        if i == duration_months - 1:  # last installment absorbs the rounding remainder
            bases.append(principal - sum(bases))
        else:
            bases.append(per_installment)
    return bases


def fee_for(base: decimal.Decimal, fee_rate: decimal.Decimal) -> decimal.Decimal:
    """The installment fee on one payment's base principal."""
    return _q(base * fee_rate / _HUNDRED)


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


def serialize_plan(
    plan: InstallmentPlan,
    payments: list[InstallmentPayment],
    prop: Property | None = None,
) -> dict:
    images = list(prop.images) if prop and prop.images else []
    return {
        "id": plan.id,
        "property_id": plan.property_id,
        # Which property this plan is for (Task 6 — the schedule is shown per-property).
        "property_title": (prop.title if prop else None) or "Property",
        "property_slug": prop.slug if prop else None,
        "property_location": prop.location if prop else None,
        "property_city": prop.city if prop else None,
        "property_image": images[0] if images else None,
        "property_spv": (prop.spv_name if prop else None),
        "units_total": plan.units_total,
        "unit_price": str(plan.unit_price),
        "down_payment_pct": plan.down_payment_pct,
        "duration_months": plan.duration_months,
        "fee_rate": str(plan.fee_rate),
        "vested_units": plan.vested_units,
        "status": plan.status,
        "payment_method": plan.payment_method or "wallet",
        "discount_amount": str(plan.discount_amount or 0),
        "reservation_expires_at": plan.reservation_expires_at,
        "failure_reason": plan.failure_reason,
        "created_at": plan.created_at,
        "completed_at": plan.completed_at,
        "parent_plan_id": plan.parent_plan_id,
        "payments": [serialize_payment(p) for p in sorted(payments, key=lambda x: x.seq)],
    }


async def _payments_for(session: AsyncSession, plan_id: uuid.UUID) -> list[InstallmentPayment]:
    res = await session.execute(
        select(InstallmentPayment)
        .where(InstallmentPayment.plan_id == plan_id)
        .order_by(InstallmentPayment.seq)
    )
    return list(res.scalars().all())


def position_figures(
    plan: InstallmentPlan,
    payments: list[InstallmentPayment],
    price: decimal.Decimal,
    entry_price: decimal.Decimal | None = None,
) -> dict:
    """A plan as a POSITION valued at ``price`` per unit (0034). Whoever holds it owns the
    right to all its units for the principal still to pay, so it is worth

        value  = units x price
        equity = value - principal still to pay
               = cost + gain

    "what was paid, plus the increase on the WHOLE position" (client, 2026-10-01: a $100 unit
    with $30 paid that rises 10% earns $10 on the $30). ``equity`` is what a buyer pays the
    seller; the buyer then pays the rest of the schedule. Also the honest value of a running
    plan in a portfolio: the units vested so far are whole units and can be worth more, or
    less, than the money actually paid in.

    ``cost`` and ``gain`` are the HOLDER's, measured from the price per unit the holder got in
    at (``entry_price``): the plan's locked price for the investor who started it, so cost is
    the principal paid; for an investor who bought the position (see ``holder_entry``) the
    price they bought it at, so cost is what they paid for it plus their installments since
    (cost = units x entry price - principal still to pay) and the gain starts at zero."""
    entry = decimal.Decimal(entry_price) if entry_price is not None else plan.unit_price
    unpaid = sorted((p for p in payments if p.status != "paid"), key=lambda p: p.seq)
    paid = sum((p.base_amount for p in payments if p.status == "paid"), decimal.Decimal("0"))
    remaining = sum((p.base_amount for p in unpaid), decimal.Decimal("0"))
    fees = sum((p.fee_amount for p in unpaid), decimal.Decimal("0"))
    today = _utcnow().date()
    value = _q(decimal.Decimal(price) * plan.units_total)
    return {
        "plan_id": plan.id,
        "units": plan.units_total,
        "vested_units": plan.vested_units,
        "locked_price": _q(plan.unit_price),
        "entry_price": _q(entry),
        "price": _q(decimal.Decimal(price)),
        "value": value,
        "paid_principal": _q(paid),
        "remaining_principal": _q(remaining),
        "remaining_fees": _q(fees),
        "equity": _q(value - remaining),
        "cost": _q(entry * plan.units_total - remaining),
        "gain": _q((decimal.Decimal(price) - entry) * plan.units_total),
        "installments_left": len(unpaid),
        "overdue": sum(1 for p in unpaid if p.due_date < today),
        "next_due": min((p.due_date for p in unpaid), default=None),
        "schedule": unpaid,
    }


async def holder_entry(
    session: AsyncSession, plan: InstallmentPlan
) -> tuple[dt.datetime, decimal.Decimal] | None:
    """When the plan's current holder took it over from another investor, and the price per
    unit they bought it at (None = they started the plan: their price is the one it locked).
    Payments made before that were the previous holder's.

    0042: a plan that changes hands records both on itself (``holder_since``/``entry_price``,
    also for a part that became a plan of its own, and for a provider or a recipient who took
    it outside the market); before that only the secondary trade told."""
    if plan.holder_since is not None and plan.entry_price is not None:
        return plan.holder_since, decimal.Decimal(plan.entry_price)
    row = (
        await session.execute(
            select(SecondaryTrade.created_at, SecondaryTrade.price_per_unit)
            .where(SecondaryTrade.plan_id == plan.id, SecondaryTrade.buyer_id == plan.investor_id)
            .order_by(SecondaryTrade.created_at.desc(), SecondaryTrade.id.desc())
            .limit(1)
        )
    ).first()
    return (row[0], decimal.Decimal(row[1])) if row is not None else None


async def holder_position(
    session: AsyncSession,
    plan: InstallmentPlan,
    payments: list[InstallmentPayment],
    price: decimal.Decimal,
) -> dict:
    """``position_figures`` for the plan's current holder, from their own entry price."""
    entry = await holder_entry(session, plan)
    return position_figures(plan, payments, price, entry[1] if entry else None)


# --- a part of a running plan changes hands (0042) ---------------------------- #
# Client (2026-11-08): the holder of a running plan can sell or send part of it (one unit, two,
# any number) on the secondary market, to a liquidity provider or to another person; the rest
# stays theirs. With ``units`` out of ``units_total`` (the SHARE), the new holder gets that share
# of everything: of what was paid (what they pay the seller for, plus or minus the price
# change), and of every payment still to come, as a plan of their own in their name with the
# same number of payments on the same dates. The seller's plan keeps the rest. Amounts are
# rounded to the cent and the last payment of each kind takes the rounding, so the two plans
# add up EXACTLY to the original: paid, still to pay, fees and units.
class SplitPayment:
    """One payment of the part being taken: its share of the original payment."""

    __slots__ = (
        "seq",
        "kind",
        "due_date",
        "status",
        "paid_at",
        "base_amount",
        "fee_amount",
        "total_amount",
        "vest_units",
    )

    def __init__(self, **values: object) -> None:
        for k, v in values.items():
            setattr(self, k, v)


def overdue_payments(
    payments: list[InstallmentPayment], today: dt.date | None = None
) -> list[InstallmentPayment]:
    """The plan's payments that are late: missed (``overdue``), or due before today and still
    unpaid. A payment due today is not late yet (the daily run charges it)."""
    today = today or _utcnow().date()
    return [
        p for p in payments if p.status != "paid" and (p.status == "overdue" or p.due_date < today)
    ]


def require_no_overdue(payments: list[InstallmentPayment], *, whose: str = "your") -> None:
    """A part of a plan (or, outside the market, the whole plan) changes hands only when no
    installment is late: the holder pays what is late first."""
    late = overdue_payments(payments)
    if late:
        total = _q(sum((p.total_amount for p in late), decimal.Decimal("0")))
        if whose == "your":
            message = (
                f"{len(late)} installment(s) of this plan are overdue ({total}). Pay them "
                "first, then you can sell or send part of the plan."
            )
        else:
            message = (
                "The seller has overdue installments on this plan, so part of it cannot change "
                "hands until they are paid."
            )
        raise AppError(
            "PLAN_OVERDUE",
            message,
            status_code=409,
            details={"overdue": len(late), "overdue_amount": str(total)},
        )


def _share_of(values: list[decimal.Decimal], share: decimal.Decimal) -> list[decimal.Decimal]:
    """The part's share of each amount, to the cent. Every one is rounded on its own and the
    LAST takes the rounding, so the parts add up to the share of the total. (If that ever left
    the last outside 0..its amount, the rounding is carried along instead.)"""
    if not values:
        return []
    target = _q(sum(values, decimal.Decimal("0")) * share)
    parts = [_q(v * share) for v in values[:-1]]
    last = target - sum(parts, decimal.Decimal("0"))
    if decimal.Decimal("0") <= last <= values[-1]:
        return [*parts, last]
    out: list[decimal.Decimal] = []
    running = done = decimal.Decimal("0")
    for v in values:
        running += v
        upto = _q(running * share)
        out.append(upto - done)
        done = upto
    return out


def _vest_share(vests: list[int], units: int, total: int) -> list[int]:
    """The part's units vesting on each payment: the share of the units vested so far, rounded
    down, payment by payment. Never more than the payment vests; adds up to ``units``."""
    out: list[int] = []
    running = done = 0
    for v in vests:
        running += v
        upto = units * running // total
        out.append(upto - done)
        done = upto
    if out and done != units:  # a plan whose vesting does not add up: the last payment completes it
        out[-1] += units - done
    return out


def split_figures(
    plan: InstallmentPlan, payments: list[InstallmentPayment], units: int
) -> list[SplitPayment]:
    """The part's payments: ``units`` of the plan's ``units_total``, every payment shared out.
    Paid payments and payments still to come are shared out separately, so the part's paid
    total and its still-to-pay total are each the exact share of the plan's."""
    ordered = sorted(payments, key=lambda p: p.seq)
    if units == plan.units_total:
        return [
            SplitPayment(
                seq=p.seq,
                kind=p.kind,
                due_date=p.due_date,
                status=p.status,
                paid_at=p.paid_at,
                base_amount=p.base_amount,
                fee_amount=p.fee_amount,
                total_amount=p.total_amount,
                vest_units=p.vest_units,
            )
            for p in ordered
        ]
    share = decimal.Decimal(units) / decimal.Decimal(plan.units_total)
    vests = _vest_share([int(p.vest_units) for p in ordered], units, plan.units_total)
    out = {
        p.seq: SplitPayment(
            seq=p.seq,
            kind=p.kind,
            due_date=p.due_date,
            status=p.status,
            paid_at=p.paid_at,
            vest_units=vest,
        )
        for p, vest in zip(ordered, vests, strict=True)
    }
    for group in (
        [p for p in ordered if p.status == "paid"],
        [p for p in ordered if p.status != "paid"],
    ):
        bases = _share_of([p.base_amount for p in group], share)
        fees = _share_of([p.fee_amount for p in group], share)
        for p, base, fee in zip(group, bases, fees, strict=True):
            row = out[p.seq]
            row.base_amount = base
            row.fee_amount = fee
            row.total_amount = base + fee
    return [out[p.seq] for p in ordered]


def part_figures(
    plan: InstallmentPlan,
    payments: list[InstallmentPayment],
    units: int,
    price: decimal.Decimal,
    entry_price: decimal.Decimal | None = None,
) -> dict:
    """``position_figures`` for ``units`` of the plan: what that part is worth at ``price``,
    its share of what was paid and of what is still to pay, and its schedule (the payments
    still to come, at the part's amounts). The whole plan gives ``position_figures``."""
    if units == plan.units_total:
        fig = position_figures(plan, payments, price, entry_price)
        fig["plan_units"] = plan.units_total
        return fig
    rows = split_figures(plan, payments, units)
    part = InstallmentPlan(
        id=plan.id,
        units_total=units,
        unit_price=plan.unit_price,
        vested_units=sum(r.vest_units for r in rows if r.status == "paid"),
    )
    fig = position_figures(part, rows, price, entry_price)  # type: ignore[arg-type]
    fig["plan_units"] = plan.units_total
    return fig


async def committed_units(session: AsyncSession, plan_id: uuid.UUID) -> dict[str, int]:
    """Units of a running plan already offered elsewhere: on its secondary-market listing and
    in open liquidity-provider exit requests. They cannot be offered again, or sent."""
    from app.models import LpExitRequest

    listed = await session.scalar(
        select(func.coalesce(func.sum(SecondaryListing.units_remaining), 0)).where(
            SecondaryListing.plan_id == plan_id, SecondaryListing.status == "active"
        )
    )
    lp_open = await session.scalar(
        select(func.coalesce(func.sum(LpExitRequest.units_remaining), 0)).where(
            LpExitRequest.plan_id == plan_id, LpExitRequest.status == "open"
        )
    )
    return {"listed": int(listed or 0), "lp_exit": int(lp_open or 0)}


async def free_plan_units(session: AsyncSession, plan: InstallmentPlan) -> int:
    """Units of the plan its holder can still sell or send."""
    held = await committed_units(session, plan.id)
    return max(0, plan.units_total - held["listed"] - held["lp_exit"])


def _ledger_move(
    session: AsyncSession,
    *,
    plan: InstallmentPlan,
    from_id: uuid.UUID,
    to_id: uuid.UUID,
    units: int,
    price: decimal.Decimal,
    reasons: tuple[str, str],
    fee_rate: decimal.Decimal,
    ref_id: uuid.UUID | None,
) -> None:
    """The units vested so far change hands (Σ per property conserved)."""
    if units <= 0:
        return
    session.add(
        OwnershipLedger(
            user_id=from_id,
            property_id=plan.property_id,
            investment_id=None,
            units=-units,
            unit_price=price,
            reason=reasons[0],
            ref_id=ref_id,
        )
    )
    session.add(
        OwnershipLedger(
            user_id=to_id,
            property_id=plan.property_id,
            investment_id=None,
            units=units,
            unit_price=price,
            reason=reasons[1],
            fee_rate=fee_rate,
            ref_id=ref_id,
        )
    )


async def split_plan(
    session: AsyncSession,
    *,
    plan: InstallmentPlan,
    payments: list[InstallmentPayment],
    units: int,
    to_user_id: uuid.UUID,
    entry_price: decimal.Decimal,
    ledger_price: decimal.Decimal,
    reasons: tuple[str, str],
    ref_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
) -> tuple[InstallmentPlan, list[InstallmentPayment]]:
    """Take ``units`` of a running plan out of it, as a new plan in ``to_user_id``'s name.

    The new plan has the same payments on the same dates, each at its share (``split_figures``):
    those already paid as paid, the rest to be charged from the new holder's wallet, who is
    reminded of them. The units vested so far under the part move in the ledger
    (``reasons``: the seller's row, the new holder's). The seller's plan keeps the rest of every
    payment and of the units. Nothing is charged here: the caller moves the money. The caller
    holds the plan's payment rows, the plan and the property (``_lock_plan_rows`` then the
    property), and has checked who may do this."""
    if plan.status != "active":
        raise AppError("PLAN_NOT_RUNNING", "This plan is not running.", status_code=409)
    if not 1 <= units < plan.units_total:
        raise AppError(
            "INVALID_UNITS",
            f"Choose between 1 and {plan.units_total - 1} unit(s) to take out of this plan.",
            status_code=422,
            details={"units_total": plan.units_total},
        )
    require_no_overdue(payments)
    rows = split_figures(plan, payments, units)
    moved_vested = sum(r.vest_units for r in rows if r.status == "paid")
    if await _holding(session, plan.investor_id, plan.property_id) < moved_vested:
        # the ledger and the plan disagree: refuse rather than move units that are not there
        raise AppError(
            "INVALID_STATE",
            "This plan cannot be divided right now. Please contact support.",
            status_code=409,
        )
    now = _utcnow()
    fee_rate = await settings_service.get_management_fee_pct(session)
    share = decimal.Decimal(units) / decimal.Decimal(plan.units_total)
    discount = _q(decimal.Decimal(plan.discount_amount or 0) * share)
    child = InstallmentPlan(
        id=uuid.uuid4(),
        investor_id=to_user_id,
        property_id=plan.property_id,
        units_total=units,
        unit_price=plan.unit_price,
        down_payment_pct=plan.down_payment_pct,
        duration_months=plan.duration_months,
        fee_rate=plan.fee_rate,
        # the new holder carries the CURRENT platform management-fee rate (Decision 2)
        management_fee_rate=fee_rate,
        vested_units=moved_vested,
        status="active",
        payment_method=plan.payment_method,
        discount_amount=discount,
        parent_plan_id=plan.id,
        holder_since=now,
        entry_price=_q(entry_price),
        created_at=now,
        updated_at=now,
    )
    session.add(child)
    await session.flush()  # the new plan exists before its payments point at it
    by_seq = {r.seq: r for r in rows}
    child_payments: list[InstallmentPayment] = []
    for p in sorted(payments, key=lambda x: x.seq):
        r = by_seq[p.seq]
        cp = InstallmentPayment(
            id=uuid.uuid4(),
            plan_id=child.id,
            seq=p.seq,
            kind=p.kind,
            due_date=p.due_date,
            base_amount=r.base_amount,
            fee_amount=r.fee_amount,
            total_amount=r.total_amount,
            vest_units=r.vest_units,
            status="paid" if p.status == "paid" else "scheduled",
            paid_at=p.paid_at if p.status == "paid" else None,
            reminder_sent_at=None,
        )
        session.add(cp)
        child_payments.append(cp)
        # the seller keeps the rest of the payment
        p.base_amount = p.base_amount - r.base_amount
        p.fee_amount = p.fee_amount - r.fee_amount
        p.total_amount = p.total_amount - r.total_amount
        p.vest_units = p.vest_units - r.vest_units
    from_id = plan.investor_id
    plan.units_total = plan.units_total - units
    plan.vested_units = plan.vested_units - moved_vested
    plan.discount_amount = decimal.Decimal(plan.discount_amount or 0) - discount
    plan.updated_at = now
    _ledger_move(
        session,
        plan=plan,
        from_id=from_id,
        to_id=to_user_id,
        units=moved_vested,
        price=ledger_price,
        reasons=reasons,
        fee_rate=fee_rate,
        ref_id=ref_id,
    )
    await session.flush()
    await write_audit(
        session,
        action="installment.plan.split",
        entity_type="installment_plan",
        entity_id=str(child.id),
        actor_id=actor_id,
        after={
            "from_plan_id": str(plan.id),
            "from_user_id": str(from_id),
            "to_user_id": str(to_user_id),
            "units": units,
            "seller_units_left": plan.units_total,
            "vested_moved": moved_vested,
            "entry_price": str(_q(entry_price)),
            "reasons": list(reasons),
        },
    )
    return child, child_payments


async def hand_over_plan(
    session: AsyncSession,
    *,
    plan: InstallmentPlan,
    payments: list[InstallmentPayment],
    to_user_id: uuid.UUID,
    entry_price: decimal.Decimal,
    ledger_price: decimal.Decimal,
    reasons: tuple[str, str],
    ref_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
) -> InstallmentPlan:
    """The whole running plan becomes ``to_user_id``'s (a liquidity provider, or the recipient
    of a transfer): the units vested so far move in the ledger and the unpaid payments keep their
    dates and amounts, charged from the new holder's wallet. Same locks as ``split_plan``."""
    if plan.status != "active":
        raise AppError("PLAN_NOT_RUNNING", "This plan is not running.", status_code=409)
    require_no_overdue(payments)
    vested = int(plan.vested_units or 0)
    if await _holding(session, plan.investor_id, plan.property_id) < vested:
        raise AppError(
            "INVALID_STATE",
            "This plan cannot change hands right now. Please contact support.",
            status_code=409,
        )
    now = _utcnow()
    fee_rate = await settings_service.get_management_fee_pct(session)
    from_id = plan.investor_id
    _ledger_move(
        session,
        plan=plan,
        from_id=from_id,
        to_id=to_user_id,
        units=vested,
        price=ledger_price,
        reasons=reasons,
        fee_rate=fee_rate,
        ref_id=ref_id,
    )
    plan.investor_id = to_user_id
    plan.management_fee_rate = fee_rate
    plan.holder_since = now
    plan.entry_price = _q(entry_price)
    plan.updated_at = now
    for p in payments:
        if p.status != "paid":
            p.status = "scheduled"
            p.reminder_sent_at = None
    await session.flush()
    await write_audit(
        session,
        action="installment.plan.handed_over",
        entity_type="installment_plan",
        entity_id=str(plan.id),
        actor_id=actor_id,
        after={
            "from_user_id": str(from_id),
            "to_user_id": str(to_user_id),
            "units": plan.units_total,
            "vested_moved": vested,
            "entry_price": str(_q(entry_price)),
            "reasons": list(reasons),
        },
    )
    return plan


async def take_plan_units(
    session: AsyncSession,
    *,
    plan: InstallmentPlan,
    payments: list[InstallmentPayment],
    units: int,
    to_user_id: uuid.UUID,
    entry_price: decimal.Decimal,
    ledger_price: decimal.Decimal,
    reasons: tuple[str, str],
    ref_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
) -> InstallmentPlan:
    """``units`` of the plan change hands: all of them hand the plan over, fewer split it.
    Returns the plan the new holder now has."""
    if units == plan.units_total:
        return await hand_over_plan(
            session,
            plan=plan,
            payments=payments,
            to_user_id=to_user_id,
            entry_price=entry_price,
            ledger_price=ledger_price,
            reasons=reasons,
            ref_id=ref_id,
            actor_id=actor_id,
        )
    child, _ = await split_plan(
        session,
        plan=plan,
        payments=payments,
        units=units,
        to_user_id=to_user_id,
        entry_price=entry_price,
        ledger_price=ledger_price,
        reasons=reasons,
        ref_id=ref_id,
        actor_id=actor_id,
    )
    return child


def schedule_rows(rows: list) -> list[dict]:
    """A schedule (payments, or a part's payments) as the API gives it: money as text."""
    return [
        {
            "seq": p.seq,
            "kind": p.kind,
            "due_date": p.due_date,
            "base_amount": str(p.base_amount),
            "fee_amount": str(p.fee_amount),
            "total_amount": str(p.total_amount),
            "status": p.status,
        }
        for p in rows
    ]


async def _active_listing_id(session: AsyncSession, plan_id: uuid.UUID) -> uuid.UUID | None:
    """The secondary-market listing that offers this plan's position, if it is for sale."""
    return await session.scalar(
        select(SecondaryListing.id).where(
            SecondaryListing.plan_id == plan_id, SecondaryListing.status == "active"
        )
    )


async def _plan_dict(session: AsyncSession, plan: InstallmentPlan) -> dict:
    """Serialize a plan with its payments AND its property (title/location/image/SPV), so the
    client can present the schedule under the property it belongs to."""
    payments = await _payments_for(session, plan.id)
    prop = await session.get(Property, plan.property_id)
    out = serialize_plan(plan, payments, prop)
    if plan.status == "active" and prop is not None:
        # what the position is worth today, and whether it is offered for sale
        entry = await holder_entry(session, plan)
        fig = position_figures(plan, payments, prop.unit_price, entry[1] if entry else None)
        out["position"] = {
            "price": str(fig["price"]),
            "entry_price": str(fig["entry_price"]),
            "value": str(fig["value"]),
            "cost": str(fig["cost"]),
            "paid_principal": str(fig["paid_principal"]),
            "remaining_principal": str(fig["remaining_principal"]),
            "remaining_fees": str(fig["remaining_fees"]),
            "equity": str(fig["equity"]),
            "gain": str(fig["gain"]),
        }
        out["listing_id"] = await _active_listing_id(session, plan.id)
        out["acquired_at"] = entry[0] if entry else None
        # what stands in the way of listing it now (a Nova pledge, a lock-up, a listing)
        from app.services import secondary_service  # it imports this module

        blocked, unlock = await secondary_service.position_block(session, plan, out["listing_id"])
        out["position"]["blocked"] = blocked
        out["position"]["lockup_until"] = unlock
    # A down-payment checkout still open: where to pay it (an Idempotency-Key replay gets it too).
    if plan.status == "pending_payment" and plan.payment_id:
        pay = await session.get(Payment, plan.payment_id)
        out["payment_id"] = plan.payment_id
        out["checkout_url"] = ((pay.raw_payload or {}) if pay else {}).get("checkout_url")
    return out


# --- create a plan (reserve allocation + build schedule + pay down payment) --- #
async def open_plan(
    session: AsyncSession,
    *,
    investor_id: uuid.UUID,
    property_id: uuid.UUID,
    amount: float,
    duration_months: int,
    idempotency_key: str,
    status: str,
    method: str,
    expected_unit_price: float | None = None,
) -> tuple[InstallmentPlan, Property, InstallmentPayment]:
    """Validate, lock the property, RESERVE the whole allocation and write the plan with its
    schedule — nothing paid yet. Returns the plan, the LOCKED property and the down payment."""
    if duration_months not in _DOWN_PCT:
        raise AppError(
            "INVALID_DURATION",
            f"Duration must be one of {sorted(_DOWN_PCT)} months.",
            status_code=422,
        )
    # an amount is money: cents first, or 3 units at 110.10 sent as the float
    # 330.29999999999995 would buy 2
    amount_dec = _q(decimal.Decimal(str(amount)))
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
    refuse_sample(prop)
    require_installments(prop)
    require_price(prop, expected_unit_price)  # the price a plan locks is one its investor saw
    if prop.unit_price <= 0:
        raise AppError("INVALID_PROPERTY", "Property has no unit price.", status_code=409)

    units_total = int(amount_dec // prop.unit_price)  # floor to whole units at the locked price
    # Same rule as a direct purchase: whole units worth at least the listing's minimum.
    if below_minimum(prop, units_total):
        raise minimum_error(prop)
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
    bases = schedule_bases(principal, duration_months)

    # Vest units ∝ each payment's base principal (Hamilton — sums EXACTLY to units_total).
    weights: list[tuple[Hashable, int]] = [(str(i), int(b * 100)) for i, b in enumerate(bases)]
    vest_split = hamilton(units_total, weights)

    # Reserve the whole allocation out of the pool now (the plan holds the unvested units).
    prop.available_units -= units_total

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
        status=status,
        payment_method=method,
        idempotency_key=idempotency_key,
    )
    session.add(plan)
    await session.flush()

    today = _utcnow().date()
    down_payment: InstallmentPayment | None = None
    for seq, base in enumerate(bases):
        fee_amount = fee_for(base, fee_rate)
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
            "payment_method": method,
            "status": status,
        },
    )
    assert down_payment is not None
    return plan, prop, down_payment


async def create_plan(
    session: AsyncSession,
    *,
    investor_id: uuid.UUID,
    property_id: uuid.UUID,
    amount: float,
    duration_months: int,
    idempotency_key: str,
    method: str = "wallet",
    success_url: str = "",
    cancel_url: str = "",
    ipn_url: str = "",
    expected_unit_price: float | None = None,
    pay_currency: str | None = None,
) -> dict:
    # Idempotency-Key replay -> the existing plan (no double reserve / double charge).
    existing = (
        await session.execute(
            select(InstallmentPlan).where(InstallmentPlan.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.investor_id != investor_id:
            # the plan was sold since (or the key is someone else's): it is not theirs to read
            raise AppError(
                "IDEMPOTENCY_KEY_REUSED",
                "This request key was already used for another plan.",
                status_code=409,
            )
        return await _plan_dict(session, existing)

    if method not in PLAN_METHODS:
        raise AppError(
            "INVALID_METHOD",
            "Pay the down payment from the wallet, by card, in crypto or with Pronova.",
            status_code=422,
        )
    # Fail fast on an unconfigured provider BEFORE reserving any units.
    if method in DIRECT_METHODS and not payment_service.provider_configured(method):
        provider = payment_service.provider_for(method)
        raise AppError(
            "PAYMENTS_NOT_CONFIGURED", f"{provider} is not configured yet.", status_code=503
        )

    plan, prop, down_payment = await open_plan(
        session,
        investor_id=investor_id,
        property_id=property_id,
        amount=amount,
        duration_months=duration_months,
        idempotency_key=idempotency_key,
        status="active" if method == "wallet" else "pending_payment",
        method=method,
        expected_unit_price=expected_unit_price,
    )
    if method == "wallet":
        # Pay the down payment now (atomic). INSUFFICIENT_FUNDS propagates -> the whole plan
        # rolls back (no reservation left behind).
        prop.investors_count = prop.investors_count + 1
        await _charge_payment(
            session,
            plan=plan,
            prop=prop,
            payment=down_payment,
            idempotency_key=f"{idempotency_key}:0",
        )
        return await _plan_dict(session, plan)

    # A hosted checkout pays the down payment and its webhook starts the plan. The units stay
    # held meanwhile, like a direct purchase's, and go back on sale if it is not paid in time.
    plan.reservation_expires_at = _utcnow() + RESERVATION_TTL
    due = down_payment.total_amount
    if method == "pronova":
        # Pronova (D5, as on a purchase): a discount off what is paid now — the down payment
        # and its fee. Platform-funded: the schedule, the vesting and the property's funding
        # keep the full amounts.
        pct = await settings_service.get_pronova_discount_pct(session)
        plan.discount_amount = _q(due * pct / _HUNDRED)
        due = _q(due - plan.discount_amount)
    checkout = await payment_service.create_plan_checkout(
        session,
        user_id=investor_id,
        plan_id=plan.id,
        amount=due,
        method=method,
        success_url=success_url,
        cancel_url=cancel_url,
        ipn_url=ipn_url,
        pay_currency=pay_currency,
    )
    plan.payment_id = checkout["payment_id"]
    await write_audit(
        session,
        action="installment.plan.reserved",
        entity_type="installment_plan",
        entity_id=str(plan.id),
        actor_id=investor_id,
        after={
            "via": method,
            "units": plan.units_total,
            "due_now": str(due),
            "discount": str(plan.discount_amount),
            "expires_at": plan.reservation_expires_at.isoformat(),
            "payment_id": str(checkout["payment_id"]),
        },
    )
    return await _plan_dict(session, plan)


# --- charge one payment (down payment or installment) ----------------------- #
async def _charge_payment(
    session: AsyncSession,
    *,
    plan: InstallmentPlan,
    prop: Property,
    payment: InstallmentPayment,
    idempotency_key: str,
    funded_by: str | None = None,
) -> None:
    """Debit the wallet (base + fee) and VEST the payment's units. Caller holds the property
    lock. Raises INSUFFICIENT_FUNDS BEFORE any write (the wallet check precedes the ledger
    writes) so a caller that catches it leaves no partial state.

    ``funded_by`` (card | crypto | pronova | sukuk): the payment was made outside the wallet —
    a down-payment checkout or a Nova Sukuk certificate — so nothing is debited; everything
    else (vesting, funding, cost basis, receipt) is the same."""
    if payment.status == "paid":
        return  # idempotent

    # the referring broker is credited below: both wallets, in the global lock order
    broker_id = await broker_service.referring_broker(session, plan.investor_id)
    if broker_id is not None:
        await wallet_service.lock_wallets(session, [plan.investor_id, broker_id])

    if funded_by is None:
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
    else:
        inv_wallet = (
            await session.execute(
                select(Wallet)
                .where(Wallet.user_id == plan.investor_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
    # Count the installment PRINCIPAL toward the investor's invested cost basis — parity with a
    # direct buy (investment_service adds the subtotal). The vested units already contribute to
    # the portfolio's current_value, so without this the portfolio reports a phantom gain.
    inv_wallet.total_invested = inv_wallet.total_invested + payment.base_amount

    # Vest this payment's units into the append-only ledger (real ownership), at the price
    # per unit their holder got in at: the plan's locked price, or, for an investor who bought
    # the position, the price they bought it at (they paid the seller the difference on every
    # unit, vested or not). It is what the holding's average cost is computed from.
    entry = await holder_entry(session, plan)
    vest_price = entry[1] if entry else plan.unit_price
    if payment.vest_units > 0:
        session.add(
            OwnershipLedger(
                user_id=plan.investor_id,
                property_id=plan.property_id,
                investment_id=None,
                units=payment.vest_units,
                unit_price=vest_price,
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

    # A referred client's broker earns the property's rate on the principal of each payment.
    await broker_service.accrue_commission(
        session,
        client_id=plan.investor_id,
        revenue_event_type=broker_service.REVENUE_INSTALLMENT,
        revenue_event_id=payment.id,
        revenue_amount=payment.base_amount,
        property_id=plan.property_id,
    )

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
                    unit_price=vest_price,
                    reason="installment_vest",
                    fee_rate=plan.management_fee_rate,
                )
            )
            plan.vested_units += short
        plan.status = "completed"
        plan.completed_at = _utcnow()

    # Payment receipt — in-app + email. Covers BOTH the manual "Pay now" and the cron
    # auto-charge (this is the single settle path), so every installment charged from the
    # wallet reaches the investor as a confirmation, not just a silent balance change.
    prop_title = prop.title
    paid_with = _PAID_WITH.get(funded_by, "from your wallet")
    if funded_by == "pronova" and plan.discount_amount:
        paid_with += f" (Pronova discount ${plan.discount_amount})"
    if plan.status == "completed":
        notif_title = "Installment plan completed"
        notif_msg = (
            f"Your final installment of ${payment.total_amount} for {prop_title} was paid "
            f"{paid_with}. All {plan.units_total} units are now fully vested — the plan "
            "is complete."
        )
    else:
        label = "down payment" if payment.seq == 0 else f"installment {payment.seq}"
        notif_msg = (
            f"Your {label} of ${payment.total_amount} for {prop_title} was paid {paid_with}. "
            f"{plan.vested_units} of {plan.units_total} units are now vested."
        )
        notif_title = "Installment paid"
    await notification_service.notify(
        session,
        user_id=plan.investor_id,
        type="installment",
        title=notif_title,
        message=notif_msg,
        email_category="investment_updates",
    )

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
            "funded_by": funded_by or "wallet",
        },
    )


# --- a down payment paid outside the wallet: start / release the plan ---------- #
# Lock order, as everywhere else in this module (pay_installment, run_due): the plan's payment
# rows, then the plan, then the property — never the plan before its payments.
async def _lock_plan_rows(
    session: AsyncSession, plan_id: uuid.UUID
) -> tuple[InstallmentPlan | None, list[InstallmentPayment]]:
    rows = (
        (
            await session.execute(
                select(InstallmentPayment)
                .where(InstallmentPayment.plan_id == plan_id)
                .order_by(InstallmentPayment.seq)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    plan = (
        await session.execute(
            select(InstallmentPlan)
            .where(InstallmentPlan.id == plan_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    return plan, list(rows)


async def _lock_property(session: AsyncSession, property_id: uuid.UUID) -> Property:
    return (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one()


async def _start_plan(
    session: AsyncSession,
    *,
    plan: InstallmentPlan,
    prop: Property,
    payments: list[InstallmentPayment],
    funded_by: str,
    reference: str,
) -> None:
    """The down payment arrived outside the wallet (a checkout's webhook, or staff approving a
    Nova Sukuk certificate): the plan starts. Caller holds the payment, plan and property locks.

    The schedule runs from TODAY: a plan approved days after it was requested (a Nova review)
    or paid late must not find its first installments already due, or overdue."""
    today = _utcnow().date()
    for p in payments:
        if p.status != "paid":
            p.status = "scheduled"
            p.due_date = today if p.seq == 0 else _add_months(today, p.seq)
            p.reminder_sent_at = None
    plan.status = "active"
    plan.reservation_expires_at = None
    plan.failure_reason = None
    plan.cancelled_at = None
    prop.investors_count = prop.investors_count + 1
    down = next(p for p in payments if p.seq == 0)
    await _charge_payment(
        session, plan=plan, prop=prop, payment=down, idempotency_key=reference, funded_by=funded_by
    )
    await write_audit(
        session,
        action="installment.plan.started",
        entity_type="installment_plan",
        entity_id=str(plan.id),
        after={"via": funded_by, "units": plan.units_total, "reference": reference},
    )


async def _release_plan(
    session: AsyncSession,
    *,
    plan: InstallmentPlan,
    prop: Property,
    payments: list[InstallmentPayment],
    status: str,
    reason: str,
) -> None:
    """A plan that never started gives its units back (its checkout failed or expired, or its
    Nova certificate was rejected). Caller holds the payment, plan and property locks."""
    restored = plan.units_total - plan.vested_units
    return_units(prop, restored, plan.unit_price)
    plan.status = status
    plan.failure_reason = reason
    plan.cancelled_at = _utcnow()
    plan.reservation_expires_at = None
    for p in payments:
        if p.status != "paid":
            p.status = "cancelled"
    await write_audit(
        session,
        action="installment.plan.released",
        entity_type="installment_plan",
        entity_id=str(plan.id),
        after={"status": status, "reason": reason, "restored_units": restored},
    )


async def _refund_down_payment(
    session: AsyncSession, *, payment: Payment, user_id: uuid.UUID, title: str, why: str
) -> None:
    """Money arrived for a down payment that cannot start its plan: it goes to the wallet."""
    captured = payment.amount_captured or payment.amount
    await wallet_service.credit(
        session,
        user_id=user_id,
        amount=captured,
        reference_id=payment.id,
        tx_type=TransactionType.deposit,
        description="Refund — installment plan could not start",
    )
    await notification_service.notify(
        session,
        user_id=user_id,
        type="installment",
        title="Installment plan refunded",
        message=f"{why} We refunded {captured} {payment.currency} to your wallet.",
        email_category="investment_updates",
    )
    await write_audit(
        session,
        action="installment.plan.reconciled_refunded",
        entity_type="payment",
        entity_id=str(payment.id),
        after={"refunded": str(captured), "plan": title},
    )


async def confirm_down_payment(session: AsyncSession, *, payment: Payment) -> dict:
    """A down-payment checkout was paid (payment_service._apply, under the payment row lock):
    start the plan. Paid after the plan was released: start it if its units are still free,
    else refund the money to the wallet — as when its plan cannot be found at all."""
    plan = None
    rows: list[InstallmentPayment] = []
    if payment.related_plan_id is not None:
        plan, rows = await _lock_plan_rows(session, payment.related_plan_id)
    if plan is None or not rows:
        await _refund_down_payment(
            session,
            payment=payment,
            user_id=payment.user_id,
            title="unknown",
            why="Your down payment reached us, but its installment plan no longer exists.",
        )
        return {"status": "processed", "result": "refunded"}
    if plan.status in ("active", "completed"):
        return {"status": "already_confirmed"}
    prop = await _lock_property(session, plan.property_id)
    funded_by = payment.payment_method or "card"
    reference = f"payment:{payment.id}"
    repriced = price_moved(prop, plan.unit_price)
    if plan.status == "pending_payment":
        if not (hold_lapsed(plan.reservation_expires_at) and repriced):
            await _start_plan(
                session,
                plan=plan,
                prop=prop,
                payments=rows,
                funded_by=funded_by,
                reference=reference,
            )
            return {"status": "processed", "result": "plan_started"}
        # Paid after the hold ran out (not swept yet) and the unit price has changed since:
        # the hold is over, exactly as if the sweep had already released it.
        await _release_plan(
            session,
            plan=plan,
            prop=prop,
            payments=rows,
            status="expired",
            reason="reservation_expired",
        )

    # A hold lasts 30 minutes, a hosted checkout can be paid for a day. A plan paid late
    # starts only at the price it locked: once the unit price has moved (0034), an old
    # checkout must not lock yesterday's price for the whole plan. The money is refunded.
    free = prop.status == PropertyStatus.active and prop.available_units >= plan.units_total
    if free and not repriced:
        retake_units(prop, plan.units_total, plan.unit_price)
        await _start_plan(
            session, plan=plan, prop=prop, payments=rows, funded_by=funded_by, reference=reference
        )
        await write_audit(
            session,
            action="installment.plan.reconciled_started",
            entity_type="installment_plan",
            entity_id=str(plan.id),
            after={"payment_id": str(payment.id)},
        )
        return {"status": "processed", "result": "reconciled_started"}

    plan.failure_reason = "price_changed_refunded" if free else "units_unavailable_refunded"
    await _refund_down_payment(
        session,
        payment=payment,
        user_id=plan.investor_id,
        title=prop.title,
        why=(
            f"The unit price of {prop.title} changed before your down payment confirmed, so "
            "the plan did not start. You can start a new plan at the new price."
            if free
            else f"The units of {prop.title} were taken before your down payment confirmed."
        ),
    )
    return {"status": "processed", "result": "refunded"}


async def release_plan_for_payment(
    session: AsyncSession, *, payment: Payment, reason: str = "payment_failed"
) -> dict:
    """A down-payment checkout failed or expired at the provider: release the plan's units."""
    if payment.related_plan_id is None:
        return {"status": "ignored_no_plan"}
    plan, rows = await _lock_plan_rows(session, payment.related_plan_id)
    if plan is None or plan.status != "pending_payment":
        return {"status": "noop"}
    prop = await _lock_property(session, plan.property_id)
    await _release_plan(
        session, plan=plan, prop=prop, payments=rows, status="cancelled", reason=reason
    )
    return {"status": "released"}


async def expire_pending_plans(session: AsyncSession, *, now: dt.datetime | None = None) -> int:
    """Release the units of plans whose down-payment checkout was not paid in time (the same
    window as a direct purchase). A webhook starting the same plan first wins: the status is
    checked again under the locks."""
    cutoff = now or _utcnow()
    candidates = (
        (
            await session.execute(
                select(InstallmentPlan.id).where(
                    InstallmentPlan.status == "pending_payment",
                    InstallmentPlan.reservation_expires_at < cutoff,
                )
            )
        )
        .scalars()
        .all()
    )
    released = 0
    for plan_id in candidates:
        plan, rows = await _lock_plan_rows(session, plan_id)
        if plan is None or plan.status != "pending_payment":
            continue
        if plan.reservation_expires_at is None or plan.reservation_expires_at >= cutoff:
            continue
        prop = await _lock_property(session, plan.property_id)
        await _release_plan(
            session,
            plan=plan,
            prop=prop,
            payments=rows,
            status="expired",
            reason="reservation_expired",
        )
        released += 1
    return released


async def start_sukuk_plan(
    session: AsyncSession, *, plan_id: uuid.UUID, certificate_id: uuid.UUID
) -> InstallmentPlan:
    """Staff approved the Nova Sukuk certificate that pays this plan's down payment."""
    plan, rows = await _lock_plan_rows(session, plan_id)
    if plan is None or plan.status != "pending_review":
        raise AppError(
            "INVALID_TRANSITION",
            "This plan is not waiting for a Nova certificate.",
            status_code=409,
        )
    prop = await _lock_property(session, plan.property_id)
    await _start_plan(
        session,
        plan=plan,
        prop=prop,
        payments=rows,
        funded_by="sukuk",
        reference=f"sukuk:{certificate_id}",
    )
    return plan


async def cancel_sukuk_plan(
    session: AsyncSession, *, plan_id: uuid.UUID, reason: str
) -> InstallmentPlan | None:
    """Staff rejected the Nova Sukuk certificate: the plan never starts, its units go back."""
    plan, rows = await _lock_plan_rows(session, plan_id)
    if plan is None or plan.status != "pending_review":
        return plan
    prop = await _lock_property(session, plan.property_id)
    await _release_plan(
        session, plan=plan, prop=prop, payments=rows, status="cancelled", reason=reason
    )
    return plan


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
        return await _plan_dict(session, plan)
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
    return await _plan_dict(session, plan)


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
        out.append(await _plan_dict(session, plan))
    return out


# --- branded schedule PDF (Task 6) ------------------------------------------ #
def _payment_label(p: InstallmentPayment) -> str:
    if p.kind == "downpayment":
        return "Down payment"
    if p.kind == "final":
        return f"Final (Month {p.seq})"
    return f"Month {p.seq}"


async def _schedule_facts(
    session: AsyncSession, *, investor_id: uuid.UUID, plan_id: uuid.UUID
) -> dict:
    """What the schedule PDF and spreadsheet show, summed from the real schedule rows (so the
    two files always agree); 404 if the plan isn't the caller's."""
    plan = await session.get(InstallmentPlan, plan_id)
    if plan is None or plan.investor_id != investor_id:
        raise AppError("NOT_FOUND", "Installment plan not found.", status_code=404)
    payments = sorted(await _payments_for(session, plan.id), key=lambda x: x.seq)
    prop = await session.get(Property, plan.property_id)
    if prop is None:
        raise AppError("PROPERTY_NOT_FOUND", "Property not found.", status_code=404)
    user = await session.get(User, investor_id)
    holder = (user.full_name if user and user.full_name else (user.email if user else "")) or "-"

    contract = sum((p.base_amount for p in payments), decimal.Decimal("0"))
    fees = sum((p.fee_amount for p in payments), decimal.Decimal("0"))
    paid = sum((p.total_amount for p in payments if p.status == "paid"), decimal.Decimal("0"))
    unpaid = sorted((p for p in payments if p.status != "paid"), key=lambda x: x.due_date)
    if unpaid:
        next_due = long_date(unpaid[0].due_date, "%b %d, %Y")
    else:
        next_due = "Completed" if plan.status == "completed" else "-"
    return {
        "plan": plan,
        "prop": prop,
        "holder": holder,
        "payments": payments,
        "contract": contract,
        "fees": fees,
        "grand": contract + fees,
        "paid": paid,
        "remaining": contract + fees - paid,
        "next_due": next_due,
        "plan_ref": ("CMX-INS-" + str(plan.id)[:8]).upper(),
        "issued": _utcnow(),
        "slug": prop.slug or str(prop.id),
    }


async def build_schedule_pdf(
    session: AsyncSession, *, investor_id: uuid.UUID, plan_id: uuid.UUID
) -> tuple[str, bytes]:
    """Return (filename, pdf_bytes) — the caller's own installment plan as a branded PDF
    (official design + logo). All figures are server-authoritative, summed from the real
    schedule rows; 404 if the plan isn't the caller's."""
    f = await _schedule_facts(session, investor_id=investor_id, plan_id=plan_id)
    plan, prop = f["plan"], f["prop"]

    def money(d: decimal.Decimal) -> str:
        return f"${d:,.2f}"

    rows = [
        {
            "label": _payment_label(p),
            "due": long_date(p.due_date, "%b %d, %Y"),
            "base": money(p.base_amount),
            "fee": money(p.fee_amount),
            "total": money(p.total_amount),
            "status": p.status.capitalize(),
        }
        for p in f["payments"]
    ]

    pdf = installment_pdf.render_schedule_pdf(
        holder=f["holder"],
        property_title=prop.title,
        location=prop.location or "-",
        spv=prop.spv_name or f"{prop.title} SPV",
        status=plan.status,
        units_total=plan.units_total,
        vested_units=plan.vested_units,
        unit_price=money(plan.unit_price),
        down_payment_pct=plan.down_payment_pct,
        duration_months=plan.duration_months,
        fee_rate=str(plan.fee_rate),
        contract_value=money(f["contract"]),
        total_fees=money(f["fees"]),
        grand_total=money(f["grand"]),
        total_paid=money(f["paid"]),
        remaining_balance=money(f["remaining"]),
        next_due=f["next_due"],
        plan_ref=f["plan_ref"],
        issued=long_date(f["issued"], "%b %d, %Y"),
        rows=rows,
    )
    return f"installment-schedule-{f['slug']}.pdf", pdf


async def build_schedule_xlsx(
    session: AsyncSession, *, investor_id: uuid.UUID, plan_id: uuid.UUID
) -> tuple[str, bytes]:
    """The same plan as the PDF, as an Excel workbook (figures as numbers, dates as dates), for
    an investor who wants to work with their schedule; 404 if the plan isn't the caller's."""
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    f = await _schedule_facts(session, investor_id=investor_id, plan_id=plan_id)
    plan, prop = f["plan"], f["prop"]
    money = "#,##0.00"
    head_fill = PatternFill("solid", fgColor="0F6E4C")
    head_font = Font(bold=True, color="FFFFFF")

    wb = Workbook()
    ws = wb.active
    ws.title = tr("Installment schedule")
    meta = [
        ("Capimax PropShare — Installment schedule", None, None),
        ("Holder", f["holder"], None),
        ("Property", prop.title, None),
        ("Location", prop.location or "-", None),
        ("Plan reference", f["plan_ref"], None),
        ("Status", status_text(plan.status.capitalize()), None),
        ("Units", plan.units_total, None),
        ("Units vested", plan.vested_units, None),
        ("Unit price (USD)", plan.unit_price, money),
        ("Down payment (%)", plan.down_payment_pct, None),
        ("Duration (months)", plan.duration_months, None),
        ("Installment fee (% per payment)", plan.fee_rate, None),
        ("Contract value (USD)", f["contract"], money),
        ("Total fees (USD)", f["fees"], money),
        ("Grand total (USD)", f["grand"], money),
        ("Paid so far (USD)", f["paid"], money),
        ("Remaining (USD)", f["remaining"], money),
        ("Next due", tr(f["next_due"]), None),
        ("Issued (UTC)", f["issued"].strftime("%Y-%m-%d %H:%M"), None),
    ]
    for label, value, fmt in meta:
        ws.append([tr(label), value])
        if fmt:
            ws.cell(row=ws.max_row, column=2).number_format = fmt
    ws["A1"].font = Font(bold=True, size=14, color="0F6E4C")
    for row in ws.iter_rows(min_row=2, max_row=len(meta), max_col=1):
        row[0].font = Font(bold=True)
    ws.append([])

    header = ["Payment", "Due date", "Principal (USD)", "Fee (USD)", "Total (USD)", "Status"]
    ws.append([tr(h) for h in header])
    head_row = ws.max_row
    for cell in ws[head_row]:
        cell.font, cell.fill = head_font, head_fill
    for p in f["payments"]:
        ws.append(
            [
                tr(_payment_label(p)),
                p.due_date,
                p.base_amount,
                p.fee_amount,
                p.total_amount,
                status_text(p.status.capitalize()),
            ]
        )
        ws.cell(row=ws.max_row, column=2).number_format = "yyyy-mm-dd"
        for col in (3, 4, 5):
            ws.cell(row=ws.max_row, column=col).number_format = money
    ws.freeze_panes = ws.cell(row=head_row + 1, column=1)
    for col, width in zip("ABCDEF", (34, 22, 16, 13, 15, 12), strict=True):
        ws.column_dimensions[col].width = width
    sheet_direction(ws)

    buf = io.BytesIO()
    wb.save(buf)
    return f"installment-schedule-{f['slug']}.xlsx", buf.getvalue()


async def close_stale_position_listings(
    session: AsyncSession, *, now: dt.datetime | None = None
) -> int:
    """Close the listings of positions whose plan is no longer running. Such a listing cannot
    be bought anyway (the purchase checks the plan); this keeps the seller's list honest, and
    tells the seller."""
    running = select(InstallmentPlan.id).where(InstallmentPlan.status == "active")
    stale = (
        await session.execute(
            select(SecondaryListing, InstallmentPlan.status, Property.title)
            .join(InstallmentPlan, InstallmentPlan.id == SecondaryListing.plan_id)
            .join(Property, Property.id == SecondaryListing.property_id)
            .where(
                SecondaryListing.plan_id.is_not(None),
                SecondaryListing.status == "active",
                SecondaryListing.plan_id.not_in(running),
            )
            .with_for_update(skip_locked=True, of=SecondaryListing)
        )
    ).all()
    for listing, plan_status, title in stale:
        listing.status = "cancelled"
        listing.cancelled_at = now or _utcnow()
        await write_audit(
            session,
            action="secondary.position_listing_closed",
            entity_type="secondary_listing",
            entity_id=str(listing.id),
            after={"plan_id": str(listing.plan_id), "plan_status": plan_status},
        )
        why = (
            "is now fully paid: its units are ordinary units, which you can list for sale like "
            "any others"
            if plan_status == "completed"
            else "is no longer running"
        )
        await notification_service.notify(
            session,
            user_id=listing.seller_id,
            type="secondary",
            title="Position listing closed",
            message=(
                f"Your listing of the installment position in {title} was closed: the plan {why}."
            ),
            email_category="investment_updates",
        )
    return len(stale)


# --- due-payment cron (admin OR X-Cron-Secret) ------------------------------ #
def _closed_accounts():
    """The accounts that are closed (account_service), as a subquery: nothing is charged to
    them and they are not reminded. What their wallets hold may be owed to beneficiaries."""
    return select(User.id).where(User.closed_at.is_not(None))


async def run_due(session: AsyncSession, *, now: dt.datetime | None = None) -> dict:
    """Idempotent sweep (FOR UPDATE SKIP LOCKED): send due-soon reminders, then charge due
    installments from the wallet. A payment that can't be charged (insufficient balance) is
    marked ``overdue`` and the investor is notified — GRACE + reminder, NO auto-forfeit and
    NO late fee (the UI states neither; see DECISIONS.md). Overdue rows are retried next run."""
    now = now or _utcnow()
    today = now.date()
    remind_cutoff = today + dt.timedelta(days=_REMINDER_DAYS)

    # Pass 0 — a position offered for sale whose plan has since been paid off is no longer a
    # position (its units are ordinary units now): its listing closes. Done first, before any
    # plan row is locked: a purchase locks the listing before the plan, so must this.
    await close_stale_position_listings(session, now=now)

    # Pass 1 — reminders for upcoming (not-yet-due) installments of active plans.
    reminders = 0
    rows = (
        await session.execute(
            # the plan's holder as a column, not the plan itself: an entity loaded here would
            # stay in the session and Pass 2 would get it back without its row being re-read
            select(InstallmentPayment, InstallmentPlan.investor_id)
            .join(InstallmentPlan, InstallmentPayment.plan_id == InstallmentPlan.id)
            .where(
                InstallmentPayment.status == "scheduled",
                InstallmentPayment.reminder_sent_at.is_(None),
                InstallmentPayment.due_date <= remind_cutoff,
                InstallmentPayment.due_date >= today,
                InstallmentPayment.seq > 0,
                InstallmentPlan.status == "active",
                InstallmentPlan.investor_id.not_in(_closed_accounts()),
            )
            .with_for_update(skip_locked=True, of=InstallmentPayment)
        )
    ).all()
    for payment, investor_id in rows:
        await notification_service.notify(
            session,
            user_id=investor_id,
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
                .join(InstallmentPlan, InstallmentPlan.id == InstallmentPayment.plan_id)
                .where(
                    InstallmentPayment.status.in_(("scheduled", "overdue")),
                    InstallmentPayment.due_date <= today,
                    InstallmentPayment.seq > 0,
                    # a plan that has not started (0032) is not charged, nor its rows locked
                    InstallmentPlan.status == "active",
                    # a closed account's wallet is left as it is: its plan waits for staff
                    InstallmentPlan.investor_id.not_in(_closed_accounts()),
                )
                .with_for_update(skip_locked=True, of=InstallmentPayment)
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
                # the row as it is NOW, under its lock: its holder may have paid an installment
                # early, or sold the position, since this session first saw the plan
                .execution_options(populate_existing=True)
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
