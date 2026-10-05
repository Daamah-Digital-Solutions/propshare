"""A listing's unit price over time (0034).

Client (meeting 2026-10-01): a property under construction earns by its price going up, not
by rent. The developer sells in phases (100, then 110, then 115) and "every month we give the
property its new price, the guide price the holder exits at", shown to the holder on the
dashboard and as a chart in the reports.

One price, one place: ``properties.unit_price`` is the CURRENT price, and everything already
reads it: a new purchase (so a new phase's buyers pay the phase's price), the guide price of
a secondary listing, the price of a liquidity-provider exit and the value of a holding. Staff
record a new price here; nothing else may change the price of a listing investors hold (the
listing editor refuses, see ``listing_service.apply_offering_rules``). Each change:

  * is one append-only ``property_prices`` row (the price before, the new price, an optional
    phase name and note, who recorded it) and one audit entry;
  * keeps the offering consistent: the units still for sale are now offered at the new price,
    so the offering's total follows, and the minimum investment stays the same number of
    whole units;
  * is told to everyone who holds the property or is paying for it by installments.

What it never touches: an installment plan (its price was locked when it started), a purchase
already reserved (priced when it was made) and a secondary listing (the seller's own price).

An OPEN liquidity-provider exit request is closed: the platform priced it at the old price,
and a seller must not be bought out at a price the property no longer has. The seller is
told, and makes a new request at the new price.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import (
    InstallmentPlan,
    LpExitRequest,
    Property,
    PropertyPrice,
    SecondaryListing,
)
from app.models.base import PropertyStatus
from app.models.investments import OwnershipLedger
from app.services import notification_service
from app.services.investment_service import _recompute_progress

_CENTS = decimal.Decimal("0.01")
_HUNDRED = decimal.Decimal(100)
PUBLIC_STATUSES = (PropertyStatus.active, PropertyStatus.funded)
# A bigger change in one step is far more often a typing mistake (1100 for 110) than a real
# revaluation: it needs an explicit confirmation.
MAX_STEP_PCT = decimal.Decimal(25)
LABEL_MAX = 60
NOTE_MAX = 300


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _q(value: decimal.Decimal) -> decimal.Decimal:
    return value.quantize(_CENTS, rounding=decimal.ROUND_HALF_UP)


def usd(value: decimal.Decimal) -> str:
    d = _q(decimal.Decimal(value))
    return f"${d:,.0f}" if d == d.to_integral_value() else f"${d:,.2f}"


def change_pct(old: decimal.Decimal, new: decimal.Decimal) -> decimal.Decimal:
    """The move from ``old`` to ``new`` in percent (2 decimals; 0 when there is no base)."""
    if not old or old <= 0:
        return decimal.Decimal("0.00")
    return _q((decimal.Decimal(new) - decimal.Decimal(old)) / decimal.Decimal(old) * _HUNDRED)


def signed_pct(value: decimal.Decimal) -> str:
    """'+3.00%' / '-1.50%' / '0.00%' — for sentences and labels."""
    d = _q(decimal.Decimal(value))
    return f"{'+' if d > 0 else ''}{d}%"


def _clean(value: str | None, limit: int) -> str | None:
    text = " ".join((value or "").split())[:limit]
    return text or None


async def _rows(session: AsyncSession, property_id: uuid.UUID) -> list[PropertyPrice]:
    return list(
        (
            await session.execute(
                select(PropertyPrice)
                .where(PropertyPrice.property_id == property_id)
                .order_by(PropertyPrice.created_at, PropertyPrice.id)
            )
        )
        .scalars()
        .all()
    )


def _history(prop: Property, rows: Sequence[PropertyPrice]) -> dict:
    """The price line of one listing: its launch price, then every recorded change."""
    current = decimal.Decimal(prop.unit_price)
    launch = launch_price_of(prop)
    points = [
        {
            "at": prop.created_at,
            "price": str(_q(launch)),
            "change_pct": "0.00",
            "label": "Launch price",
            "note": None,
        }
    ]
    for row in rows:
        points.append(
            {
                "at": row.created_at,
                "price": str(_q(row.price)),
                "change_pct": str(change_pct(row.previous_price, row.price)),
                "label": row.label,
                "note": row.note,
            }
        )
    return {
        "property_id": prop.id,
        "current_price": str(_q(current)),
        "launch_price": str(_q(launch)),
        "change_pct": str(change_pct(launch, current)),
        "updated_at": rows[-1].created_at if rows else None,
        "phase": next((r.label for r in reversed(rows) if r.label), None),
        "points": points,
    }


def launch_price_of(prop: Property) -> decimal.Decimal:
    """The price the listing was launched at: kept on the listing from its first price change
    on (``properties.launch_price``); until then it is simply the current price."""
    if prop.launch_price is not None:
        return decimal.Decimal(prop.launch_price)
    return decimal.Decimal(prop.unit_price)


async def history(session: AsyncSession, prop: Property) -> dict:
    return _history(prop, await _rows(session, prop.id))


async def summaries(
    session: AsyncSession, property_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, dict]:
    """Per listing, what a holding's card shows next to the current price: the launch price and
    when the price last changed (missing = never changed since launch)."""
    if not property_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(PropertyPrice)
                .where(PropertyPrice.property_id.in_(list(property_ids)))
                .order_by(PropertyPrice.created_at, PropertyPrice.id)
            )
        )
        .scalars()
        .all()
    )
    out: dict[uuid.UUID, dict] = {}
    for row in rows:
        entry = out.setdefault(
            row.property_id, {"launch_price": decimal.Decimal(row.previous_price)}
        )
        entry["previous_price"] = decimal.Decimal(row.previous_price)
        entry["updated_at"] = row.created_at
        if row.label:
            entry["phase"] = row.label
    return out


async def _holders(session: AsyncSession, property_id: uuid.UUID) -> list[uuid.UUID]:
    """Everyone the price concerns: holders of the property and investors paying for it."""
    owners = (
        await session.execute(
            select(OwnershipLedger.user_id)
            .where(OwnershipLedger.property_id == property_id)
            .group_by(OwnershipLedger.user_id)
            .having(func.sum(OwnershipLedger.units) > 0)
        )
    ).scalars()
    payers = (
        await session.execute(
            select(InstallmentPlan.investor_id).where(
                InstallmentPlan.property_id == property_id, InstallmentPlan.status == "active"
            )
        )
    ).scalars()
    return sorted({*owners, *payers}, key=str)


async def record_price(
    session: AsyncSession,
    *,
    property_id: uuid.UUID,
    price: decimal.Decimal | float | str,
    label: str | None = None,
    note: str | None = None,
    actor_id: uuid.UUID | None = None,
    confirm_large: bool = False,
) -> PropertyPrice:
    """Give a published listing its new unit price (a monthly revaluation, or a new sales
    phase). Returns the history row. The caller's transaction commits it."""
    try:
        new = _q(decimal.Decimal(str(price)))
    except (decimal.InvalidOperation, ValueError) as exc:
        raise AppError(
            "INVALID_PRICE", "Enter the new price as a number.", status_code=422
        ) from exc
    if not new.is_finite() or new <= 0:
        raise AppError("INVALID_PRICE", "The price must be greater than 0.", status_code=422)

    # Open liquidity-provider exit requests of the property, BEFORE the property row: a
    # provider funding one locks the request and then the property, so must this.
    open_exits = list(
        (
            await session.execute(
                select(LpExitRequest)
                .where(LpExitRequest.property_id == property_id, LpExitRequest.status == "open")
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    # the property row: everything that prices against it (purchases, plans, listings, exits)
    # takes the same lock
    prop = (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    if prop.status not in PUBLIC_STATUSES:
        raise AppError(
            "NOT_PUBLISHED",
            "This listing is not published yet: set its price under Listing details.",
            status_code=409,
        )
    old = decimal.Decimal(prop.unit_price)
    if new == old:
        raise AppError("SAME_PRICE", f"The unit price is already {usd(old)}.", status_code=409)
    move = change_pct(old, new)
    if abs(move) > MAX_STEP_PCT and not confirm_large:
        raise AppError(
            "LARGE_CHANGE",
            f"{usd(old)} to {usd(new)} is a change of {signed_pct(move)} in one step. If that "
            "is right, tick the confirmation and save again.",
            status_code=422,
            details={"change_pct": str(move), "max_step_pct": str(MAX_STEP_PCT)},
        )

    row = PropertyPrice(
        property_id=prop.id,
        previous_price=old,
        price=new,
        label=_clean(label, LABEL_MAX),
        note=_clean(note, NOTE_MAX),
        created_by=actor_id,
        # the time AFTER the listing's lock was taken (not the transaction's start, which is
        # the column default): two changes recorded at once keep the order they happened in
        created_at=_utcnow(),
    )
    session.add(row)
    if prop.launch_price is None:
        prop.launch_price = old  # the first change: what it was launched at, kept from now on

    # The units still for sale are offered at the new price from now on, so the offering's
    # total follows them (sold units keep what was paid for them). Funding progress therefore
    # stays "money in / all the money the offering takes" and reaches 100% exactly at sell-out.
    before_total = decimal.Decimal(prop.total_value)
    prop.total_value = _q(before_total + (new - old) * int(prop.available_units or 0))
    # The minimum stays the same number of whole units (it is always a multiple of the price).
    before_minimum = decimal.Decimal(prop.minimum_investment or 0)
    min_units = max(1, int((before_minimum / old).to_integral_value(decimal.ROUND_CEILING)))
    prop.minimum_investment = _q(new * min_units)
    prop.unit_price = new
    prop.updated_at = _utcnow()
    _recompute_progress(prop)
    await session.flush()

    await write_audit(
        session,
        action="property.price_recorded",
        entity_type="property",
        entity_id=str(prop.id),
        actor_id=actor_id,
        before={
            "unit_price": str(old),
            "total_value": str(before_total),
            "minimum_investment": str(before_minimum),
        },
        after={
            "unit_price": str(new),
            "total_value": str(prop.total_value),
            "minimum_investment": str(prop.minimum_investment),
            "change_pct": str(move),
            "label": row.label,
            "note": row.note,
        },
    )

    # exit requests priced at the old price end here (their units are free again)
    for req in open_exits:
        req.status = "expired"
        await write_audit(
            session,
            action="lp.exit_request.repriced",
            entity_type="lp_exit_request",
            entity_id=str(req.id),
            actor_id=actor_id,
            after={
                "seller_id": str(req.seller_id),
                "property_id": str(prop.id),
                "units_remaining": req.units_remaining,
                "priced_at": str(req.unit_price_snapshot),
                "new_price": str(new),
            },
        )
        await notification_service.notify(
            session,
            user_id=req.seller_id,
            type="liquidity",
            title="Exit request closed: the price changed",
            message=(
                f"Your request to exit {req.units_remaining} unit(s) of {prop.title} was "
                f"priced at {usd(req.unit_price_snapshot)} a unit. The unit price is now "
                f"{usd(new)}, so the request was closed and your units are free again. "
                "Make a new request to exit at the new price."
            ),
            email_category="investment_updates",
        )

    phase = f" {row.label}." if row.label else ""
    message = (
        f"The unit price of {prop.title} is now {usd(new)} ({signed_pct(move)} from "
        f"{usd(old)}).{phase} Your holding is valued at the new price."
    )
    # A listing on the secondary market keeps the price its seller set: say so to those who
    # have one, or it would quietly stay on sale below (or above) the new price.
    listed = set(
        (
            await session.execute(
                select(SecondaryListing.seller_id).where(
                    SecondaryListing.property_id == prop.id, SecondaryListing.status == "active"
                )
            )
        ).scalars()
    )
    for user_id in await _holders(session, prop.id):
        await notification_service.notify(
            session,
            user_id=user_id,
            type="investment",
            title=f"New unit price: {prop.title}",
            message=(
                message + " Your listing on the secondary market keeps the price you set: "
                "cancel it and list again to change that price."
                if user_id in listed
                else message
            ),
            email_category="investment_updates",
        )
    return row
