"""Distribution engine (Phase 6) — pro-rata returns + management-fee withholding.

One admin-triggered run pays every investor their share of a gross pool, all in ONE
atomic transaction:

  * **Pro-rata by units**, Hamilton largest-remainder so ``Σ payouts == gross_pool``
    exactly to the cent (computed in integer cents — no float, deterministic).
  * **Management fee** (rental only) withheld from each gross share at the investor's
    **snapshot rate** (``investments.management_fee_rate`` frozen at purchase) ×
    period fraction; the fee is retained as recorded revenue (no platform wallet in
    v1), the **net** is credited to the wallet.
  * **Idempotent**: UNIQUE(property_id, period_key) refuses a re-run of a period
    (409); UNIQUE(distribution_id, user_id) prevents a double-pay within a run.
  * **Atomic**: lock order property → wallet, wallets locked in sorted user_id order,
    ownership frozen via FOR UPDATE on the property; any failure rolls the run back
    whole (no partial credits).
  * **Family** (record-only): a group owner's net is split among members by
    allocated_units (Hamilton, exact) into family_return_allocations; the money still
    lands in the owner's wallet.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections.abc import Hashable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import (
    Distribution,
    DistributionItem,
    FamilyGroup,
    FamilyMember,
    FamilyReturnAllocation,
    FamilyTransfer,
    InstallmentPlan,
    Property,
)
from app.models.base import TransactionType
from app.models.investments import OwnershipLedger
from app.services import broker_service, notification_service, wallet_service

_CENTS = decimal.Decimal("0.01")
_VALID_KINDS = {"rental", "appreciation", "other"}


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _to_cents(amount: decimal.Decimal) -> int:
    return int((amount * 100).to_integral_value(rounding=decimal.ROUND_HALF_UP))


def _from_cents(cents: int) -> decimal.Decimal:
    return (decimal.Decimal(cents) / 100).quantize(_CENTS)


def hamilton(pool_cents: int, weights: list[tuple[Hashable, int]]) -> dict[Hashable, int]:
    """Split ``pool_cents`` across weighted keys so the parts sum EXACTLY to the pool.

    Largest-remainder method, integer-exact and deterministic: floor each ideal
    share, then hand the leftover cents one-by-one to the largest remainders (ties
    broken by weight desc, then key asc). Returns {key: cents}.
    """
    total_weight = sum(w for _k, w in weights)
    if total_weight <= 0:
        return {k: 0 for k, _w in weights}
    floors: dict[Hashable, int] = {}
    remainders: list[tuple[int, int, Hashable]] = []  # (remainder_num, weight, key)
    allocated = 0
    for key, w in weights:
        num = pool_cents * w
        floor = num // total_weight
        floors[key] = floor
        allocated += floor
        remainders.append((num % total_weight, w, key))
    leftover = pool_cents - allocated
    # Largest remainder first; deterministic tie-break: bigger weight, then smaller key.
    remainders.sort(key=lambda t: (-t[0], -t[1], str(t[2])))
    for i in range(leftover):
        floors[remainders[i][2]] += 1
    return floors


async def _ownership(session: AsyncSession, property_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
    """Rental-yield-eligible units per user from the append-only ownership ledger (units > 0).

    Group 6: units vested under an ACTIVE (pre-handover) installment plan are EXCLUDED — a
    partially-vested installment holder earns NO rental yield until the final payment
    (handover), at which point the plan is 'completed' and its units become yield-eligible.
    """
    res = await session.execute(
        select(OwnershipLedger.user_id, func.coalesce(func.sum(OwnershipLedger.units), 0))
        .where(OwnershipLedger.property_id == property_id)
        .group_by(OwnershipLedger.user_id)
    )
    ledger = {uid: int(units) for uid, units in res.all()}

    pre_handover = await session.execute(
        select(
            InstallmentPlan.investor_id, func.coalesce(func.sum(InstallmentPlan.vested_units), 0)
        )
        .where(InstallmentPlan.property_id == property_id, InstallmentPlan.status == "active")
        .group_by(InstallmentPlan.investor_id)
    )
    for uid, vested in pre_handover.all():
        if uid in ledger:
            ledger[uid] -= int(vested)

    rows = [(uid, units) for uid, units in ledger.items() if units > 0]
    rows.sort(key=lambda r: str(r[0]))  # deterministic + sorted lock order
    return rows


async def _fee_base_per_user(
    session: AsyncSession, property_id: uuid.UUID
) -> dict[uuid.UUID, decimal.Decimal]:
    """Annual management-fee base per owner, derived from the **ownership ledger** using
    the **per-row fee_rate stamped at acquisition** (Decision 2). Each acquisition row
    contributes ``units × unit_price × fee_rate/100`` at the rate that owner consented
    to — original investors keep their agreed rate, LP/secondary owners carry the
    platform rate stamped when they acquired. This is NEVER a global re-derive, so no
    owner's agreed fee changes retroactively.

    Sales can't be attributed to a specific acquisition lot (no per-lot cost basis), so
    the consented liability is reduced **proportionally** to units still held:
    ``fee_base = Σ(acquisition rows) × (net_units_held / total_units_acquired)``.
    A row with NULL fee_rate (legacy/unbackfillable) contributes 0 — no guessed fee.
    """
    res = await session.execute(
        select(
            OwnershipLedger.user_id,
            OwnershipLedger.units,
            OwnershipLedger.unit_price,
            OwnershipLedger.fee_rate,
        ).where(OwnershipLedger.property_id == property_id)
    )
    acc: dict[uuid.UUID, dict[str, decimal.Decimal]] = {}
    for uid, units, price, rate in res.all():
        u = int(units)
        a = acc.setdefault(
            uid, {"gross": decimal.Decimal(0), "acq": decimal.Decimal(0), "net": decimal.Decimal(0)}
        )
        a["net"] += decimal.Decimal(u)
        if u > 0:
            r = decimal.Decimal(rate) if rate is not None else decimal.Decimal(0)
            a["gross"] += decimal.Decimal(u) * decimal.Decimal(price) * r / decimal.Decimal(100)
            a["acq"] += decimal.Decimal(u)
    out: dict[uuid.UUID, decimal.Decimal] = {}
    for uid, a in acc.items():
        if a["acq"] > 0 and a["net"] > 0:
            out[uid] = a["gross"] * (a["net"] / a["acq"])
    return out


def _check_inputs(
    kind: str, period_key: str, period_start: dt.date, period_end: dt.date, gross_pool
) -> None:
    if kind not in _VALID_KINDS:
        raise AppError(
            "INVALID_KIND", f"kind must be one of {sorted(_VALID_KINDS)}", status_code=422
        )
    if not str(period_key or "").strip():
        raise AppError("INVALID_PERIOD", "Name the period (for example 2026-10).", status_code=422)
    if gross_pool <= 0:
        raise AppError("INVALID_AMOUNT", "gross_pool must be positive.", status_code=422)
    if period_end < period_start:
        raise AppError("INVALID_PERIOD", "The period cannot end before it starts.", status_code=422)


def period_days(period_start: dt.date, period_end: dt.date) -> int:
    """Days in a period, both dates included: 1 to 30 September is 30 days, a calendar year
    365. Investors see the period's last day as its date, so the last day is part of it."""
    return (period_end - period_start).days + 1


async def pool_from_yield(
    session: AsyncSession,
    *,
    property_id: uuid.UUID,
    annual_yield_pct: decimal.Decimal,
    period_start: dt.date,
    period_end: dt.date,
) -> dict:
    """The gross pool an annual yield pays for a period: the yield-eligible units at the
    property's unit price, times the yearly rate, times the period's share of a year (to
    the cent). For staff who think of a distribution as "8% a year" rather than an amount."""
    if annual_yield_pct <= 0 or annual_yield_pct > 100:
        raise AppError(
            "INVALID_AMOUNT",
            "The yield is a yearly percentage above 0 and up to 100.",
            status_code=422,
        )
    if period_end < period_start:
        raise AppError("INVALID_PERIOD", "The period cannot end before it starts.", status_code=422)
    prop = await session.get(Property, property_id)
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    units = sum(u for _uid, u in await _ownership(session, property_id))
    if not units:
        raise AppError("NO_OWNERS", "No confirmed unit owners to distribute to.", status_code=422)
    days = period_days(period_start, period_end)
    value = decimal.Decimal(prop.unit_price) * units
    pool = (value * annual_yield_pct / 100 * days / 365).quantize(
        _CENTS, rounding=decimal.ROUND_HALF_UP
    )
    if pool <= 0:
        raise AppError("INVALID_AMOUNT", "That yield pays less than a cent.", status_code=422)
    return {
        "pool": pool,
        "units": units,
        "unit_price": decimal.Decimal(prop.unit_price),
        "value": value,
        "days": days,
        "annual_yield_pct": annual_yield_pct,
    }


async def _split(
    session: AsyncSession,
    *,
    property_id: uuid.UUID,
    kind: str,
    period_start: dt.date,
    period_end: dt.date,
    gross_pool: decimal.Decimal,
) -> list[tuple[uuid.UUID, int, decimal.Decimal, decimal.Decimal, decimal.Decimal]]:
    """Each owner's ``(user_id, units, gross, fee, net)``, sorted by user_id: the gross pool
    pro rata to the yield-eligible units (exact to the cent), less the rental management fee
    at each owner's stamped rate for the period's fraction of a year, never more than the
    gross. The ONE computation behind a run and its preview."""
    owners = await _ownership(session, property_id)
    if not owners:
        raise AppError("NO_OWNERS", "No confirmed unit owners to distribute to.", status_code=422)
    gross_cents = hamilton(_to_cents(gross_pool), [(uid, units) for uid, units in owners])
    period_fraction = decimal.Decimal(period_days(period_start, period_end)) / decimal.Decimal(365)
    fee_base = await _fee_base_per_user(session, property_id) if kind == "rental" else {}
    lines = []
    for uid, units in owners:  # sorted by user_id -> deterministic wallet lock order
        gross = _from_cents(gross_cents[uid])
        fee = decimal.Decimal("0")
        if kind == "rental" and uid in fee_base:
            fee = (fee_base[uid] * period_fraction).quantize(_CENTS)
            if fee > gross:
                fee = gross  # never withhold more than the gross share
        lines.append((uid, units, gross, fee, gross - fee))
    return lines


async def preview_distribution(
    session: AsyncSession,
    *,
    property_id: uuid.UUID,
    kind: str,
    period_key: str,
    period_start: dt.date,
    period_end: dt.date,
    gross_pool: decimal.Decimal,
) -> dict:
    """What ``run_distribution`` would pay with these inputs, writing nothing: each owner's
    units, gross, fee and net, the totals, and whether the period was distributed already."""
    _check_inputs(kind, period_key, period_start, period_end, gross_pool)
    prop = await session.get(Property, property_id)
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    already = await session.scalar(
        select(Distribution.id).where(
            Distribution.property_id == property_id, Distribution.period_key == period_key
        )
    )
    lines = await _split(
        session,
        property_id=property_id,
        kind=kind,
        period_start=period_start,
        period_end=period_end,
        gross_pool=gross_pool,
    )
    return {
        "property": prop,
        "already_distributed": already is not None,
        "lines": lines,
        "investors": len(lines),
        "units": sum(units for _u, units, _g, _f, _n in lines),
        "gross": sum((g for _u, _units, g, _f, _n in lines), decimal.Decimal("0")),
        "fee": sum((f for _u, _units, _g, f, _n in lines), decimal.Decimal("0")),
        "net": sum((n for _u, _units, _g, _f, n in lines), decimal.Decimal("0")),
    }


async def run_distribution(
    session: AsyncSession,
    *,
    property_id: uuid.UUID,
    kind: str,
    period_key: str,
    period_start: dt.date,
    period_end: dt.date,
    gross_pool: decimal.Decimal,
    created_by: uuid.UUID | None,
    idempotency_key: str | None = None,
) -> dict:
    _check_inputs(kind, period_key, period_start, period_end, gross_pool)

    # Freeze ownership: lock the property row so no invest changes units mid-run.
    prop = (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)

    # Idempotency layer 1: a period is distributed at most once.
    dupe = await session.scalar(
        select(Distribution.id).where(
            Distribution.property_id == property_id, Distribution.period_key == period_key
        )
    )
    if dupe is not None:
        raise AppError(
            "DISTRIBUTION_EXISTS",
            f"A distribution for period '{period_key}' already exists for this property.",
            status_code=409,
        )

    lines = await _split(
        session,
        property_id=property_id,
        kind=kind,
        period_start=period_start,
        period_end=period_end,
        gross_pool=gross_pool,
    )
    owners = [(uid, units) for uid, units, _g, _f, _n in lines]

    distribution = Distribution(
        property_id=property_id,
        kind=kind,
        period_key=period_key,
        period_start=period_start,
        period_end=period_end,
        gross_pool=gross_pool.quantize(_CENTS),
        created_by=created_by,
        idempotency_key=idempotency_key,
        status="pending",
    )
    session.add(distribution)
    await session.flush()  # assign distribution.id

    total_net = decimal.Decimal("0")
    total_fee = decimal.Decimal("0")
    units_by_user = dict(owners)

    # Phase-11 hook: a rental mgmt fee withheld on a referred client's units is platform
    # revenue → the referring broker is credited in THIS tx. Pre-lock the union of owner
    # wallets + their referring brokers in the GLOBAL sorted order so the extra broker
    # credits can't violate the lock hierarchy (no deadlock across concurrent runs).
    broker_ids: list[uuid.UUID] = []
    if kind == "rental":
        for uid, _u in owners:
            b = await broker_service.referring_broker(session, uid)
            if b is not None:
                broker_ids.append(b)
    await wallet_service.lock_wallets(session, [uid for uid, _u in owners] + broker_ids)

    for uid, units, gross, fee, net in lines:  # sorted by user_id -> wallet lock order

        txn_id: uuid.UUID | None = None
        if net > 0:
            wallet = await wallet_service.credit(
                session,
                user_id=uid,
                amount=net,
                reference_id=distribution.id,
                tx_type=TransactionType.return_,
                description=f"Return — {prop.title} ({period_key})",
            )
            wallet.total_returns = wallet.total_returns + net

        item = DistributionItem(
            distribution_id=distribution.id,
            user_id=uid,
            units=units,
            gross_amount=gross,
            management_fee=fee,
            net_amount=net,
            transaction_id=txn_id,
        )
        session.add(item)
        if net > 0:
            await _allocate_family(session, distribution.id, uid, net, property_id, units)
        if fee > 0:
            # The withheld mgmt fee is the platform-revenue event; accrue the broker's
            # commission against THIS item (idempotent on item.id; no-op if not referred).
            await session.flush()  # assign item.id
            await broker_service.accrue_commission(
                session,
                client_id=uid,
                revenue_event_type=broker_service.REVENUE_MGMT_FEE,
                revenue_event_id=item.id,
                revenue_amount=fee,
            )
        total_net += net
        total_fee += fee

    distribution.total_net = total_net.quantize(_CENTS)
    distribution.total_management_fee = total_fee.quantize(_CENTS)
    distribution.status = "completed"
    distribution.completed_at = _utcnow()

    await write_audit(
        session,
        action="distribution.run",
        entity_type="distribution",
        entity_id=str(distribution.id),
        actor_id=created_by,
        after={
            "property_id": str(property_id),
            "period_key": period_key,
            "gross_pool": str(distribution.gross_pool),
            "total_net": str(distribution.total_net),
            "total_management_fee": str(distribution.total_management_fee),
            "investors": len(owners),
        },
    )
    for uid in units_by_user:
        await notification_service.notify(
            session,
            user_id=uid,
            type="return",
            title="Return distributed",
            message=f"A {kind} distribution for {prop.title} ({period_key}) was credited.",
            email_category="returns",
        )

    return {
        "distribution_id": distribution.id,
        "property_id": property_id,
        "period_key": period_key,
        "gross_pool": str(distribution.gross_pool),
        "total_net": str(distribution.total_net),
        "total_management_fee": str(distribution.total_management_fee),
        "investors": len(owners),
        "status": distribution.status,
    }


async def _allocate_family(
    session: AsyncSession,
    distribution_id: uuid.UUID,
    holder_id: uuid.UUID,
    holder_net: decimal.Decimal,
    property_id: uuid.UUID,
    holder_units: int,
) -> None:
    """Record-only family split (Phase 10, no-double-count §3): of the holder's net for
    THIS property, only the **PENDING fraction** is recorded to not-yet-registered
    members; the rest stays the holder's own. Real-owner members are paid directly by
    the distribution loop and are NEVER in this split — so no unit is counted twice.

    ``recorded = holder_net × pending_total / holder_units`` (pending_total ≤ holder_units
    by the §2 invariant), split among pending recipients by their per-property pending
    units (Hamilton, exact). Money stays in the holder's wallet (already credited)."""
    if holder_units <= 0:
        return
    group = (
        await session.execute(select(FamilyGroup).where(FamilyGroup.owner_id == holder_id))
    ).scalar_one_or_none()
    if group is None:
        return
    res = await session.execute(
        select(FamilyTransfer.to_member_id, func.coalesce(func.sum(FamilyTransfer.units), 0))
        .select_from(FamilyTransfer)
        .join(FamilyMember, FamilyTransfer.from_member_id == FamilyMember.id)
        .where(
            FamilyMember.user_id == holder_id,
            FamilyTransfer.property_id == property_id,
            FamilyTransfer.status == "pending",
        )
        .group_by(FamilyTransfer.to_member_id)
    )
    pending = [(mid, int(u)) for mid, u in res.all() if int(u) > 0]
    if not pending:
        return
    pending_total = min(sum(u for _m, u in pending), holder_units)
    recorded = (
        holder_net * decimal.Decimal(pending_total) / decimal.Decimal(holder_units)
    ).quantize(_CENTS)
    if recorded <= 0:
        return
    pending.sort(key=lambda r: str(r[0]))
    split = hamilton(_to_cents(recorded), [(mid, u) for mid, u in pending])
    for mid, _u in pending:
        share = _from_cents(split[mid])
        if share <= 0:
            continue
        session.add(
            FamilyReturnAllocation(
                family_group_id=group.id,
                member_id=mid,
                amount=share,
                distribution_id=distribution_id,
            )
        )
        member = await session.get(FamilyMember, mid)
        if member is not None:
            member.allocated_returns = member.allocated_returns + share
            # recorded only: owed to them, released when they verify
            member.pending_returns = member.pending_returns + share
    group.total_returns = group.total_returns + recorded


# --- reads ----------------------------------------------------------------- #
async def my_returns(session: AsyncSession, user_id: uuid.UUID) -> dict:
    """The caller's return history + a monthly aggregation for the dashboard charts."""
    res = await session.execute(
        select(DistributionItem, Distribution)
        .join(Distribution, DistributionItem.distribution_id == Distribution.id)
        .where(DistributionItem.user_id == user_id)
        .order_by(Distribution.period_end.desc())
    )
    items = []
    monthly: dict[str, decimal.Decimal] = {}
    total = decimal.Decimal("0")
    total_fees = decimal.Decimal("0")
    for item, dist in res.all():
        items.append(
            {
                "distribution_id": str(dist.id),
                "property_id": str(dist.property_id),
                "kind": dist.kind,
                "period_key": dist.period_key,
                "period_end": dist.period_end.isoformat(),
                "units": item.units,
                "gross_amount": str(item.gross_amount),
                "management_fee": str(item.management_fee),
                "net_amount": str(item.net_amount),
            }
        )
        total += item.net_amount
        total_fees += item.management_fee
        month = dist.period_end.strftime("%Y-%m")
        monthly[month] = monthly.get(month, decimal.Decimal("0")) + item.net_amount
    monthly_list = [{"month": m, "net": str(v)} for m, v in sorted(monthly.items())]
    return {
        "total_net": str(total.quantize(_CENTS)),
        "total_management_fee": str(total_fees.quantize(_CENTS)),
        "count": len(items),
        "monthly": monthly_list,
        "items": items,
    }
