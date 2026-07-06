"""Investment engine (Phase 5) — the second money phase.

One purchase, two rails, all server-authoritative:

  * **wallet-funded** — fully atomic in ONE transaction: lock the property row
    (``FOR UPDATE``), then the wallet row, debit the buyer (subtotal + platform
    fee), allocate units, append the ownership ledger, flip the property to
    ``funded`` when the last unit sells. Lock order is strictly **property → wallet**.
  * **direct-pay** (Stripe card / NOWPayments crypto) — reserve units immediately
    (decrement ``available_units`` under the property lock, create a ``pending``
    investment with a 30-minute ``reservation_expires_at``), then a signed webhook
    confirms it (Phase 4 pattern). An unpaid reservation is released by
    ``expire_reservations``; a late webhook after expiry is reconciled (re-acquire
    units if still free, else refund the captured amount to the wallet).

Oversell protection: ``SELECT ... FOR UPDATE`` on the property row serializes
concurrent buyers; the ``properties.available_units >= 0`` CHECK is the DB
backstop. Amounts are ``Decimal`` and snapshotted onto the investment so a later
fee-rate change never rewrites history. The client never sends a price or fee.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import AuditLog, Investment, Property
from app.models.base import InvestmentStatus, PropertyStatus, TransactionType
from app.models.investments import OwnershipLedger
from app.services import (
    broker_service,
    notification_service,
    payment_service,
    settings_service,
    wallet_service,
)

_CENTS = decimal.Decimal("0.01")
_HUNDRED = decimal.Decimal(100)
RESERVATION_TTL = dt.timedelta(minutes=30)
# Direct-pay rails (reserve units -> hosted checkout -> webhook confirms). "pronova" is a
# branded rail that settles via Stripe card (D5); it behaves exactly like "card" except a
# server-applied discount reduces only the CHARGED amount (see create_investment).
_DIRECT_METHODS = {"card", "crypto", "pronova"}


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _q(value: decimal.Decimal) -> decimal.Decimal:
    return value.quantize(_CENTS, rounding=decimal.ROUND_HALF_UP)


def _recompute_progress(prop: Property) -> None:
    """Funding progress reflects CONFIRMED money (funded_amount / total_value)."""
    if prop.total_value and prop.total_value > 0:
        pct = (prop.funded_amount / prop.total_value) * decimal.Decimal(100)
        prop.funding_progress = min(decimal.Decimal(100), _q(pct))
    else:
        prop.funding_progress = decimal.Decimal(0)


def _quote(unit_price: decimal.Decimal, amount: decimal.Decimal, rates: dict) -> dict:
    """Server-authoritative money math from the requested USD amount."""
    if unit_price <= 0:
        raise AppError("INVALID_PROPERTY", "Property has no unit price.", status_code=409)
    units = int(amount // unit_price)
    subtotal = _q(unit_price * units)
    platform_fee = _q(subtotal * rates["platform_fee_pct"] / decimal.Decimal(100))
    return {
        "units": units,
        "subtotal": subtotal,
        "platform_fee": platform_fee,
        "total_charge": _q(subtotal + platform_fee),
    }


# --- Create (entry point) -------------------------------------------------- #
async def create_investment(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    property_id: uuid.UUID,
    amount: float,
    method: str,
    idempotency_key: str,
    success_url: str,
    cancel_url: str,
    ipn_url: str,
) -> dict:
    # Idempotency-Key replay -> return the existing investment (and its checkout, if any).
    existing = (
        await session.execute(
            select(Investment).where(Investment.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _result(existing, await _checkout_url_for(session, existing))

    # Fail fast on an unconfigured direct-pay provider BEFORE reserving any units.
    if method in _DIRECT_METHODS and not payment_service.provider_configured(method):
        provider = payment_service.provider_for(method)
        raise AppError(
            "PAYMENTS_NOT_CONFIGURED", f"{provider} is not configured yet.", status_code=503
        )

    # Lock the property row: this serializes concurrent buyers (oversell protection).
    prop = (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    if prop.status != PropertyStatus.active:
        raise AppError(
            "PROPERTY_NOT_OPEN", "This property is not open for investment.", status_code=409
        )

    amount_dec = decimal.Decimal(str(amount))
    rates = await settings_service.get_fee_rates(session)
    quote = _quote(prop.unit_price, amount_dec, rates)
    if quote["units"] < 1 or quote["subtotal"] < prop.minimum_investment:
        raise AppError(
            "AMOUNT_TOO_LOW",
            f"Minimum investment is {prop.minimum_investment} (1 unit = {prop.unit_price}).",
            status_code=422,
            details={"minimum_investment": str(prop.minimum_investment)},
        )
    if quote["units"] > prop.available_units:
        raise AppError(
            "INSUFFICIENT_UNITS",
            "Not enough units remain for this investment.",
            status_code=409,
            details={"available_units": prop.available_units, "requested": quote["units"]},
        )

    snapshot = {
        "platform_fee_pct": str(rates["platform_fee_pct"]),
        "management_fee_pct": str(rates["management_fee_pct"]),
    }
    # Pronova (D5, owner-set): a discount off the TOTAL payable on a rail that SETTLES VIA
    # STRIPE CARD. Reduce ONLY the amount charged — units, booked subtotal and platform fee
    # stay full, so the property funds in full and the discount is a platform-funded promo
    # subsidy (recorded on the investment snapshot + audited). Server-authoritative.
    if method == "pronova":
        pct = await settings_service.get_pronova_discount_pct(session)
        discount_amount = _q(quote["total_charge"] * pct / _HUNDRED)
        quote["total_charge"] = _q(quote["total_charge"] - discount_amount)
        snapshot["pronova_discount_pct"] = str(pct)
        snapshot["pronova_discount_amount"] = str(discount_amount)
    inv = Investment(
        user_id=user_id,
        property_id=prop.id,
        units=quote["units"],
        amount=quote["subtotal"],
        payment_method=None,
        idempotency_key=idempotency_key,
        unit_price_snapshot=prop.unit_price,
        platform_fee_amount=quote["platform_fee"],
        platform_fee_rate=rates["platform_fee_pct"],
        management_fee_rate=rates["management_fee_pct"],
        total_charged=quote["total_charge"],
        fee_settings_snapshot=snapshot,
        status=InvestmentStatus.pending,
    )
    session.add(inv)
    await session.flush()  # assign inv.id

    if method == "wallet":
        return await _fund_from_wallet(session, prop=prop, inv=inv, quote=quote)
    return await _reserve_for_direct_pay(
        session,
        prop=prop,
        inv=inv,
        method=method,
        success_url=success_url,
        cancel_url=cancel_url,
        ipn_url=ipn_url,
    )


async def _accrue_broker_commission(session: AsyncSession, inv: Investment) -> None:
    """Phase-11 hook: the buyer's one-time platform fee is platform revenue. If the buyer
    is a broker-referred client, accrue the broker's commission on it (idempotent on
    inv.id; no-op when there's no referring broker). Safe to call unconditionally."""
    fee = inv.platform_fee_amount
    if fee is None or fee <= 0:
        return
    await broker_service.accrue_commission(
        session,
        client_id=inv.user_id,
        revenue_event_type=broker_service.REVENUE_PLATFORM_FEE,
        revenue_event_id=inv.id,
        revenue_amount=fee,
    )


async def _fund_from_wallet(
    session: AsyncSession, *, prop: Property, inv: Investment, quote: dict
) -> dict:
    # Lock order property -> wallet: property is already locked above. If the buyer is
    # broker-referred, the broker's wallet is also credited in this tx, so pre-lock the
    # {buyer, broker} pair in the GLOBAL sorted order before any debit/credit.
    broker_id = await broker_service.referring_broker(session, inv.user_id)
    if broker_id is not None:
        await wallet_service.lock_wallets(session, [inv.user_id, broker_id])
    wallet = await wallet_service.debit(
        session,
        user_id=inv.user_id,
        reference_id=inv.id,
        line_items=[
            (TransactionType.investment, quote["subtotal"], f"Investment in {prop.title}"),
            (TransactionType.fee, quote["platform_fee"], "Platform fee (one-time)"),
        ],
    )
    wallet.total_invested = wallet.total_invested + quote["subtotal"]
    _allocate_units(session, prop, inv, confirmed_via="wallet")
    await _notify_confirmed(session, inv, prop)
    await write_audit(
        session,
        action="investment.confirmed",
        entity_type="investment",
        entity_id=str(inv.id),
        actor_id=inv.user_id,
        after={
            "via": "wallet",
            "units": inv.units,
            "subtotal": str(inv.amount),
            "platform_fee": str(inv.platform_fee_amount),
            "property_id": str(prop.id),
        },
    )
    await _accrue_broker_commission(session, inv)
    return _result(inv, None)


async def _reserve_for_direct_pay(
    session: AsyncSession,
    *,
    prop: Property,
    inv: Investment,
    method: str,
    success_url: str,
    cancel_url: str,
    ipn_url: str,
) -> dict:
    # Reserve the units now (held under the property lock) so they can't be oversold
    # while the off-platform payment is in flight. funded_amount/investors_count are
    # NOT touched until the webhook confirms.
    prop.available_units -= inv.units
    inv.reservation_expires_at = _utcnow() + RESERVATION_TTL
    payment = await payment_service.create_investment_checkout(
        session,
        user_id=inv.user_id,
        investment_id=inv.id,
        amount=inv.total_charged or inv.amount,
        method=method,
        success_url=success_url,
        cancel_url=cancel_url,
        ipn_url=ipn_url,
    )
    inv.payment_id = payment["payment_id"]
    inv.payment_reference = str(payment["payment_id"])
    await write_audit(
        session,
        action="investment.reserved",
        entity_type="investment",
        entity_id=str(inv.id),
        actor_id=inv.user_id,
        after={
            "via": method,
            "units": inv.units,
            "expires_at": inv.reservation_expires_at.isoformat(),
            "payment_id": str(payment["payment_id"]),
        },
    )
    return _result(inv, payment["checkout_url"])


def _allocate_units(
    session: AsyncSession, prop: Property, inv: Investment, *, confirmed_via: str
) -> None:
    """Finalize a confirmed purchase: drop available units, book the money, append
    the ownership ledger, flip to funded on the last unit. Caller holds the property
    lock. For direct-pay the units were already reserved, so only book the money."""
    if confirmed_via == "wallet":
        prop.available_units -= inv.units  # reserve + confirm in one step
    prop.funded_amount = prop.funded_amount + inv.amount
    prop.investors_count = prop.investors_count + 1
    _recompute_progress(prop)
    if prop.available_units <= 0:
        prop.status = PropertyStatus.funded
    inv.status = InvestmentStatus.confirmed
    inv.confirmed_at = _utcnow()
    inv.confirmed_via = confirmed_via
    inv.reservation_expires_at = None
    inv.failure_reason = None
    # Append-only ownership record (source of truth for unit ownership).
    session.add(
        OwnershipLedger(
            user_id=inv.user_id,
            property_id=prop.id,
            investment_id=inv.id,
            units=inv.units,
            unit_price=inv.unit_price_snapshot or prop.unit_price,
            reason="purchase",
            # Decision 2: stamp the rate the investor consented to at purchase.
            fee_rate=inv.management_fee_rate,
        )
    )


# --- Webhook-driven confirmation / release --------------------------------- #
async def confirm_investment(session: AsyncSession, *, payment) -> dict:
    """Finalize a direct-pay reservation. Called from payment_service.process_webhook
    inside the locked payment row, when a 'investment' payment reaches 'succeeded'."""
    inv_id = payment.related_investment_id
    if inv_id is None:
        return {"status": "ignored_no_investment"}
    inv = (
        await session.execute(select(Investment).where(Investment.id == inv_id).with_for_update())
    ).scalar_one_or_none()
    if inv is None:
        return {"status": "ignored_unknown_investment"}
    if inv.status == InvestmentStatus.confirmed:
        return {"status": "already_confirmed"}

    prop = (
        await session.execute(
            select(Property).where(Property.id == inv.property_id).with_for_update()
        )
    ).scalar_one()

    if inv.status == InvestmentStatus.pending:
        # Units already reserved at creation — just book the money + ledger.
        _allocate_units(session, prop, inv, confirmed_via=payment.payment_method or "card")
        await _notify_confirmed(session, inv, prop)
        await write_audit(
            session,
            action="investment.confirmed",
            entity_type="investment",
            entity_id=str(inv.id),
            after={"via": "webhook", "units": inv.units, "property_id": str(prop.id)},
        )
        await _accrue_broker_commission(session, inv)
        return {"status": "processed", "result": "confirmed"}

    # Late webhook after the reservation was already released (expired/cancelled).
    return await _reconcile_late_payment(session, inv=inv, prop=prop, payment=payment)


async def _reconcile_late_payment(
    session: AsyncSession, *, inv: Investment, prop: Property, payment
) -> dict:
    captured = payment.amount_captured or payment.amount
    if prop.status == PropertyStatus.active and prop.available_units >= inv.units:
        # Units still free — re-acquire and confirm.
        prop.available_units -= inv.units
        _allocate_units(session, prop, inv, confirmed_via=payment.payment_method or "card")
        await _notify_confirmed(session, inv, prop)
        await write_audit(
            session,
            action="investment.reconciled_confirmed",
            entity_type="investment",
            entity_id=str(inv.id),
            after={"units": inv.units, "property_id": str(prop.id)},
        )
        await _accrue_broker_commission(session, inv)
        return {"status": "processed", "result": "reconciled_confirmed"}

    # Units gone — refund the captured amount to the buyer's wallet.
    await wallet_service.credit(
        session,
        user_id=inv.user_id,
        amount=captured,
        reference_id=payment.id,
        tx_type=TransactionType.deposit,
        description="Refund — investment could not be fulfilled",
    )
    inv.failure_reason = "units_unavailable_refunded"
    await notification_service.notify(
        session,
        user_id=inv.user_id,
        type="investment",
        title="Investment refunded",
        message=(
            "Those units sold out before your payment confirmed. "
            f"We refunded {captured} {payment.currency} to your wallet."
        ),
        email_category="investment_updates",
    )
    await write_audit(
        session,
        action="investment.reconciled_refunded",
        entity_type="investment",
        entity_id=str(inv.id),
        after={"refunded": str(captured), "payment_id": str(payment.id)},
    )
    return {"status": "processed", "result": "refunded"}


async def release_reservation_for_payment(
    session: AsyncSession, *, payment, reason: str = "payment_failed"
) -> dict:
    """A direct-pay payment failed/cancelled — release the held units (idempotent)."""
    inv_id = payment.related_investment_id
    if inv_id is None:
        return {"status": "ignored_no_investment"}
    inv = (
        await session.execute(select(Investment).where(Investment.id == inv_id).with_for_update())
    ).scalar_one_or_none()
    if inv is None or inv.status != InvestmentStatus.pending:
        return {"status": "noop"}
    prop = (
        await session.execute(
            select(Property).where(Property.id == inv.property_id).with_for_update()
        )
    ).scalar_one()
    prop.available_units += inv.units
    if prop.status == PropertyStatus.funded and prop.available_units > 0:
        prop.status = PropertyStatus.active
    inv.status = InvestmentStatus.cancelled
    inv.failure_reason = reason
    inv.reservation_expires_at = None
    await write_audit(
        session,
        action="investment.released",
        entity_type="investment",
        entity_id=str(inv.id),
        after={"reason": reason, "restored_units": inv.units},
    )
    return {"status": "released"}


async def expire_reservations(session: AsyncSession, *, now: dt.datetime | None = None) -> int:
    """Release units held by reservations whose 30-minute window lapsed unpaid.

    Safe to run repeatedly (a cron in prod, lazily in tests). Uses SKIP LOCKED so a
    concurrent webhook confirming the same row is never blocked or double-processed.
    """
    cutoff = now or _utcnow()
    rows = (
        (
            await session.execute(
                select(Investment)
                .where(
                    Investment.status == InvestmentStatus.pending,
                    Investment.reservation_expires_at < cutoff,
                )
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    count = 0
    for inv in rows:
        prop = (
            await session.execute(
                select(Property).where(Property.id == inv.property_id).with_for_update()
            )
        ).scalar_one()
        prop.available_units += inv.units
        if prop.status == PropertyStatus.funded and prop.available_units > 0:
            prop.status = PropertyStatus.active
        inv.status = InvestmentStatus.expired
        inv.failure_reason = "reservation_expired"
        inv.reservation_expires_at = None
        await write_audit(
            session,
            action="investment.reservation_expired",
            entity_type="investment",
            entity_id=str(inv.id),
            after={"restored_units": inv.units, "property_id": str(prop.id)},
        )
        count += 1
    return count


# --- Reads ----------------------------------------------------------------- #
async def list_my_investments(session: AsyncSession, user_id: uuid.UUID) -> list[Investment]:
    res = await session.execute(
        select(Investment)
        .where(Investment.user_id == user_id)
        .order_by(Investment.created_at.desc())
    )
    return list(res.scalars().all())


async def get_my_investment(
    session: AsyncSession, *, user_id: uuid.UUID, investment_id: uuid.UUID
) -> Investment:
    inv = await session.get(Investment, investment_id)
    if inv is None or inv.user_id != user_id:
        raise AppError("NOT_FOUND", "Investment not found", status_code=404)
    return inv


async def _reinvest_already_done(session: AsyncSession, key: str) -> bool:
    """Idempotency for the wallet-funded reinvest (no investments row is created): a replay
    is detected via the append-only audit row stamped with the Idempotency-Key."""
    row = await session.scalar(
        select(AuditLog.id).where(
            AuditLog.action == "investment.reinvest", AuditLog.after["key"].astext == key
        )
    )
    return row is not None


async def reinvest_from_wallet(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    property_id: uuid.UUID,
    amount: float,
    idempotency_key: str,
) -> dict:
    """Reinvest returns from the wallet at the admin-configured ``reinvest_discount_pct``
    (the 2nd narrow D5 exception — a REAL, server-applied subsidy, mirroring the family
    reinvest). ``units = floor(amount / effective_price)`` where ``effective_price =
    unit_price × (1 − discount/100)``; the buyer is charged ``units × effective_price``
    (whole units only, mirroring the direct-buy quote) — any remainder stays in the wallet.
    Server-authoritative — the client never computes the price.
    Atomic (lock order property → wallet); idempotent on the Idempotency-Key."""
    amount_dec = decimal.Decimal(str(amount)).quantize(_CENTS)
    if amount_dec <= 0:
        raise AppError("INVALID_AMOUNT", "Amount must be positive.", status_code=422)
    if await _reinvest_already_done(session, idempotency_key):
        return {"property_id": str(property_id), "amount": str(amount_dec), "replayed": True}

    prop = (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    if prop.status != PropertyStatus.active:
        raise AppError(
            "PROPERTY_NOT_OPEN", "This property is not open for investment.", status_code=409
        )
    if prop.unit_price <= 0:
        raise AppError("INVALID_PROPERTY", "Property has no unit price.", status_code=409)

    discount = await settings_service.get_reinvest_discount_pct(session)
    effective_price = _q(prop.unit_price * (_HUNDRED - discount) / _HUNDRED)
    if effective_price <= 0:
        raise AppError("INVALID_DISCOUNT", "Effective price must be positive.", status_code=409)
    units = int(amount_dec // effective_price)  # floor(amount / effective_price)
    if units < 1:
        raise AppError(
            "AMOUNT_TOO_LOW",
            f"Minimum is one unit at the discounted price ({effective_price}).",
            status_code=422,
        )
    if units > prop.available_units:
        raise AppError(
            "INSUFFICIENT_UNITS",
            "Not enough units available in this property.",
            status_code=409,
            details={"available_units": prop.available_units, "requested": units},
        )

    # Charge only for the WHOLE units acquired, at the discounted price (mirrors the direct-buy
    # _quote, which debits units × unit_price). Debiting the raw amount over-charged the
    # remainder and defeated the discount; the unspent remainder now stays in the wallet.
    cost = _q(effective_price * units)
    # Lock order property -> wallet: property already locked; debit() locks the wallet.
    mgmt_rate = await settings_service.get_management_fee_pct(session)
    wallet = await wallet_service.debit(
        session,
        user_id=user_id,
        reference_id=property_id,
        line_items=[(TransactionType.investment, cost, f"Reinvest — {prop.title}")],
        actor_id=user_id,
    )
    wallet.total_invested = wallet.total_invested + cost
    prop.available_units = prop.available_units - units
    prop.funded_amount = prop.funded_amount + cost
    prop.investors_count = prop.investors_count + 1
    _recompute_progress(prop)
    if prop.available_units <= 0:
        prop.status = PropertyStatus.funded
    session.add(
        OwnershipLedger(
            user_id=user_id,
            property_id=property_id,
            investment_id=None,
            units=units,
            unit_price=prop.unit_price,  # nominal value of the units acquired
            reason="reinvest",
            fee_rate=mgmt_rate,
        )
    )
    await write_audit(
        session,
        action="investment.reinvest",
        entity_type="property",
        entity_id=str(property_id),
        actor_id=user_id,
        after={
            "amount": str(cost),
            "requested": str(amount_dec),
            "discount_pct": str(discount),
            "effective_price": str(effective_price),
            "units": units,
            "key": idempotency_key,
        },
    )
    await notification_service.notify(
        session,
        user_id=user_id,
        type="investment",
        title="Reinvestment confirmed",
        message=f"You reinvested {cost} and now own {units} more unit(s) of {prop.title}.",
        email_category="investment_updates",
    )
    return {
        "property_id": str(property_id),
        "amount": str(cost),
        "discount_pct": str(discount),
        "effective_price": str(effective_price),
        "units": units,
    }


async def portfolio_summary(session: AsyncSession, user_id: uuid.UUID) -> dict:
    """Server-authoritative portfolio for the caller. Holdings + current value come from
    the append-only ``ownership_ledger`` (net units per property × the property's current
    unit_price); invested + returns come from the wallet totals. No client-side math."""
    from app.models import Wallet

    rows = (
        await session.execute(
            select(
                OwnershipLedger.property_id,
                func.coalesce(func.sum(OwnershipLedger.units), 0),
                Property.unit_price,
            )
            .join(Property, Property.id == OwnershipLedger.property_id)
            .where(OwnershipLedger.user_id == user_id)
            .group_by(OwnershipLedger.property_id, Property.unit_price)
        )
    ).all()
    current_value = decimal.Decimal("0")
    total_units = 0
    properties = 0
    for _pid, units, unit_price in rows:
        u = int(units)
        if u <= 0:
            continue
        properties += 1
        total_units += u
        current_value += decimal.Decimal(u) * decimal.Decimal(unit_price)
    wallet = (
        await session.execute(select(Wallet).where(Wallet.user_id == user_id))
    ).scalar_one_or_none()
    invested = wallet.total_invested if wallet else decimal.Decimal("0")
    returns = wallet.total_returns if wallet else decimal.Decimal("0")
    return {
        "invested": str(_q(decimal.Decimal(invested))),
        "current_value": str(_q(current_value)),
        "total_returns": str(_q(decimal.Decimal(returns))),
        "properties": properties,
        "units": total_units,
    }


# --- helpers --------------------------------------------------------------- #
async def _checkout_url_for(session: AsyncSession, inv: Investment) -> str | None:
    if inv.payment_id is None:
        return None
    from app.models import Payment

    payment = await session.get(Payment, inv.payment_id)
    if payment is None or not isinstance(payment.raw_payload, dict):
        return None
    return payment.raw_payload.get("checkout_url")


async def _notify_confirmed(session: AsyncSession, inv: Investment, prop: Property) -> None:
    await notification_service.notify(
        session,
        user_id=inv.user_id,
        type="investment",
        title="Investment confirmed",
        message=f"You now own {inv.units} unit(s) of {prop.title}.",
        email_category="investment_updates",
    )


def _result(inv: Investment, checkout_url: str | None) -> dict:
    return {
        "investment_id": inv.id,
        "property_id": inv.property_id,
        "status": str(inv.status),
        "units": inv.units,
        "amount": str(inv.amount),
        "platform_fee": str(inv.platform_fee_amount or "0"),
        "total_charged": str(inv.total_charged or inv.amount),
        "management_fee_rate": str(inv.management_fee_rate or "0"),
        "checkout_url": checkout_url,
    }
