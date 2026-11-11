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

Units of a running installment plan (0042). An investor on a plan can offer some of its units,
or all, to a liquidity provider. The provider buys them at the discounted price like any units,
but takes over their share of the installments still to come: the provider pays the seller the
discounted value of the units LESS that share of the principal still to pay (``cash``); the
liquidity fee is withheld from that cash. The units become the provider's own plan (some of the
plan: a new plan with the same dates and its share of every payment; all of it: the plan
itself), charged from the provider's wallet on its dates. The cash is worked out when the
provider funds (the seller may have paid an installment since), so the provider sends the cash
they were shown and a fill that no longer matches it is refused. A plan's units change hands
only when no installment of it is overdue. Lock order: request -> the plan's payments -> the
plan -> property -> wallets.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import InstallmentPlan, LpExitRequest, LpPosition, Property, Wallet
from app.models.base import TransactionType
from app.models.investments import OwnershipLedger
from app.services import (
    installment_service,
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
    plan_id: uuid.UUID | None = None,
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
            return await _request_out(session, existing)

    if plan_id is not None:
        return await _create_plan_request(
            session,
            seller_id=seller_id,
            plan_id=plan_id,
            units=units,
            idempotency_key=idempotency_key,
            now=now,
        )

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
    expected_cash: str | None = None,
) -> dict:
    """``expected_cash``: for units of an installment plan only, the cash the provider was
    shown (see ``_fund_plan_request``)."""
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
    if req.plan_id is not None:
        return await _fund_plan_request(
            session,
            req=req,
            lp_user_id=lp_user_id,
            units=units,
            idempotency_key=idempotency_key,
            expected_cash=expected_cash,
        )

    seller_id = req.seller_id
    property_id = req.property_id

    # Lock #2: the property row.
    prop = (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    # The request was priced at the unit price of its day. Recording a new price closes the
    # open requests (price_service), but one made in the same instant can slip past that:
    # a seller is never bought out at a price the property no longer has.
    if decimal.Decimal(req.unit_price_snapshot) != decimal.Decimal(prop.unit_price):
        raise AppError(
            "PRICE_CHANGED",
            "The unit price of this property changed after this request was made, so it can "
            "no longer be funded. The seller can make a new request at the new price.",
            status_code=409,
        )

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
        .where(
            LpExitRequest.status == "open",
            LpExitRequest.units_remaining > 0,
            # one priced at a price the property no longer has cannot be funded
            LpExitRequest.unit_price_snapshot == Property.unit_price,
        )
        .order_by(LpExitRequest.created_at.desc())
    )
    if property_id is not None:
        stmt = stmt.where(LpExitRequest.property_id == property_id)
    rows = (await session.execute(stmt)).all()
    out = []
    for req, prop in rows:
        row = await _request_out(session, req, prop)
        if req.plan_id is not None and row.get("position") is None:
            continue  # its plan was paid off or changed hands: nothing left to fund here
        out.append(row)
    return out


async def list_my_exit_requests(session: AsyncSession, seller_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(LpExitRequest, Property)
            .join(Property, LpExitRequest.property_id == Property.id)
            .where(LpExitRequest.seller_id == seller_id)
            .order_by(LpExitRequest.created_at.desc())
        )
    ).all()
    return [await _request_out(session, req, prop) for req, prop in rows]


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
        # 0042: units of a running installment plan
        "plan_id": req.plan_id,
        "position": None,
    }


async def expire_open_requests(session: AsyncSession, *, now: dt.datetime | None = None) -> int:
    """Flip lapsed ``open`` exit requests to ``expired`` so their units stop being
    reserved across both markets (``secondary_service.reserved_units`` counts only
    ``status='open'``). A reservation is purely that count — no units were ever debited —
    so changing the status releases them with no money/ledger move. A request priced at a
    unit price the property no longer has (it slipped past a price change) lapses too.

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
                    or_(
                        LpExitRequest.expires_at < cutoff,
                        LpExitRequest.unit_price_snapshot
                        != select(Property.unit_price)
                        .where(Property.id == LpExitRequest.property_id)
                        .scalar_subquery(),
                    ),
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
        # 0042: the installment plan the provider took with the units
        "plan_id": p.plan_id,
    }


# --- units of a running installment plan (0042) ------------------------------- #
def _lp_unit_price(unit_price: decimal.Decimal, discount_pct: decimal.Decimal) -> decimal.Decimal:
    """The provider's price per unit: the unit price less the liquidity discount."""
    return _q(decimal.Decimal(unit_price) * (_HUNDRED - discount_pct) / _HUNDRED)


def _plan_fill(
    plan: InstallmentPlan,
    payments: list,
    units: int,
    unit_price: decimal.Decimal,
    discount_pct: decimal.Decimal,
    fee_pct: decimal.Decimal,
) -> dict:
    """What ``units`` of the plan come to for a provider: the discounted value of the units
    (``lp_value``), their share of the principal still to pay, which the provider takes over,
    the ``cash`` the provider pays the seller now (the difference), the liquidity fee withheld
    from it and what the seller nets. ``figures`` are the part's (its schedule included)."""
    price = _price_for(unit_price, units, discount_pct, fee_pct)
    fig = installment_service.part_figures(
        plan, payments, units, _lp_unit_price(unit_price, discount_pct)
    )
    cash = _q(price["lp_price"] - fig["remaining_principal"])
    fee = _q(cash * fee_pct / _HUNDRED) if cash > 0 else decimal.Decimal("0.00")
    return {
        "gross": price["gross"],
        "lp_value": price["lp_price"],
        "cash": cash,
        "liquidity_fee": fee,
        "seller_net": _q(cash - fee),
        "figures": fig,
    }


def _plan_position(fill: dict) -> dict:
    """A plan request's figures as the API gives them (money as text)."""
    fig = fill["figures"]
    return {
        "plan_id": fig["plan_id"],
        "units": fig["units"],
        "plan_units": fig.get("plan_units", fig["units"]),
        "vested_units": fig["vested_units"],
        "lp_unit_price": str(fig["price"]),
        "lp_value": str(fill["lp_value"]),
        "paid_principal": str(fig["paid_principal"]),
        "remaining_principal": str(fig["remaining_principal"]),
        "remaining_fees": str(fig["remaining_fees"]),
        "cash": str(fill["cash"]),
        "liquidity_fee": str(fill["liquidity_fee"]),
        "seller_net": str(fill["seller_net"]),
        "installments_left": fig["installments_left"],
        "next_due": fig["next_due"],
        "schedule": installment_service.schedule_rows(fig["schedule"]),
    }


async def _request_out(
    session: AsyncSession, req: LpExitRequest, prop: Property | None = None
) -> dict:
    """``_request_result`` with, for units of a running plan, what the units still offered come
    to today (``position``; None once the plan is no longer the seller's running plan)."""
    if prop is None:
        prop = await session.get(Property, req.property_id)
    out = _request_result(req, prop)
    if req.plan_id is None or req.units_remaining < 1:
        return out
    plan = await session.get(InstallmentPlan, req.plan_id)
    if plan is None or plan.status != "active" or plan.investor_id != req.seller_id:
        return out
    units = min(req.units_remaining, plan.units_total)
    payments = await installment_service._payments_for(session, plan.id)
    fill = _plan_fill(
        plan,
        payments,
        units,
        req.unit_price_snapshot,
        req.discount_pct_snapshot,
        req.fee_pct_snapshot,
    )
    out["position"] = _plan_position(fill)
    return out


async def quote_plan_request(
    session: AsyncSession, *, lp_user_id: uuid.UUID, request_id: uuid.UUID, units: int
) -> dict:
    """What funding ``units`` of an exit request for plan units comes to, before funding: the
    cash to the seller and the schedule the provider would take over. Nothing is held."""
    req = await session.get(LpExitRequest, request_id)
    if req is None or req.plan_id is None:
        raise AppError("NOT_FOUND", "Exit request not found", status_code=404)
    if req.status != "open":
        raise AppError("REQUEST_NOT_OPEN", "This exit request is no longer open.", status_code=409)
    if req.seller_id == lp_user_id:
        raise AppError(
            "CANNOT_FUND_OWN_REQUEST", "You cannot fund your own exit request.", status_code=409
        )
    plan = await session.get(InstallmentPlan, req.plan_id)
    if plan is None or plan.status != "active" or plan.investor_id != req.seller_id:
        raise AppError("REQUEST_NOT_OPEN", "This exit request is no longer open.", status_code=409)
    if not 1 <= units <= min(req.units_remaining, plan.units_total):
        raise AppError(
            "INSUFFICIENT_UNITS",
            f"Choose between 1 and {req.units_remaining} unit(s).",
            status_code=422,
            details={"units_remaining": req.units_remaining, "requested": units},
        )
    payments = await installment_service._payments_for(session, plan.id)
    installment_service.require_no_overdue(payments, whose="seller")
    fill = _plan_fill(
        plan,
        payments,
        units,
        req.unit_price_snapshot,
        req.discount_pct_snapshot,
        req.fee_pct_snapshot,
    )
    out = _plan_position(fill)
    out["request_id"] = req.id
    out["units_remaining"] = req.units_remaining
    out["whole"] = units == plan.units_total
    return out


async def _create_plan_request(
    session: AsyncSession,
    *,
    seller_id: uuid.UUID,
    plan_id: uuid.UUID,
    units: int,
    idempotency_key: str | None,
    now: dt.datetime | None,
) -> dict:
    """Offer ``units`` of a running plan (some, or all) to liquidity providers."""
    # the installment module's lock order: the plan's payments, the plan, then the property
    plan, payments = await installment_service._lock_plan_rows(session, plan_id)
    if plan is None or plan.investor_id != seller_id:
        raise AppError("NOT_FOUND", "Installment plan not found.", status_code=404)
    if plan.status != "active":
        raise AppError(
            "PLAN_NOT_RUNNING",
            "Only a plan that is running can be offered this way. A paid-off plan's units are "
            "ordinary units: offer them like any others.",
            status_code=409,
        )
    prop = (
        await session.execute(
            select(Property).where(Property.id == plan.property_id).with_for_update()
        )
    ).scalar_one()
    if await secondary_service._nova_pledged(session, plan.id):
        raise AppError("UNITS_PLEDGED", secondary_service._PLEDGED_MESSAGE, status_code=409)
    installment_service.require_no_overdue(payments)
    free = await installment_service.free_plan_units(session, plan)
    if units > free:
        raise AppError(
            "INSUFFICIENT_UNITS",
            f"You can offer up to {free} unit(s) of this plan now (the rest are listed on the "
            "secondary market or already offered to a liquidity provider).",
            status_code=422,
            details={"free_units": free, "requested": units},
        )

    sett = await settings_service.get_liquidity_settings(session)
    discount = decimal.Decimal(str(sett["discount_pct"]))
    fee = decimal.Decimal(str(sett["fee_pct"]))
    fill = _plan_fill(plan, payments, units, prop.unit_price, discount, fee)
    if fill["cash"] <= 0:
        raise AppError(
            "PRICE_TOO_LOW",
            f"At the liquidity price ({_lp_unit_price(prop.unit_price, discount)} a unit) these "
            f"units are worth {fill['lp_value']}, which does not cover the "
            f"{fill['figures']['remaining_principal']} still to pay on them. You can offer them "
            "on the secondary market instead.",
            status_code=422,
            details={
                "lp_value": str(fill["lp_value"]),
                "remaining_principal": str(fill["figures"]["remaining_principal"]),
            },
        )
    ttl = int(sett["ttl_minutes"])
    req = LpExitRequest(
        seller_id=seller_id,
        property_id=plan.property_id,
        plan_id=plan.id,
        units=units,
        units_remaining=units,
        unit_price_snapshot=prop.unit_price,
        discount_pct_snapshot=discount,
        fee_pct_snapshot=fee,
        gross=fill["gross"],
        # for plan units, what the provider pays now (the discounted value less the
        # installments taken over), the fee withheld from it and what the seller nets
        lp_price=fill["cash"],
        liquidity_fee=fill["liquidity_fee"],
        seller_net=fill["seller_net"],
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
            "property_id": str(plan.property_id),
            "plan_id": str(plan.id),
            "units": units,
            "plan_units": plan.units_total,
            "unit_price": str(prop.unit_price),
            "discount_pct": str(discount),
            "fee_pct": str(fee),
            "lp_value": str(fill["lp_value"]),
            "remaining_principal": str(fill["figures"]["remaining_principal"]),
            "cash": str(fill["cash"]),
            "seller_net": str(fill["seller_net"]),
        },
    )
    out = _request_result(req, prop)
    out["position"] = _plan_position(fill)
    return out


async def _fund_plan_request(
    session: AsyncSession,
    *,
    req: LpExitRequest,
    lp_user_id: uuid.UUID,
    units: int,
    idempotency_key: str,
    expected_cash: str | None,
) -> dict:
    """A provider funds ``units`` of an exit request for plan units. The caller holds the
    request row and has checked it is open, not expired, not the provider's own, and has the
    units."""
    gone = AppError("REQUEST_NOT_OPEN", "This exit request is no longer open.", status_code=409)
    assert req.plan_id is not None
    plan, payments = await installment_service._lock_plan_rows(session, req.plan_id)
    seller_id = req.seller_id
    if plan is None or plan.status != "active" or plan.investor_id != seller_id:
        raise gone
    if units > plan.units_total:  # the request outgrew the plan: a guard, not a path
        raise gone
    prop = (
        await session.execute(
            select(Property).where(Property.id == plan.property_id).with_for_update()
        )
    ).scalar_one()
    if decimal.Decimal(req.unit_price_snapshot) != decimal.Decimal(prop.unit_price):
        raise AppError(
            "PRICE_CHANGED",
            "The unit price of this property changed after this request was made, so it can "
            "no longer be funded. The seller can make a new request at the new price.",
            status_code=409,
        )
    if await secondary_service._nova_pledged(session, plan.id):
        raise AppError("UNITS_PLEDGED", secondary_service._PLEDGED_MESSAGE, status_code=409)
    installment_service.require_no_overdue(payments, whose="seller")

    fill = _plan_fill(
        plan,
        payments,
        units,
        req.unit_price_snapshot,
        req.discount_pct_snapshot,
        req.fee_pct_snapshot,
    )
    sett = await settings_service.get_liquidity_settings(session)
    fresh = _price_for(
        prop.unit_price, units, decimal.Decimal(str(sett["discount_pct"])), req.fee_pct_snapshot
    )
    band = decimal.Decimal(str(sett["band_pct"])) / _HUNDRED
    if fresh["lp_price"] <= 0 or (
        abs(fill["lp_value"] - fresh["lp_price"]) / fresh["lp_price"] > band
    ):
        raise AppError(
            "PRICE_BAND_EXCEEDED",
            "The request price is stale beyond the allowed band; please re-create it.",
            status_code=409,
        )
    cash = fill["cash"]
    if cash <= 0:
        raise gone
    try:
        agreed = (
            _q(decimal.Decimal(str(expected_cash))) if expected_cash not in (None, "") else None
        )
    except (decimal.InvalidOperation, ValueError):
        agreed = decimal.Decimal("-1")
    if agreed is not None and agreed != cash:
        raise AppError(
            "POSITION_CHANGED",
            "The amounts of these units changed since you opened them (the seller may have paid "
            "an installment). Review them and confirm again.",
            status_code=409,
            details={"cash": str(cash)},
        )
    liquidity_fee = fill["liquidity_fee"]
    fig = fill["figures"]

    for uid in sorted([lp_user_id, seller_id], key=str):
        await session.execute(select(Wallet).where(Wallet.user_id == uid).with_for_update())
    lp_wallet = await wallet_service.debit(
        session,
        user_id=lp_user_id,
        reference_id=req.id,
        line_items=[
            (TransactionType.investment, cash, f"LP buyback — {prop.title} (installment plan)")
        ],
        actor_id=lp_user_id,
    )
    lp_wallet.total_invested = lp_wallet.total_invested + cash
    await wallet_service.credit(
        session,
        user_id=seller_id,
        amount=cash,
        reference_id=req.id,
        tx_type=TransactionType.secondary_sale,
        description=f"Instant exit — {prop.title} (installment plan)",
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

    whole = units == plan.units_total
    taken = await installment_service.take_plan_units(
        session,
        plan=plan,
        payments=payments,
        units=units,
        to_user_id=lp_user_id,
        entry_price=_lp_unit_price(req.unit_price_snapshot, req.discount_pct_snapshot),
        ledger_price=req.unit_price_snapshot,
        reasons=("lp_buyback", "lp_acquire"),
        ref_id=req.id,
        actor_id=lp_user_id,
    )

    req.units_remaining -= units
    if req.units_remaining == 0:
        req.status = "filled"
        req.filled_at = _utcnow()

    position = LpPosition(
        lp_user_id=lp_user_id,
        classification="active",
        principal_amount=cash,
        status="active",
        idempotency_key=idempotency_key,
        exit_request_id=req.id,
        property_id=plan.property_id,
        units=units,
        unit_price_snapshot=req.unit_price_snapshot,
        discount_pct=req.discount_pct_snapshot,
        spread_at_entry=_q(fill["gross"] - fill["lp_value"]),
        plan_id=taken.id,
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
            "property_id": str(plan.property_id),
            "seller_id": str(seller_id),
            "from_plan_id": str(plan.id),
            "plan_id": str(taken.id),
            "whole": whole,
            "units": units,
            "lp_value": str(fill["lp_value"]),
            "assumed_principal": str(fig["remaining_principal"]),
            "cash": str(cash),
            "liquidity_fee": str(liquidity_fee),
            "seller_net": str(fill["seller_net"]),
        },
    )
    if whole:
        seller_msg = (
            f"A liquidity provider took your installment plan in {prop.title} ({units} unit(s)) "
            f"and pays its remaining installments from now on. You received {cash}, less the "
            f"{liquidity_fee} liquidity fee."
        )
    else:
        seller_msg = (
            f"A liquidity provider took {units} unit(s) of your installment plan in "
            f"{prop.title}. You received {cash}, less the {liquidity_fee} liquidity fee. Your "
            f"plan keeps {plan.units_total} unit(s); each of its remaining installments is "
            "smaller by the provider's part."
        )
    await notification_service.notify(
        session,
        user_id=seller_id,
        type="liquidity",
        title="Instant exit funded",
        message=seller_msg,
        email_category="investment_updates",
    )
    next_due = f" The next one is due on {fig['next_due'].isoformat()}." if fig["next_due"] else ""
    await notification_service.notify(
        session,
        user_id=lp_user_id,
        type="liquidity",
        title="Liquidity deployed",
        message=(
            f"You acquired {units} unit(s) of {prop.title} on an installment plan, "
            f"{fig['vested_units']} of them yours already. {fig['installments_left']} "
            f"installment(s) remain ({fig['remaining_principal']} plus fees), charged from your "
            f"wallet on their dates.{next_due} The plan and its schedule are in your dashboard."
        ),
        email_category="investment_updates",
    )
    return _position_result(position)
