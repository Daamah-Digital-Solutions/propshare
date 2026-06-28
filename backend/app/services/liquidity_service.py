"""Liquidity-provider engine — ACTIVE rail (Phase 9).

The ACTIVE product: an exiting investor lists an **instant-buyout exit request** at a
liquidity discount; a liquidity provider funds it, acquiring the units (risk-bearing)
and earning rental (as the new owner, via Phase 6) + resale (via Phase 8).

Money safeguards mirror Phase 8 exactly:
  * **Server-authoritative, seller-price-locked pricing.** discount + fee come from
    ``platform_settings`` off the property ``unit_price`` and are SNAPSHOTTED on the
    request at creation. ``seller_net`` is what the seller agreed to and is paid
    verbatim — the fill never recomputes the payout, it only band-checks the snapshot.
  * **Atomic buyback.** Lock order **exit_request → property → wallets (sorted by
    str(user_id))**. Debit the LP ``lp_price``; credit the seller ``lp_price`` and
    withhold the liquidity fee (explicit ``fee`` ledger row, retained as revenue);
    move units seller→LP in ``ownership_ledger`` (Σ/property conserved). All-or-nothing.
  * **Concurrency.** ``SELECT … FOR UPDATE`` on the exit-request row → exactly one LP
    wins; racers get 409. ``units_remaining >= 0`` CHECK is the DB backstop.
  * **Cross-market reservation.** Ownership is validated against ``reserved_units``
    (secondary listings + open exit requests) under the property lock — a unit can
    never sit on both markets.

``lp_positions(active)`` is an append-only acquisition/audit record; current holdings
always come from ``ownership_ledger`` (never from the position row's status).
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import LpExitRequest, LpPosition, Property, Wallet
from app.models.base import TransactionType
from app.models.investments import OwnershipLedger
from app.services import notification_service, secondary_service, settings_service, wallet_service

_CENTS = decimal.Decimal("0.01")
_HUNDRED = decimal.Decimal(100)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _q(value: decimal.Decimal) -> decimal.Decimal:
    return value.quantize(_CENTS, rounding=decimal.ROUND_HALF_UP)


def _price_for(
    unit_price: decimal.Decimal,
    units: int,
    discount_pct: decimal.Decimal,
    fee_pct: decimal.Decimal,
) -> dict[str, decimal.Decimal]:
    """Server-authoritative payout math: discount is the LP's spread (seller haircut);
    the fee is platform revenue withheld from the discounted price."""
    gross = _q(unit_price * units)
    lp_price = _q(gross * (_HUNDRED - discount_pct) / _HUNDRED)
    liquidity_fee = _q(lp_price * fee_pct / _HUNDRED)
    seller_net = _q(lp_price - liquidity_fee)
    return {
        "gross": gross,
        "lp_price": lp_price,
        "liquidity_fee": liquidity_fee,
        "seller_net": seller_net,
    }


async def _net_holding(session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(OwnershipLedger.units), 0)).where(
            OwnershipLedger.user_id == user_id,
            OwnershipLedger.property_id == property_id,
        )
    )
    return int(total or 0)


# --- seller: create / cancel exit request ---------------------------------- #
async def create_exit_request(
    session: AsyncSession,
    *,
    seller_id: uuid.UUID,
    property_id: uuid.UUID,
    units: int,
    idempotency_key: str | None = None,
    now: dt.datetime | None = None,
) -> dict:
    if units < 1:
        raise AppError("INVALID_UNITS", "You must exit at least one unit.", status_code=422)

    if idempotency_key:
        existing = (
            await session.execute(
                select(LpExitRequest).where(LpExitRequest.idempotency_key == idempotency_key)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return _request_result(existing)

    prop = (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)

    holding = await _net_holding(session, seller_id, property_id)
    if holding < 1:
        raise AppError("NOT_AN_OWNER", "You do not own units of this property.", status_code=422)
    # Shared cross-market reservation (secondary listings + open exit requests).
    reserved = await secondary_service.reserved_units(session, seller_id, property_id)
    if units > holding - reserved:
        raise AppError(
            "INSUFFICIENT_UNITS",
            "You do not have that many unreserved units to exit.",
            status_code=422,
            details={"holding": holding, "already_reserved": reserved, "requested": units},
        )

    sett = await settings_service.get_liquidity_settings(session)
    discount = decimal.Decimal(str(sett["discount_pct"]))
    fee = decimal.Decimal(str(sett["fee_pct"]))
    price = _price_for(prop.unit_price, units, discount, fee)
    ttl = int(sett["ttl_minutes"])

    req = LpExitRequest(
        seller_id=seller_id,
        property_id=property_id,
        units=units,
        units_remaining=units,
        unit_price_snapshot=prop.unit_price,
        discount_pct_snapshot=discount,
        fee_pct_snapshot=fee,
        gross=price["gross"],
        lp_price=price["lp_price"],
        liquidity_fee=price["liquidity_fee"],
        seller_net=price["seller_net"],
        status="open",
        idempotency_key=idempotency_key,
        expires_at=(now or _utcnow()) + dt.timedelta(minutes=ttl),
    )
    session.add(req)
    await session.flush()
    await write_audit(
        session,
        action="lp.exit_request.created",
        entity_type="lp_exit_request",
        entity_id=str(req.id),
        actor_id=seller_id,
        after={
            "property_id": str(property_id),
            "units": units,
            "unit_price": str(prop.unit_price),
            "discount_pct": str(discount),
            "fee_pct": str(fee),
            "lp_price": str(price["lp_price"]),
            "seller_net": str(price["seller_net"]),
        },
    )
    return _request_result(req)


async def cancel_exit_request(
    session: AsyncSession, *, seller_id: uuid.UUID, request_id: uuid.UUID
) -> dict:
    req = (
        await session.execute(
            select(LpExitRequest).where(LpExitRequest.id == request_id).with_for_update()
        )
    ).scalar_one_or_none()
    if req is None:
        raise AppError("NOT_FOUND", "Exit request not found", status_code=404)
    if req.seller_id != seller_id:
        raise AppError("FORBIDDEN", "You can only cancel your own request.", status_code=403)
    if req.status != "open":
        raise AppError("INVALID_STATE", "Only an open request can be cancelled.", status_code=409)
    req.status = "cancelled"
    req.cancelled_at = _utcnow()
    await write_audit(
        session,
        action="lp.exit_request.cancelled",
        entity_type="lp_exit_request",
        entity_id=str(req.id),
        actor_id=seller_id,
    )
    return {"request_id": req.id, "status": req.status}


# --- LP: fund an exit request (atomic buyback) ----------------------------- #
async def fund_exit_request(
    session: AsyncSession,
    *,
    lp_user_id: uuid.UUID,
    request_id: uuid.UUID,
    units: int,
    idempotency_key: str,
    now: dt.datetime | None = None,
) -> dict:
    if units < 1:
        raise AppError("INVALID_UNITS", "You must fund at least one unit.", status_code=422)

    # Idempotency-Key replay -> the existing position (no double-fund).
    existing = (
        await session.execute(
            select(LpPosition).where(LpPosition.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _position_result(existing)

    # Lock #1: the exit-request row — serializes competing LPs (exactly one wins).
    req = (
        await session.execute(
            select(LpExitRequest).where(LpExitRequest.id == request_id).with_for_update()
        )
    ).scalar_one_or_none()
    if req is None:
        raise AppError("NOT_FOUND", "Exit request not found", status_code=404)
    if req.status != "open":
        raise AppError("REQUEST_NOT_OPEN", "This exit request is no longer open.", status_code=409)
    if req.seller_id == lp_user_id:
        raise AppError(
            "CANNOT_FUND_OWN_REQUEST", "You cannot fund your own exit request.", status_code=409
        )
    if (now or _utcnow()) >= req.expires_at:
        # Guard only — raising rolls back the tx, so we don't mutate status here; the
        # request lapses by TTL and is filtered out of the open order book.
        raise AppError("REQUEST_EXPIRED", "This exit request has expired.", status_code=409)
    if units > req.units_remaining:
        raise AppError(
            "INSUFFICIENT_UNITS",
            "The request does not have that many units remaining.",
            status_code=409,
            details={"units_remaining": req.units_remaining, "requested": units},
        )

    seller_id = req.seller_id
    property_id = req.property_id

    # Lock #2: the property row.
    prop = (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)

    # Seller price-lock: pay from the SNAPSHOT rates (never re-priced). The fresh
    # re-derive below is a sanity BAND check only — it can reject a stale fill but
    # never changes the agreed payout.
    fill = _price_for(
        req.unit_price_snapshot, units, req.discount_pct_snapshot, req.fee_pct_snapshot
    )
    sett = await settings_service.get_liquidity_settings(session)
    fresh = _price_for(
        prop.unit_price, units, decimal.Decimal(str(sett["discount_pct"])), req.fee_pct_snapshot
    )
    band = decimal.Decimal(str(sett["band_pct"])) / _HUNDRED
    if fresh["lp_price"] <= 0:
        raise AppError(
            "PRICE_BAND_EXCEEDED", "Stale price — re-create the request.", status_code=409
        )
    deviation = abs(fill["lp_price"] - fresh["lp_price"]) / fresh["lp_price"]
    if deviation > band:
        # Guard only — the raise rolls back, so we don't mutate status (it would be a
        # no-op). The seller re-creates at current terms; the stale one lapses by TTL.
        raise AppError(
            "PRICE_BAND_EXCEEDED",
            "The request price is stale beyond the allowed band; please re-create it.",
            status_code=409,
            details={"deviation_pct": str(_q(deviation * _HUNDRED))},
        )

    lp_price = fill["lp_price"]
    liquidity_fee = fill["liquidity_fee"]

    # Lock #3: both wallets, sorted by str(user_id) (matches the global hierarchy).
    for uid in sorted([lp_user_id, seller_id], key=str):
        await session.execute(select(Wallet).where(Wallet.user_id == uid).with_for_update())

    # Debit the LP the discounted buyback price. Over-balance -> 422, whole tx rolls back.
    lp_wallet = await wallet_service.debit(
        session,
        user_id=lp_user_id,
        reference_id=req.id,
        line_items=[(TransactionType.investment, lp_price, f"LP buyback — {prop.title}")],
        actor_id=lp_user_id,
    )
    lp_wallet.total_invested = lp_wallet.total_invested + lp_price

    # Credit the seller the full discounted price, then withhold the liquidity fee as an
    # explicit ledger row (retained revenue) -> seller nets seller_net; balance==SUM(ledger).
    await wallet_service.credit(
        session,
        user_id=seller_id,
        amount=lp_price,
        reference_id=req.id,
        tx_type=TransactionType.secondary_sale,
        description=f"Instant exit — {prop.title}",
        actor_id=lp_user_id,
    )
    if liquidity_fee > 0:
        await wallet_service.debit(
            session,
            user_id=seller_id,
            reference_id=req.id,
            line_items=[(TransactionType.fee, liquidity_fee, "Liquidity fee")],
            actor_id=lp_user_id,
        )

    # Move ownership seller -> LP (Σ/property conserved). LP's acquired row carries the
    # platform management-fee rate at acquisition (Decision 2).
    lp_fee_rate = await settings_service.get_management_fee_pct(session)
    session.add(
        OwnershipLedger(
            user_id=seller_id,
            property_id=property_id,
            investment_id=None,
            units=-units,
            unit_price=req.unit_price_snapshot,
            reason="lp_buyback",
        )
    )
    session.add(
        OwnershipLedger(
            user_id=lp_user_id,
            property_id=property_id,
            investment_id=None,
            units=units,
            unit_price=req.unit_price_snapshot,
            reason="lp_acquire",
            fee_rate=lp_fee_rate,
        )
    )

    req.units_remaining -= units
    if req.units_remaining == 0:
        req.status = "filled"
        req.filled_at = _utcnow()

    position = LpPosition(
        lp_user_id=lp_user_id,
        classification="active",
        principal_amount=lp_price,
        status="active",
        idempotency_key=idempotency_key,
        exit_request_id=req.id,
        property_id=property_id,
        units=units,
        unit_price_snapshot=req.unit_price_snapshot,
        discount_pct=req.discount_pct_snapshot,
        spread_at_entry=_q(fill["gross"] - lp_price),
    )
    session.add(position)
    await session.flush()

    await write_audit(
        session,
        action="lp.exit_request.funded",
        entity_type="lp_position",
        entity_id=str(position.id),
        actor_id=lp_user_id,
        after={
            "request_id": str(req.id),
            "property_id": str(property_id),
            "seller_id": str(seller_id),
            "units": units,
            "lp_price": str(lp_price),
            "liquidity_fee": str(liquidity_fee),
            "seller_net": str(_q(lp_price - liquidity_fee)),
        },
    )
    await notification_service.notify(
        session,
        user_id=seller_id,
        type="liquidity",
        title="Instant exit funded",
        message=f"Your exit of {units} unit(s) of {prop.title} was funded.",
    )
    await notification_service.notify(
        session,
        user_id=lp_user_id,
        type="liquidity",
        title="Liquidity deployed",
        message=f"You acquired {units} unit(s) of {prop.title}.",
    )
    return _position_result(position)


# --- reads ----------------------------------------------------------------- #
async def list_open_requests(
    session: AsyncSession, *, property_id: uuid.UUID | None = None
) -> list[dict]:
    stmt = (
        select(LpExitRequest, Property)
        .join(Property, LpExitRequest.property_id == Property.id)
        .where(LpExitRequest.status == "open", LpExitRequest.units_remaining > 0)
        .order_by(LpExitRequest.created_at.desc())
    )
    if property_id is not None:
        stmt = stmt.where(LpExitRequest.property_id == property_id)
    rows = (await session.execute(stmt)).all()
    return [_request_result(req, prop) for req, prop in rows]


async def list_my_exit_requests(session: AsyncSession, seller_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(LpExitRequest, Property)
            .join(Property, LpExitRequest.property_id == Property.id)
            .where(LpExitRequest.seller_id == seller_id)
            .order_by(LpExitRequest.created_at.desc())
        )
    ).all()
    return [_request_result(req, prop) for req, prop in rows]


async def list_my_positions(session: AsyncSession, lp_user_id: uuid.UUID) -> list[dict]:
    """ACTIVE acquisition history (audit). NOT current holdings — those come from the
    ownership ledger (see the holdings endpoint)."""
    rows = (
        (
            await session.execute(
                select(LpPosition)
                .where(
                    LpPosition.lp_user_id == lp_user_id,
                    LpPosition.classification == "active",
                )
                .order_by(LpPosition.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_position_result(p) for p in rows]


# --- helpers --------------------------------------------------------------- #
def _request_result(req: LpExitRequest, prop: Property | None = None) -> dict:
    return {
        "request_id": req.id,
        "property_id": str(req.property_id),
        "property_title": prop.title if prop else None,
        "property_location": prop.location if prop else None,
        "seller_id": str(req.seller_id),
        "units": req.units,
        "units_remaining": req.units_remaining,
        "unit_price": str(req.unit_price_snapshot),
        "discount_pct": str(req.discount_pct_snapshot),
        "fee_pct": str(req.fee_pct_snapshot),
        "gross": str(req.gross),
        "lp_price": str(req.lp_price),
        "liquidity_fee": str(req.liquidity_fee),
        "seller_net": str(req.seller_net),
        "status": req.status,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
    }


async def expire_open_requests(session: AsyncSession, *, now: dt.datetime | None = None) -> int:
    """Flip lapsed ``open`` exit requests to ``expired`` so their units stop being
    reserved across both markets (``secondary_service.reserved_units`` counts only
    ``status='open'``). A reservation is purely that count — no units were ever debited —
    so changing the status releases them with no money/ledger move.

    Cron-able + idempotent: ``FOR UPDATE SKIP LOCKED`` (a concurrent fund on the same row
    is never blocked or double-processed); already-expired rows aren't reselected.
    """
    cutoff = now or _utcnow()
    rows = (
        (
            await session.execute(
                select(LpExitRequest)
                .where(
                    LpExitRequest.status == "open",
                    LpExitRequest.expires_at < cutoff,
                )
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    count = 0
    for req in rows:
        req.status = "expired"
        await write_audit(
            session,
            action="lp.exit_request.expired",
            entity_type="lp_exit_request",
            entity_id=str(req.id),
            after={
                "seller_id": str(req.seller_id),
                "property_id": str(req.property_id),
                "units_remaining": req.units_remaining,
            },
        )
        count += 1
    return count


def _position_result(p: LpPosition) -> dict:
    return {
        "position_id": p.id,
        "classification": p.classification,
        "property_id": str(p.property_id) if p.property_id else None,
        "units_acquired": p.units,
        "principal": str(p.principal_amount),
        "spread_at_entry": str(p.spread_at_entry) if p.spread_at_entry is not None else None,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
