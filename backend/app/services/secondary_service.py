"""Secondary market (Phase 8) — investor-to-investor unit resale.

This transfers unit OWNERSHIP and moves MONEY between two investors' wallets, so it
carries the same money safeguards as the primary engine:

  * **List**: a holder lists N units at a price/unit. Ownership is validated from the
    append-only ``ownership_ledger`` (net units held), the lock-up + price bounds are
    enforced (admin-configurable, default open / 0 / 1.0%), and the active listing
    *reserves* the units — ``holding − Σ active-listing units_remaining`` is checked
    under a ``FOR UPDATE`` on the property row. No ledger row is written at listing.
  * **Buy**: ONE atomic transaction. Lock order is strictly **listing → property →
    wallets** (both wallets locked in sorted user_id order). The listing row lock
    serializes concurrent buyers (exactly one wins; the rest get 409). The buyer is
    debited gross + resale fee; the seller is credited the FULL gross; units move via
    two ``ownership_ledger`` rows (seller −M / buyer +M — Σ per property conserved);
    the resale fee is retained as recorded platform revenue (no platform wallet, same
    as the Phase 6 management fee). Partial fills decrement ``units_remaining`` (DB
    CHECK >= 0); the last fill flips the listing to ``sold``. All-or-nothing.

Idempotency: ``secondary_trades.idempotency_key`` UNIQUE — a buyer's request replay
returns the same trade and never double-buys.

Positions on an installment plan (0034). Units vested under a running plan cannot be listed
one by one (they are held with the plan), but the plan itself can change hands, whole:

  * **List**: the holder offers the POSITION (every unit of the plan, paid for or not) at a
    price per unit, like any listing (same lock-up and price bounds against the property's
    current price). One active listing per plan; the position must be worth more than the
    principal still to pay.
  * **Buy**: one buyer takes the whole position. They pay the seller the position's value
    less the principal still to pay — what the seller paid plus the increase on the whole
    position — and the buyer-side resale fee on that cash; the units vested so far move in the
    ledger; the plan becomes the buyer's, who pays the remaining installments on their dates.
    The amount is computed when the purchase runs (the seller may have paid an installment
    since the listing was read), so the buyer sends the amount they agreed to and a purchase
    that no longer matches it is refused. Lock order: listing → the plan's payments → the
    plan → property → wallets (the installment module's own order after the listing).
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import (
    FamilyMember,
    FamilyTransfer,
    InstallmentPlan,
    LpExitRequest,
    Property,
    ScheduledGift,
    SecondaryListing,
    SecondaryTrade,
    SukukCertificate,
    Wallet,
)
from app.models.base import TransactionType
from app.models.investments import OwnershipLedger
from app.services import (
    installment_service,
    notification_service,
    price_service,
    settings_service,
    wallet_service,
)

_CENTS = decimal.Decimal("0.01")
_HUNDRED = decimal.Decimal(100)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _q(value: decimal.Decimal) -> decimal.Decimal:
    return value.quantize(_CENTS, rounding=decimal.ROUND_HALF_UP)


async def _net_holding(session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID) -> int:
    """Net units the user currently holds of a property (purchases − resales), from
    the append-only ownership ledger (the source of truth)."""
    total = await session.scalar(
        select(func.coalesce(func.sum(OwnershipLedger.units), 0)).where(
            OwnershipLedger.user_id == user_id,
            OwnershipLedger.property_id == property_id,
        )
    )
    return int(total or 0)


async def reserved_units(session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID) -> int:
    """Units this user has reserved across BOTH markets for the property — active
    secondary listings AND open LP exit requests. The single shared reservation rule
    (Phase 9 fix): a unit can never sit on both markets at once, in either order.
    Callers must hold the property row ``FOR UPDATE`` while using this."""
    return sum((await reservation_breakdown(session, user_id, property_id)).values())


async def reservation_breakdown(
    session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID
) -> dict[str, int]:
    """The parts of ``reserved_units``, by reason, so a holder can be told WHY units cannot be
    sold: ``listed`` (active secondary listings), ``lp_exit`` (open liquidity-provider exit
    requests), ``family_pending`` (promised to family members not registered yet), ``gift``
    (scheduled gifts), ``installment_plan`` (vested under a plan that is still running) and
    ``pledged`` (an approved Nova Sukuk certificate's pledge)."""
    secondary = await session.scalar(
        select(func.coalesce(func.sum(SecondaryListing.units_remaining), 0)).where(
            SecondaryListing.seller_id == user_id,
            SecondaryListing.property_id == property_id,
            SecondaryListing.status == "active",
            # a listed plan position holds no units of its own: the plan's vested units are
            # already held below, and its other units are not in the holding yet
            SecondaryListing.plan_id.is_(None),
        )
    )
    lp_open = await session.scalar(
        select(func.coalesce(func.sum(LpExitRequest.units_remaining), 0)).where(
            LpExitRequest.seller_id == user_id,
            LpExitRequest.property_id == property_id,
            LpExitRequest.status == "open",
        )
    )
    # Phase 10: units this user has promised to not-yet-registered family members
    # (pending family transfers OUT) are reserved against their holding too.
    family_pending = await session.scalar(
        select(func.coalesce(func.sum(FamilyTransfer.units), 0))
        .select_from(FamilyTransfer)
        .join(FamilyMember, FamilyTransfer.from_member_id == FamilyMember.id)
        .where(
            FamilyMember.user_id == user_id,
            FamilyTransfer.property_id == property_id,
            FamilyTransfer.status == "pending",
        )
    )
    # Group 5: units this user has promised to a future gift (scheduled, or pending the
    # recipient's KYC) are reserved against their holding — so a gifted unit can never be
    # simultaneously listed, LP-exited, family-allocated, or double-gifted before the date.
    gift_reserved = await session.scalar(
        select(func.coalesce(func.sum(ScheduledGift.units), 0)).where(
            ScheduledGift.giver_id == user_id,
            ScheduledGift.property_id == property_id,
            ScheduledGift.asset_type == "property_shares",
            ScheduledGift.status.in_(("scheduled", "pending")),
        )
    )
    # Group 6: units already VESTED under an ACTIVE (pre-handover) installment plan are held
    # against the holder: they cannot be listed loose, LP-exited, family-allocated or gifted
    # while the plan runs. They change hands only with the plan, as one position (0034,
    # create_position_listing). A completed plan releases them.
    installment_vested = await session.scalar(
        select(func.coalesce(func.sum(InstallmentPlan.vested_units), 0)).where(
            InstallmentPlan.investor_id == user_id,
            InstallmentPlan.property_id == property_id,
            InstallmentPlan.status == "active",
        )
    )
    nova_pledged = await pledged_units(session, user_id, property_id)
    return {
        "listed": int(secondary or 0),
        "lp_exit": int(lp_open or 0),
        "family_pending": int(family_pending or 0),
        "gift": int(gift_reserved or 0),
        "installment_plan": int(installment_vested or 0),
        "pledged": int(nova_pledged or 0),
    }


async def lockup_until(
    session: AsyncSession,
    user_id: uuid.UUID,
    property_id: uuid.UUID,
    now: dt.datetime | None = None,
) -> dt.datetime | None:
    """When the resale lock-up on this holding ends, if it is still running (None when there
    is no lock-up or it is over)."""
    days = int((await settings_service.get_secondary_settings(session))["lockup_days"] or 0)
    if days <= 0:
        return None
    first = await _earliest_acquisition(session, user_id, property_id)
    if first is None:
        return None
    unlock = first + dt.timedelta(days=days)
    return unlock if (now or _utcnow()) < unlock else None


async def pledged_units(session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID) -> int:
    """0032: units paid with an APPROVED Nova Sukuk certificate stay pledged to Nova Finance
    until staff release the pledge. A plan's pledged units are already held (as vested units of
    an active plan) until it completes, so they count here only once it has."""
    total = await session.scalar(
        select(func.coalesce(func.sum(SukukCertificate.units), 0))
        .select_from(SukukCertificate)
        .outerjoin(InstallmentPlan, SukukCertificate.plan_id == InstallmentPlan.id)
        .where(
            SukukCertificate.user_id == user_id,
            SukukCertificate.property_id == property_id,
            SukukCertificate.status == "approved",
            or_(SukukCertificate.plan_id.is_(None), InstallmentPlan.status != "active"),
        )
    )
    return int(total or 0)


async def _earliest_acquisition(
    session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID
) -> dt.datetime | None:
    """When the user first ACQUIRED units of the property (min created_at over the
    positive ownership rows) — the lock-up reference point."""
    return await session.scalar(
        select(func.min(OwnershipLedger.created_at)).where(
            OwnershipLedger.user_id == user_id,
            OwnershipLedger.property_id == property_id,
            OwnershipLedger.units > 0,
        )
    )


# --- list ------------------------------------------------------------------- #
async def _check_lockup(
    session: AsyncSession,
    sett: dict,
    seller_id: uuid.UUID,
    property_id: uuid.UUID,
    now: dt.datetime | None,
) -> None:
    """Lock-up: now must be >= the seller's first acquisition of the property + lockup_days."""
    lockup_days = int(sett["lockup_days"] or 0)
    if lockup_days <= 0:
        return
    first = await _earliest_acquisition(session, seller_id, property_id)
    if first is None:
        return
    unlock = first + dt.timedelta(days=lockup_days)
    if (now or _utcnow()) < unlock:
        raise AppError(
            "LOCKUP_ACTIVE",
            f"These units are under a {lockup_days}-day lock-up.",
            status_code=409,
            details={"unlocks_at": unlock.isoformat()},
        )


def _check_price_bounds(sett: dict, ref: decimal.Decimal, price: decimal.Decimal) -> None:
    """Price bounds against the property's current unit price. Open by default."""
    pmin = sett["price_min_pct"]
    pmax = sett["price_max_pct"]
    if pmin is not None and price < _q(ref * pmin / _HUNDRED):
        raise AppError(
            "PRICE_OUT_OF_BOUNDS",
            f"Price is below the allowed minimum ({pmin}% of {ref}).",
            status_code=422,
        )
    if pmax is not None and price > _q(ref * pmax / _HUNDRED):
        raise AppError(
            "PRICE_OUT_OF_BOUNDS",
            f"Price is above the allowed maximum ({pmax}% of {ref}).",
            status_code=422,
        )


def _price(price_per_unit: float | decimal.Decimal | str) -> decimal.Decimal:
    price = decimal.Decimal(str(price_per_unit)).quantize(_CENTS)
    if price <= 0:
        raise AppError("INVALID_PRICE", "Price per unit must be positive.", status_code=422)
    return price


async def create_listing(
    session: AsyncSession,
    *,
    seller_id: uuid.UUID,
    property_id: uuid.UUID,
    units: int,
    price_per_unit: float,
    now: dt.datetime | None = None,
) -> dict:
    if units < 1:
        raise AppError("INVALID_UNITS", "You must list at least one unit.", status_code=422)
    price = _price(price_per_unit)

    # Lock the property row: serializes listing/reservation math against concurrent
    # listings (and against buys that change the ledger).
    prop = (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)

    holding = await _net_holding(session, seller_id, property_id)
    if holding < 1:
        raise AppError("NOT_AN_OWNER", "You do not own units of this property.", status_code=422)
    reserved = await reserved_units(session, seller_id, property_id)
    if units > holding - reserved:
        raise AppError(
            "INSUFFICIENT_UNITS",
            "You do not have that many unreserved units to list.",
            status_code=422,
            details={"holding": holding, "already_listed": reserved, "requested": units},
        )

    sett = await settings_service.get_secondary_settings(session)
    await _check_lockup(session, sett, seller_id, property_id, now)
    _check_price_bounds(sett, prop.unit_price, price)

    listing = SecondaryListing(
        seller_id=seller_id,
        property_id=property_id,
        investment_id=None,
        units_for_sale=units,
        units_remaining=units,
        price_per_unit=price,
        status="active",
    )
    session.add(listing)
    await session.flush()
    await write_audit(
        session,
        action="secondary.listed",
        entity_type="secondary_listing",
        entity_id=str(listing.id),
        actor_id=seller_id,
        after={"property_id": str(property_id), "units": units, "price_per_unit": str(price)},
    )
    return _listing_result(listing, prop)


# --- a position on an installment plan (0034) -------------------------------- #
async def _nova_pledged(session: AsyncSession, plan_id: uuid.UUID) -> bool:
    """The plan was started with a Nova Sukuk certificate whose pledge is not released yet."""
    held = await session.scalar(
        select(func.count())
        .select_from(SukukCertificate)
        .where(SukukCertificate.plan_id == plan_id, SukukCertificate.status == "approved")
    )
    return bool(held)


_PLEDGED_MESSAGE = (
    "This plan was started with a Nova Sukuk certificate: its units are pledged to Nova "
    "Finance, so the position cannot be sold until Nova Finance releases them."
)


def _position_out(fig: dict, fee_pct: decimal.Decimal) -> dict:
    """A position's figures as the API gives them (money as strings). ``cash`` is what the
    buyer pays the seller now; the buyer then pays the schedule."""
    cash = fig["equity"]
    fee = _q(cash * fee_pct / _HUNDRED) if cash > 0 else decimal.Decimal("0.00")
    return {
        "plan_id": fig["plan_id"],
        "units": fig["units"],
        "vested_units": fig["vested_units"],
        "locked_price": str(fig["locked_price"]),
        "entry_price": str(fig["entry_price"]),
        "price": str(fig["price"]),
        "value": str(fig["value"]),
        "cost": str(fig["cost"]),
        "paid_principal": str(fig["paid_principal"]),
        "remaining_principal": str(fig["remaining_principal"]),
        "remaining_fees": str(fig["remaining_fees"]),
        "gain": str(fig["gain"]),
        "cash": str(cash),
        "resale_fee": str(fee),
        "total_now": str(_q(cash + fee)),
        "installments_left": fig["installments_left"],
        "overdue": fig["overdue"],
        "next_due": fig["next_due"],
        "schedule": [
            {
                "seq": p.seq,
                "kind": p.kind,
                "due_date": p.due_date,
                "base_amount": str(p.base_amount),
                "fee_amount": str(p.fee_amount),
                "total_amount": str(p.total_amount),
                "status": p.status,
            }
            for p in fig["schedule"]
        ],
    }


async def create_position_listing(
    session: AsyncSession,
    *,
    seller_id: uuid.UUID,
    plan_id: uuid.UUID,
    price_per_unit: float,
    now: dt.datetime | None = None,
) -> dict:
    """Offer a running installment plan for sale as one position, at a price per unit."""
    price = _price(price_per_unit)
    # lock order of the installment module: the plan's payments, the plan, then the property
    plan, payments = await installment_service._lock_plan_rows(session, plan_id)
    if plan is None or plan.investor_id != seller_id:
        raise AppError("NOT_FOUND", "Installment plan not found.", status_code=404)
    if plan.status != "active":
        tail = (
            " This plan is paid off: list its units like any others."
            if plan.status == "completed"
            else ""
        )
        raise AppError(
            "PLAN_NOT_RUNNING",
            "Only a plan that is running can be sold as a position." + tail,
            status_code=409,
        )
    prop = (
        await session.execute(
            select(Property).where(Property.id == plan.property_id).with_for_update()
        )
    ).scalar_one()
    if await _nova_pledged(session, plan.id):
        raise AppError("UNITS_PLEDGED", _PLEDGED_MESSAGE, status_code=409)
    already = await session.scalar(
        select(SecondaryListing.id).where(
            SecondaryListing.plan_id == plan.id, SecondaryListing.status == "active"
        )
    )
    if already is not None:
        raise AppError(
            "ALREADY_LISTED",
            "This position is already listed for sale. Cancel that listing to change its price.",
            status_code=409,
            details={"listing_id": str(already)},
        )

    sett = await settings_service.get_secondary_settings(session)
    await _check_lockup(session, sett, seller_id, plan.property_id, now)
    _check_price_bounds(sett, prop.unit_price, price)
    fig = await installment_service.holder_position(session, plan, payments, price)
    if fig["equity"] <= 0:
        floor = _q(fig["remaining_principal"] / plan.units_total)
        raise AppError(
            "PRICE_TOO_LOW",
            f"At {price} a unit the position is worth {fig['value']}, which does not cover the "
            f"{fig['remaining_principal']} still to pay on it. Ask more than {floor} a unit.",
            status_code=422,
            details={
                "remaining_principal": str(fig["remaining_principal"]),
                "minimum_price": str(floor),
            },
        )

    listing = SecondaryListing(
        seller_id=seller_id,
        property_id=plan.property_id,
        investment_id=None,
        plan_id=plan.id,
        units_for_sale=plan.units_total,
        units_remaining=plan.units_total,
        price_per_unit=price,
        status="active",
    )
    session.add(listing)
    await session.flush()
    await write_audit(
        session,
        action="secondary.position_listed",
        entity_type="secondary_listing",
        entity_id=str(listing.id),
        actor_id=seller_id,
        after={
            "plan_id": str(plan.id),
            "property_id": str(plan.property_id),
            "units": plan.units_total,
            "price_per_unit": str(price),
            "value": str(fig["value"]),
            "remaining_principal": str(fig["remaining_principal"]),
            "cash": str(fig["equity"]),
        },
    )
    fee_pct = decimal.Decimal(str(sett["resale_fee_pct"] or "0"))
    return _listing_result(listing, prop, _position_out(fig, fee_pct))


async def _buy_position(
    session: AsyncSession,
    *,
    listing: SecondaryListing,
    buyer_id: uuid.UUID,
    units: int,
    expected_cash: str | None,
    idempotency_key: str,
    expected_fee: str | None = None,
) -> dict:
    """One buyer takes a whole installment position. The caller holds the listing row lock
    and has checked that the listing is active and not the buyer's own."""
    if units != listing.units_remaining:
        raise AppError(
            "WHOLE_POSITION",
            f"This is an installment position: it is sold whole ({listing.units_remaining} units).",
            status_code=422,
            details={"units": listing.units_remaining},
        )
    gone = AppError("LISTING_NOT_ACTIVE", "This position is no longer for sale.", status_code=409)
    assert listing.plan_id is not None
    plan, payments = await installment_service._lock_plan_rows(session, listing.plan_id)
    seller_id = listing.seller_id
    if plan is None or plan.status != "active" or plan.investor_id != seller_id:
        raise gone
    prop = (
        await session.execute(
            select(Property).where(Property.id == plan.property_id).with_for_update()
        )
    ).scalar_one()
    if await _nova_pledged(session, plan.id):
        raise AppError("UNITS_PLEDGED", _PLEDGED_MESSAGE, status_code=409)

    sett = await settings_service.get_secondary_settings(session)
    fee_pct = decimal.Decimal(str(sett["resale_fee_pct"] or "0"))
    # the plan's own figures (what a buyer is shown), not the seller's cost and gain
    fig = installment_service.position_figures(plan, payments, listing.price_per_unit)
    cash = fig["equity"]
    if cash <= 0:  # the seller only ever pays the remainder down: a guard, not a path
        raise gone
    resale_fee = _q(cash * fee_pct / _HUNDRED)
    total_charged = _q(cash + resale_fee)

    # The buyer agreed to amounts on their screen. The seller may have paid an installment
    # since (more to pay now, less to take over), or the resale fee may have been changed:
    # never charge an amount nobody confirmed.
    def _agreed(value: str | None) -> decimal.Decimal | None:
        try:
            return _q(decimal.Decimal(str(value))) if value is not None else None
        except (decimal.InvalidOperation, ValueError):
            return None

    if _agreed(expected_cash) != cash or (
        expected_fee is not None and _agreed(expected_fee) != resale_fee
    ):
        raise AppError(
            "POSITION_CHANGED",
            "The amounts of this position changed since you opened it. Review them and "
            "confirm again.",
            status_code=409,
            details={"position": _json_ready(_position_out(fig, fee_pct))},
        )
    vested = int(plan.vested_units or 0)
    if await _net_holding(session, seller_id, plan.property_id) < vested:
        # the ledger and the plan disagree: refuse rather than move units that are not there
        raise AppError(
            "INVALID_STATE",
            "This position cannot be sold right now. Please contact support.",
            status_code=409,
        )
    # the buyer holds the plan's units at the CURRENT platform management-fee rate (Decision 2)
    buyer_fee_rate = await settings_service.get_management_fee_pct(session)

    for uid in sorted([buyer_id, seller_id], key=str):
        await session.execute(select(Wallet).where(Wallet.user_id == uid).with_for_update())
    lines: list[tuple[TransactionType, decimal.Decimal, str | None]] = [
        (TransactionType.investment, cash, f"Installment position — {prop.title}")
    ]
    if resale_fee > 0:  # a fee of zero (the rate is 0, or it rounds to nothing) is no line
        lines.append((TransactionType.fee, resale_fee, "Resale fee (one-time)"))
    buyer_wallet = await wallet_service.debit(
        session,
        user_id=buyer_id,
        reference_id=listing.id,
        line_items=lines,
        actor_id=buyer_id,
    )
    buyer_wallet.total_invested = buyer_wallet.total_invested + cash
    await wallet_service.credit(
        session,
        user_id=seller_id,
        amount=cash,
        reference_id=listing.id,
        tx_type=TransactionType.secondary_sale,
        description=f"Installment position sold — {prop.title}",
        actor_id=buyer_id,
    )

    # The units vested so far change hands (Σ per property conserved); the rest vest to the
    # buyer as the buyer pays for them.
    if vested > 0:
        session.add(
            OwnershipLedger(
                user_id=seller_id,
                property_id=plan.property_id,
                investment_id=None,
                units=-vested,
                unit_price=listing.price_per_unit,
                reason="secondary_sale",
            )
        )
        session.add(
            OwnershipLedger(
                user_id=buyer_id,
                property_id=plan.property_id,
                investment_id=None,
                units=vested,
                unit_price=listing.price_per_unit,
                reason="secondary_purchase",
                fee_rate=buyer_fee_rate,
            )
        )

    # The plan is the buyer's from here: the unpaid installments keep their dates and
    # amounts, are charged from the buyer's wallet and remind the buyer.
    now = _utcnow()
    plan.investor_id = buyer_id
    plan.management_fee_rate = buyer_fee_rate
    plan.updated_at = now
    for p in payments:
        if p.status != "paid":
            p.status = "scheduled"
            p.reminder_sent_at = None

    listing.units_remaining = 0
    listing.status = "sold"
    listing.sold_at = now

    trade = SecondaryTrade(
        listing_id=listing.id,
        property_id=plan.property_id,
        seller_id=seller_id,
        buyer_id=buyer_id,
        units=plan.units_total,
        price_per_unit=listing.price_per_unit,
        gross=cash,
        resale_fee=resale_fee,
        total_charged=total_charged,
        plan_id=plan.id,
        position_value=fig["value"],
        paid_principal=fig["paid_principal"],
        assumed_principal=fig["remaining_principal"],
        assumed_fees=fig["remaining_fees"],
        idempotency_key=idempotency_key,
    )
    session.add(trade)
    await session.flush()

    await write_audit(
        session,
        action="secondary.position_traded",
        entity_type="secondary_trade",
        entity_id=str(trade.id),
        actor_id=buyer_id,
        after={
            "listing_id": str(listing.id),
            "plan_id": str(plan.id),
            "property_id": str(plan.property_id),
            "seller_id": str(seller_id),
            "units": plan.units_total,
            "vested_units": vested,
            "price_per_unit": str(listing.price_per_unit),
            "position_value": str(fig["value"]),
            "paid_principal": str(fig["paid_principal"]),
            "assumed_principal": str(fig["remaining_principal"]),
            "cash": str(cash),
            "resale_fee": str(resale_fee),
            "total_charged": str(total_charged),
        },
    )
    left = fig["installments_left"]
    await notification_service.notify(
        session,
        user_id=seller_id,
        type="secondary",
        title="Installment position sold",
        message=(
            f"You sold your installment position in {prop.title} ({plan.units_total} unit(s)) "
            f"for {cash}. The buyer pays the remaining installments from now on."
        ),
        email_category="investment_updates",
    )
    next_due = f" The next one is due on {fig['next_due'].isoformat()}." if fig["next_due"] else ""
    await notification_service.notify(
        session,
        user_id=buyer_id,
        type="secondary",
        title="Installment position bought",
        message=(
            f"You took over an installment position in {prop.title}: {plan.units_total} "
            f"unit(s), {vested} of them yours already. {left} installment(s) remain "
            f"({fig['remaining_principal']} plus fees), charged from your wallet on their "
            f"dates.{next_due}"
        ),
        email_category="investment_updates",
    )
    return _trade_result(trade)


def _json_ready(position: dict) -> dict:
    """The position with its dates as text, for an error's details."""
    out = dict(position)
    out["plan_id"] = str(out["plan_id"])
    out["next_due"] = out["next_due"].isoformat() if out["next_due"] else None
    out["schedule"] = [{**row, "due_date": row["due_date"].isoformat()} for row in out["schedule"]]
    return out


async def cancel_listing(
    session: AsyncSession, *, seller_id: uuid.UUID, listing_id: uuid.UUID
) -> dict:
    listing = (
        await session.execute(
            select(SecondaryListing).where(SecondaryListing.id == listing_id).with_for_update()
        )
    ).scalar_one_or_none()
    if listing is None:
        raise AppError("NOT_FOUND", "Listing not found", status_code=404)
    if listing.seller_id != seller_id:
        raise AppError("FORBIDDEN", "You can only cancel your own listing.", status_code=403)
    if listing.status != "active":
        raise AppError("INVALID_STATE", "Only an active listing can be cancelled.", status_code=409)
    listing.status = "cancelled"
    listing.cancelled_at = _utcnow()
    await write_audit(
        session,
        action="secondary.cancelled",
        entity_type="secondary_listing",
        entity_id=str(listing.id),
        actor_id=seller_id,
    )
    return {"listing_id": listing.id, "status": listing.status}


# --- buy (atomic transfer) -------------------------------------------------- #
async def buy_listing(
    session: AsyncSession,
    *,
    buyer_id: uuid.UUID,
    listing_id: uuid.UUID,
    units: int,
    idempotency_key: str,
    expected_cash: str | None = None,
    expected_fee: str | None = None,
) -> dict:
    """Buy units off a listing. ``expected_cash`` and ``expected_fee`` are only for an
    installment position: what the buyer agreed to pay the seller, and the resale fee they
    were shown on top (see ``_buy_position``)."""
    if units < 1:
        raise AppError("INVALID_UNITS", "You must buy at least one unit.", status_code=422)

    # Idempotency-Key replay -> return the existing trade (no second purchase).
    existing = (
        await session.execute(
            select(SecondaryTrade).where(SecondaryTrade.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.buyer_id != buyer_id:
            raise AppError(
                "IDEMPOTENCY_KEY_REUSED",
                "This request key was already used for another purchase.",
                status_code=409,
            )
        return _trade_result(existing)

    # Lock order #1: the listing row — serializes concurrent buyers (exactly one wins).
    listing = (
        await session.execute(
            select(SecondaryListing).where(SecondaryListing.id == listing_id).with_for_update()
        )
    ).scalar_one_or_none()
    if listing is None:
        raise AppError("NOT_FOUND", "Listing not found", status_code=404)
    if listing.status != "active":
        raise AppError(
            "LISTING_NOT_ACTIVE", "This listing is no longer available.", status_code=409
        )
    if listing.seller_id == buyer_id:
        raise AppError(
            "CANNOT_BUY_OWN_LISTING", "You cannot buy your own listing.", status_code=409
        )
    if listing.plan_id is not None:
        return await _buy_position(
            session,
            listing=listing,
            buyer_id=buyer_id,
            units=units,
            expected_cash=expected_cash,
            expected_fee=expected_fee,
            idempotency_key=idempotency_key,
        )
    if units > listing.units_remaining:
        raise AppError(
            "INSUFFICIENT_UNITS",
            "The listing does not have that many units remaining.",
            status_code=409,
            details={"units_remaining": listing.units_remaining, "requested": units},
        )

    seller_id = listing.seller_id
    property_id = listing.property_id

    # Lock order #2: the property row (freezes ownership/price reference).
    prop = (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)

    sett = await settings_service.get_secondary_settings(session)
    fee_pct = decimal.Decimal(str(sett["resale_fee_pct"] or "0"))
    # Decision 2: the buyer acquires units at the CURRENT platform management-fee rate.
    buyer_fee_rate = await settings_service.get_management_fee_pct(session)
    gross = _q(listing.price_per_unit * units)
    resale_fee = _q(gross * fee_pct / decimal.Decimal(100))
    total_charged = _q(gross + resale_fee)

    # Lock order #3: both wallets, sorted by user_id (deadlock-free). credit()/debit()
    # re-lock the same rows harmlessly inside this critical section.
    for uid in sorted([buyer_id, seller_id], key=str):
        await session.execute(select(Wallet).where(Wallet.user_id == uid).with_for_update())

    # Debit the buyer: gross (investment) + resale fee (fee). Over-balance -> 422 and
    # the whole purchase rolls back (listing + ledger untouched).
    lines: list[tuple[TransactionType, decimal.Decimal, str | None]] = [
        (TransactionType.investment, gross, f"Secondary purchase — {prop.title}")
    ]
    if resale_fee > 0:  # a resale fee set to zero is no line (the wallet refuses empty ones)
        lines.append((TransactionType.fee, resale_fee, "Resale fee (one-time)"))
    buyer_wallet = await wallet_service.debit(
        session,
        user_id=buyer_id,
        reference_id=listing.id,
        line_items=lines,
        actor_id=buyer_id,
    )
    buyer_wallet.total_invested = buyer_wallet.total_invested + gross

    # Credit the seller the FULL gross (the fee is buyer-side, retained as revenue).
    await wallet_service.credit(
        session,
        user_id=seller_id,
        amount=gross,
        reference_id=listing.id,
        tx_type=TransactionType.secondary_sale,
        description=f"Secondary sale — {prop.title}",
        actor_id=buyer_id,
    )

    # Move ownership: seller -units, buyer +units (Σ per property conserved).
    session.add(
        OwnershipLedger(
            user_id=seller_id,
            property_id=property_id,
            investment_id=None,
            units=-units,
            unit_price=listing.price_per_unit,
            reason="secondary_sale",
        )
    )
    session.add(
        OwnershipLedger(
            user_id=buyer_id,
            property_id=property_id,
            investment_id=None,
            units=units,
            unit_price=listing.price_per_unit,
            reason="secondary_purchase",
            fee_rate=buyer_fee_rate,  # Decision 2: platform rate at acquisition
        )
    )

    # Decrement the live counter; flip to sold on the last unit (DB CHECK >= 0 backstop).
    listing.units_remaining -= units
    if listing.units_remaining == 0:
        listing.status = "sold"
        listing.sold_at = _utcnow()

    trade = SecondaryTrade(
        listing_id=listing.id,
        property_id=property_id,
        seller_id=seller_id,
        buyer_id=buyer_id,
        units=units,
        price_per_unit=listing.price_per_unit,
        gross=gross,
        resale_fee=resale_fee,
        total_charged=total_charged,
        idempotency_key=idempotency_key,
    )
    session.add(trade)
    await session.flush()

    await write_audit(
        session,
        action="secondary.traded",
        entity_type="secondary_trade",
        entity_id=str(trade.id),
        actor_id=buyer_id,
        after={
            "listing_id": str(listing.id),
            "property_id": str(property_id),
            "seller_id": str(seller_id),
            "units": units,
            "gross": str(gross),
            "resale_fee": str(resale_fee),
            "total_charged": str(total_charged),
        },
    )
    await notification_service.notify(
        session,
        user_id=seller_id,
        type="secondary",
        title="Units sold",
        message=f"You sold {units} unit(s) of {prop.title} for {gross}.",
    )
    await notification_service.notify(
        session,
        user_id=buyer_id,
        type="secondary",
        title="Units purchased",
        message=f"You bought {units} unit(s) of {prop.title}.",
    )
    return _trade_result(trade)


# --- reads ------------------------------------------------------------------ #
async def _position_of(
    session: AsyncSession,
    listing: SecondaryListing,
    fee_pct: decimal.Decimal,
    *,
    for_seller: bool = False,
) -> dict | None:
    """The position a listing offers, at the listing's price (None for a listing of ordinary
    units, and for one whose plan is no longer the seller's running plan).

    The market shows the PLAN's figures: what has been paid on it and the price change since
    it started, which is all a buyer needs (cash = paid + that change). What the seller paid
    for the position, if they bought it themselves, is theirs alone (``for_seller``)."""
    if listing.plan_id is None:
        return None
    plan = await session.get(InstallmentPlan, listing.plan_id)
    if plan is None or plan.status != "active" or plan.investor_id != listing.seller_id:
        return None
    payments = await installment_service._payments_for(session, plan.id)
    if for_seller:
        fig = await installment_service.holder_position(
            session, plan, payments, listing.price_per_unit
        )
    else:
        fig = installment_service.position_figures(plan, payments, listing.price_per_unit)
    return _position_out(fig, fee_pct)


async def _fee_pct(session: AsyncSession) -> decimal.Decimal:
    sett = await settings_service.get_secondary_settings(session)
    return decimal.Decimal(str(sett["resale_fee_pct"] or "0"))


async def list_active_listings(
    session: AsyncSession, *, property_id: uuid.UUID | None = None
) -> list[dict]:
    stmt = (
        select(SecondaryListing, Property)
        .join(Property, SecondaryListing.property_id == Property.id)
        .where(SecondaryListing.status == "active", SecondaryListing.units_remaining > 0)
        .order_by(SecondaryListing.created_at.desc())
    )
    if property_id is not None:
        stmt = stmt.where(SecondaryListing.property_id == property_id)
    rows = (await session.execute(stmt)).all()
    fee_pct = await _fee_pct(session)
    out: list[dict] = []
    for listing, prop in rows:
        position = await _position_of(session, listing, fee_pct)
        if listing.plan_id is not None and position is None:
            continue  # its plan was paid off or changed hands: nothing left to buy here
        out.append(_listing_result(listing, prop, position))
    return out


async def list_my_listings(session: AsyncSession, seller_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(SecondaryListing, Property)
            .join(Property, SecondaryListing.property_id == Property.id)
            .where(SecondaryListing.seller_id == seller_id)
            .order_by(SecondaryListing.created_at.desc())
        )
    ).all()
    fee_pct = await _fee_pct(session)
    # what each position that was sold brought its seller
    sold_for = dict(
        (
            await session.execute(
                select(SecondaryTrade.listing_id, SecondaryTrade.gross).where(
                    SecondaryTrade.seller_id == seller_id, SecondaryTrade.plan_id.is_not(None)
                )
            )
        ).all()
    )
    out: list[dict] = []
    for listing, prop in rows:
        position = (
            await _position_of(session, listing, fee_pct, for_seller=True)
            if listing.status == "active"
            else None
        )
        row = _listing_result(listing, prop, position)
        if listing.plan_id is not None and listing.id in sold_for:
            row["cash"] = str(sold_for[listing.id])
        out.append(row)
    return out


async def position_block(
    session: AsyncSession, plan: InstallmentPlan, listing_id: uuid.UUID | None
) -> tuple[str | None, dt.datetime | None]:
    """What stands in the way of listing a running plan now, and until when: ``pledged`` (its
    units back a Nova Sukuk certificate), ``lockup`` (the resale lock-up, with its end) or
    ``listed`` (it is already for sale). (None, None) = it can be listed."""
    if await _nova_pledged(session, plan.id):
        return "pledged", None
    unlock = await lockup_until(session, plan.investor_id, plan.property_id)
    if unlock is not None:
        return "lockup", unlock
    return ("listed", None) if listing_id is not None else (None, None)


async def my_positions(session: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """The caller's running installment plans as positions they could sell, valued at each
    property's current unit price: what a buyer would pay them, what the buyer would take
    over, and what stands in the way (a Nova pledge, a lock-up, an existing listing)."""
    plans = (
        (
            await session.execute(
                select(InstallmentPlan)
                .where(InstallmentPlan.investor_id == user_id, InstallmentPlan.status == "active")
                .order_by(InstallmentPlan.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    fee_pct = await _fee_pct(session)
    out: list[dict] = []
    for plan in plans:
        prop = await session.get(Property, plan.property_id)
        if prop is None:
            continue
        payments = await installment_service._payments_for(session, plan.id)
        fig = await installment_service.holder_position(session, plan, payments, prop.unit_price)
        listing_id = await installment_service._active_listing_id(session, plan.id)
        blocked, unlock = await position_block(session, plan, listing_id)
        out.append(
            {
                **_position_out(fig, fee_pct),
                "property_id": str(plan.property_id),
                "property_title": prop.title,
                "property_location": prop.location,
                "unit_price": str(_q(prop.unit_price)),
                "listing_id": listing_id,
                "blocked": blocked,
                "lockup_until": unlock,
            }
        )
    return out


async def _average_cost(
    session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID
) -> decimal.Decimal | None:
    """What the units held now cost per unit, on average (each acquisition at its own price;
    a disposal takes units out at the average so far). None when nothing is held."""
    rows = (
        await session.execute(
            select(OwnershipLedger.units, OwnershipLedger.unit_price)
            .where(OwnershipLedger.user_id == user_id, OwnershipLedger.property_id == property_id)
            .order_by(OwnershipLedger.created_at, OwnershipLedger.id)
        )
    ).all()
    units = 0
    cost = decimal.Decimal("0")
    for moved, price in rows:
        if moved > 0:
            units += moved
            cost += decimal.Decimal(price) * moved
        elif units > 0:
            taken = min(-moved, units)
            cost -= cost / units * taken
            units -= taken
    return _q(cost / units) if units > 0 else None


async def my_holdings(session: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """The caller's net unit holdings per property (source of truth: ownership_ledger),
    minus the units already reserved in their active listings (sellable units), with the
    property's price now, at launch and what the holding cost."""
    rows = (
        await session.execute(
            select(
                OwnershipLedger.property_id,
                func.coalesce(func.sum(OwnershipLedger.units), 0),
                Property.title,
                Property.unit_price,
                Property.location,
            )
            .join(Property, OwnershipLedger.property_id == Property.id)
            .where(OwnershipLedger.user_id == user_id)
            .group_by(
                OwnershipLedger.property_id,
                Property.title,
                Property.unit_price,
                Property.location,
            )
        )
    ).all()
    held_rows = [r for r in rows if int(r[1] or 0) > 0]
    prices = await price_service.summaries(session, [r[0] for r in held_rows])
    out: list[dict] = []
    for pid, units, title, unit_price, location in held_rows:
        held = int(units or 0)
        held_back = await reservation_breakdown(session, user_id, pid)
        reserved = sum(held_back.values())
        pledged = held_back["pledged"]
        price = prices.get(pid, {})
        launch = decimal.Decimal(price.get("launch_price", unit_price))
        average = await _average_cost(session, user_id, pid)
        out.append(
            {
                "property_id": str(pid),
                "title": title,
                "location": location,
                "units": held,
                "listed_units": reserved - pledged,
                "pledged_units": pledged,
                "sellable_units": max(0, held - reserved),
                "unit_price": str(unit_price),
                "held_back": held_back,
                # units vested under a running installment plan: sold with the plan, as a
                # position (see my_positions), never one by one
                "plan_units": held_back["installment_plan"],
                "launch_price": str(_q(launch)),
                "price_change_pct": str(price_service.change_pct(launch, unit_price)),
                "price_updated_at": price.get("updated_at"),
                "average_cost": str(average) if average is not None else None,
            }
        )
    return out


# --- helpers ---------------------------------------------------------------- #
def _listing_result(
    listing: SecondaryListing, prop: Property | None, position: dict | None = None
) -> dict:
    return {
        "listing_id": listing.id,
        # an installment plan position (sold whole; the buyer takes the plan over)
        "plan_id": listing.plan_id,
        "position": position,
        # a position: what the buyer pays the seller (its price is per unit, but the sale is
        # not units x price); once sold, what it was sold for
        "cash": position["cash"] if position else None,
        "property_id": str(listing.property_id) if listing.property_id else None,
        "property_title": prop.title if prop else None,
        "property_location": prop.location if prop else None,
        "seller_id": str(listing.seller_id),
        "units_for_sale": listing.units_for_sale,
        "units_remaining": listing.units_remaining,
        "price_per_unit": str(listing.price_per_unit),
        "unit_price_ref": str(prop.unit_price) if prop else None,
        "status": listing.status,
        "created_at": listing.created_at.isoformat() if listing.created_at else None,
    }


def _trade_result(trade: SecondaryTrade) -> dict:
    return {
        "trade_id": trade.id,
        "listing_id": trade.listing_id,
        "property_id": str(trade.property_id),
        "units": trade.units,
        "price_per_unit": str(trade.price_per_unit),
        "gross": str(trade.gross),
        "resale_fee": str(trade.resale_fee),
        "total_charged": str(trade.total_charged),
        "created_at": trade.created_at.isoformat() if trade.created_at else None,
        # the sale of an installment position: ``gross`` is the cash paid to the seller
        "plan_id": trade.plan_id,
        "position_value": _str(trade.position_value),
        "paid_principal": _str(trade.paid_principal),
        "assumed_principal": _str(trade.assumed_principal),
        "assumed_fees": _str(trade.assumed_fees),
    }


def _str(value: decimal.Decimal | None) -> str | None:
    return str(value) if value is not None else None
