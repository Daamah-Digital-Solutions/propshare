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
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import func, select
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
    Wallet,
)
from app.models.base import TransactionType
from app.models.investments import OwnershipLedger
from app.services import notification_service, settings_service, wallet_service

_CENTS = decimal.Decimal("0.01")


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
    secondary = await session.scalar(
        select(func.coalesce(func.sum(SecondaryListing.units_remaining), 0)).where(
            SecondaryListing.seller_id == user_id,
            SecondaryListing.property_id == property_id,
            SecondaryListing.status == "active",
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
    # against the holder — they can't be listed/LP-exited/family-allocated/gifted until the
    # plan completes at handover (the final payment). Completed plans release them.
    installment_vested = await session.scalar(
        select(func.coalesce(func.sum(InstallmentPlan.vested_units), 0)).where(
            InstallmentPlan.investor_id == user_id,
            InstallmentPlan.property_id == property_id,
            InstallmentPlan.status == "active",
        )
    )
    return (
        int(secondary or 0)
        + int(lp_open or 0)
        + int(family_pending or 0)
        + int(gift_reserved or 0)
        + int(installment_vested or 0)
    )


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
    price = decimal.Decimal(str(price_per_unit)).quantize(_CENTS)
    if price <= 0:
        raise AppError("INVALID_PRICE", "Price per unit must be positive.", status_code=422)

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

    # Lock-up: now must be >= earliest acquisition + lockup_days.
    lockup_days = int(sett["lockup_days"] or 0)
    if lockup_days > 0:
        first = await _earliest_acquisition(session, seller_id, property_id)
        if first is not None:
            unlock = first + dt.timedelta(days=lockup_days)
            if (now or _utcnow()) < unlock:
                raise AppError(
                    "LOCKUP_ACTIVE",
                    f"These units are under a {lockup_days}-day lock-up.",
                    status_code=409,
                    details={"unlocks_at": unlock.isoformat()},
                )

    # Price bounds (ref = property unit_price). Open by default.
    ref = prop.unit_price
    pmin = sett["price_min_pct"]
    pmax = sett["price_max_pct"]
    if pmin is not None and price < _q(ref * pmin / decimal.Decimal(100)):
        raise AppError(
            "PRICE_OUT_OF_BOUNDS",
            f"Price is below the allowed minimum ({pmin}% of {ref}).",
            status_code=422,
        )
    if pmax is not None and price > _q(ref * pmax / decimal.Decimal(100)):
        raise AppError(
            "PRICE_OUT_OF_BOUNDS",
            f"Price is above the allowed maximum ({pmax}% of {ref}).",
            status_code=422,
        )

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
) -> dict:
    if units < 1:
        raise AppError("INVALID_UNITS", "You must buy at least one unit.", status_code=422)

    # Idempotency-Key replay -> return the existing trade (no second purchase).
    existing = (
        await session.execute(
            select(SecondaryTrade).where(SecondaryTrade.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
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
    buyer_wallet = await wallet_service.debit(
        session,
        user_id=buyer_id,
        reference_id=listing.id,
        line_items=[
            (TransactionType.investment, gross, f"Secondary purchase — {prop.title}"),
            (TransactionType.fee, resale_fee, "Resale fee (one-time)"),
        ],
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
    return [_listing_result(listing, prop) for listing, prop in rows]


async def list_my_listings(session: AsyncSession, seller_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(SecondaryListing, Property)
            .join(Property, SecondaryListing.property_id == Property.id)
            .where(SecondaryListing.seller_id == seller_id)
            .order_by(SecondaryListing.created_at.desc())
        )
    ).all()
    return [_listing_result(listing, prop) for listing, prop in rows]


async def my_holdings(session: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """The caller's net unit holdings per property (source of truth: ownership_ledger),
    minus the units already reserved in their active listings (sellable units)."""
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
    out: list[dict] = []
    for pid, units, title, unit_price, location in rows:
        held = int(units or 0)
        if held <= 0:
            continue
        reserved = await reserved_units(session, user_id, pid)
        out.append(
            {
                "property_id": str(pid),
                "title": title,
                "location": location,
                "units": held,
                "listed_units": reserved,
                "sellable_units": max(0, held - reserved),
                "unit_price": str(unit_price),
            }
        )
    return out


# --- helpers ---------------------------------------------------------------- #
def _listing_result(listing: SecondaryListing, prop: Property | None) -> dict:
    return {
        "listing_id": listing.id,
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
    }
