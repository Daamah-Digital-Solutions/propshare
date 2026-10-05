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
from app.models import AuditLog, Investment, Property, Wallet
from app.models.base import InvestmentStatus, PaymentMethod, PropertyStatus, TransactionType
from app.models.investments import OwnershipLedger
from app.services import (
    broker_service,
    listing_service,
    notification_service,
    payment_service,
    settings_service,
    wallet_service,
)

_CENTS = decimal.Decimal("0.01")


def _usd(value: decimal.Decimal) -> str:
    d = decimal.Decimal(value).quantize(_CENTS)
    return f"${d:,.0f}" if d == d.to_integral_value() else f"${d:,.2f}"


SAMPLE_MESSAGE = (
    "This is a sample listing shown for demonstration only. It is not open for investment."
)


def is_sample(prop: Property) -> bool:
    """Demo listings (content.sample = true) are visible like any listing but can never take
    money: every way to acquire units refuses them."""
    return bool((prop.content or {}).get("sample"))


def refuse_sample(prop: Property) -> None:
    if is_sample(prop):
        raise AppError("SAMPLE_LISTING", SAMPLE_MESSAGE, status_code=409)


def below_minimum(prop: Property, units: int) -> bool:
    """Whole units only: an amount is rounded DOWN to whole units, and those units must be
    worth at least the listing's minimum investment (and at least one unit)."""
    return units < 1 or prop.unit_price * units < prop.minimum_investment


def minimum_error(prop: Property) -> AppError:
    """Same rule and message for direct purchases and installment plans."""
    unit = decimal.Decimal(prop.unit_price)
    minimum = max(decimal.Decimal(prop.minimum_investment or 0), unit)
    # the smallest whole number of units worth at least the minimum
    min_units = int((minimum / unit).to_integral_value(rounding=decimal.ROUND_CEILING))
    min_amount = unit * min_units
    return AppError(
        "AMOUNT_TOO_LOW",
        f"The minimum investment for this property is {_usd(min_amount)} "
        f"({min_units} whole unit{'' if min_units == 1 else 's'} at {_usd(unit)} each). "
        "Amounts are rounded down to whole units.",
        status_code=422,
        details={
            "minimum_investment": str(prop.minimum_investment),
            "unit_price": str(prop.unit_price),
            "minimum_amount": f"{min_amount.normalize():f}",
        },
    )


def is_offplan(prop: Property) -> bool:
    """Under construction: no rent yet, the investor earns by the unit price going up."""
    return listing_service.profile_of(prop.model) in listing_service.OFFPLAN_PROFILES


def payment_modes(prop: Property) -> tuple[str, ...]:
    """How units of this listing are bought: ``full`` (paid at once) and/or ``installments``
    (the plan). A ready listing is paid in full. An under-construction one says which (0034:
    ``properties.offplan_payment``): installments, full (a project sold in phases, each at
    its own price) or both."""
    if not is_offplan(prop):
        return ("full",)
    choice = prop.offplan_payment or "installments"
    return ("full", "installments") if choice == "both" else (choice,)


def require_full_payment(prop: Property) -> None:
    if "full" not in payment_modes(prop):
        raise AppError(
            "INSTALLMENTS_ONLY",
            "This property is bought through its installment plan, not paid in full.",
            status_code=409,
        )


def require_installments(prop: Property) -> None:
    if is_offplan(prop) and "installments" not in payment_modes(prop):
        raise AppError(
            "FULL_PAYMENT_ONLY",
            "This property is paid in full: it has no installment plan.",
            status_code=409,
        )


def require_price(prop: Property, expected: decimal.Decimal | float | str | None) -> None:
    """The buyer confirmed an order at the unit price on their screen. If the price has changed
    since (a page left open across a price change), refuse and say the new price, so the screen
    shows the new amounts for a fresh confirmation: nobody buys, or locks a plan, at a price
    they have not seen. Without ``expected`` (an older client) nothing is checked."""
    if expected is None:
        return
    try:
        seen = _q(decimal.Decimal(str(expected)))
    except (decimal.InvalidOperation, ValueError):
        seen = None
    now = _q(decimal.Decimal(prop.unit_price))
    if seen != now:
        raise AppError(
            "PRICE_CHANGED",
            f"The unit price of this property is now ${now}. Review the new amounts and "
            "confirm again.",
            status_code=409,
            details={"unit_price": str(now)},
        )


def price_moved(prop: Property, priced_at: decimal.Decimal | None) -> bool:
    """The unit price is no longer the one a held purchase or plan was priced at."""
    return priced_at is not None and decimal.Decimal(prop.unit_price) != decimal.Decimal(priced_at)


def hold_lapsed(expires_at: dt.datetime | None) -> bool:
    """A hold with a time limit whose time is up (a hold with no limit never lapses)."""
    return expires_at is not None and expires_at <= dt.datetime.now(dt.UTC)


def return_units(prop: Property, units: int, priced_at: decimal.Decimal | None) -> None:
    """Units held for a purchase or a plan that did not go through are on sale again, at
    TODAY's price. If the price moved since they were priced, the offering's total follows
    (see price_service.record_price), so funding progress still ends at exactly 100%."""
    prop.available_units += units
    if priced_at is not None and prop.unit_price != priced_at:
        prop.total_value = _q(prop.total_value + (prop.unit_price - priced_at) * units)
        _recompute_progress(prop)
    if prop.status == PropertyStatus.funded and prop.available_units > 0:
        prop.status = PropertyStatus.active


def retake_units(prop: Property, units: int, priced_at: decimal.Decimal | None) -> None:
    """The reverse: a payment that arrived late takes its units back out of the pool at the
    price it was made at."""
    prop.available_units -= units
    if priced_at is not None and prop.unit_price != priced_at:
        prop.total_value = _q(prop.total_value - (prop.unit_price - priced_at) * units)
        _recompute_progress(prop)


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


async def _lock_and_quote(
    session: AsyncSession,
    *,
    property_id: uuid.UUID,
    amount: float,
    expected_unit_price: float | None = None,
) -> tuple[Property, dict, dict]:
    """Lock the property (serializes concurrent buyers: oversell protection), check it is
    open and has the units, and price the purchase. Returns (property, fee rates, quote)."""
    prop = (
        await session.execute(select(Property).where(Property.id == property_id).with_for_update())
    ).scalar_one_or_none()
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    if prop.status != PropertyStatus.active:
        raise AppError(
            "PROPERTY_NOT_OPEN", "This property is not open for investment.", status_code=409
        )
    refuse_sample(prop)
    require_full_payment(prop)
    require_price(prop, expected_unit_price)

    # an amount is money: cents first, or 3 units at 110.10 sent as the float
    # 330.29999999999995 would buy 2
    amount_dec = _q(decimal.Decimal(str(amount)))
    rates = await settings_service.get_fee_rates(session)
    quote = _quote(prop.unit_price, amount_dec, rates)
    if below_minimum(prop, quote["units"]):
        raise minimum_error(prop)
    if quote["units"] > prop.available_units:
        raise AppError(
            "INSUFFICIENT_UNITS",
            "Not enough units remain for this investment.",
            status_code=409,
            details={"available_units": prop.available_units, "requested": quote["units"]},
        )
    return prop, rates, quote


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
    expected_unit_price: float | None = None,
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

    prop, rates, quote = await _lock_and_quote(
        session, property_id=property_id, amount=amount, expected_unit_price=expected_unit_price
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


async def _count_invested(session: AsyncSession, inv: Investment) -> None:
    """A purchase paid outside the wallet (a checkout, or a Nova Sukuk certificate) counts
    toward the buyer's invested cost basis exactly like a wallet purchase: the portfolio's
    current value already includes its units, so without this it shows a phantom gain.
    Locks the buyer's wallet — with the referring broker's, whose commission follows, in the
    global wallet lock order (as ``_fund_from_wallet`` does)."""
    broker_id = await broker_service.referring_broker(session, inv.user_id)
    await wallet_service.lock_wallets(
        session, [inv.user_id, broker_id] if broker_id is not None else [inv.user_id]
    )
    wallet = (
        await session.execute(
            select(Wallet)
            .where(Wallet.user_id == inv.user_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if wallet is not None:
        wallet.total_invested = wallet.total_invested + inv.amount


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

    if (
        inv.status == InvestmentStatus.pending
        and hold_lapsed(inv.reservation_expires_at)
        and price_moved(prop, inv.unit_price_snapshot)
    ):
        # Paid after the hold ran out (the sweep has not released it yet) and the unit price
        # has changed since: the hold is over, exactly as if the sweep had already run.
        return_units(prop, inv.units, inv.unit_price_snapshot)
        inv.status = InvestmentStatus.expired
        inv.reservation_expires_at = None

    if inv.status == InvestmentStatus.pending:
        # Units already reserved at creation — just book the money + ledger.
        _allocate_units(session, prop, inv, confirmed_via=payment.payment_method or "card")
        await _count_invested(session, inv)
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
    free = prop.status == PropertyStatus.active and prop.available_units >= inv.units
    # A hold lasts 30 minutes, a hosted checkout can be paid for a day. Paying late is honoured
    # only at the price the purchase was made at: once the unit price has moved (0034), an old
    # checkout must not buy at yesterday's price. The money goes back to the wallet instead.
    repriced = free and price_moved(prop, inv.unit_price_snapshot)
    if free and not repriced:
        # Units still free — re-acquire and confirm.
        retake_units(prop, inv.units, inv.unit_price_snapshot)
        _allocate_units(session, prop, inv, confirmed_via=payment.payment_method or "card")
        await _count_invested(session, inv)
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

    # Units gone, or the price changed — refund the captured amount to the buyer's wallet.
    await wallet_service.credit(
        session,
        user_id=inv.user_id,
        amount=captured,
        reference_id=payment.id,
        tx_type=TransactionType.deposit,
        description="Refund — investment could not be fulfilled",
    )
    inv.failure_reason = "price_changed_refunded" if repriced else "units_unavailable_refunded"
    why = (
        f"The unit price of {prop.title} changed before your payment confirmed, so the "
        "purchase was not completed. You can buy at the new price from your wallet."
        if repriced
        else "Those units sold out before your payment confirmed."
    )
    await notification_service.notify(
        session,
        user_id=inv.user_id,
        type="investment",
        title="Investment refunded",
        message=f"{why} We refunded {captured} {payment.currency} to your wallet.",
        email_category="investment_updates",
    )
    await write_audit(
        session,
        action="investment.reconciled_refunded",
        entity_type="investment",
        entity_id=str(inv.id),
        after={
            "refunded": str(captured),
            "payment_id": str(payment.id),
            "reason": inv.failure_reason,
        },
    )
    return {"status": "processed", "result": "refunded"}


async def release_reservation_for_payment(
    session: AsyncSession, *, payment, reason: str = "payment_failed"
) -> dict:
    """A direct-pay payment failed/cancelled — release the held units (idempotent)."""
    inv_id = payment.related_investment_id
    if inv_id is None:
        return {"status": "ignored_no_investment"}
    return await _release_pending(session, investment_id=inv_id, reason=reason)


async def _release_pending(session: AsyncSession, *, investment_id: uuid.UUID, reason: str) -> dict:
    """A pending purchase ends unpaid (its checkout failed, or its Nova certificate was
    rejected): its units go back on sale (idempotent)."""
    inv = (
        await session.execute(
            select(Investment).where(Investment.id == investment_id).with_for_update()
        )
    ).scalar_one_or_none()
    if inv is None or inv.status != InvestmentStatus.pending:
        return {"status": "noop"}
    prop = (
        await session.execute(
            select(Property).where(Property.id == inv.property_id).with_for_update()
        )
    ).scalar_one()
    return_units(prop, inv.units, inv.unit_price_snapshot)
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


# --- Nova Sukuk: a purchase paid with a certificate staff review (0032) ----- #
async def reserve_for_sukuk(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    property_id: uuid.UUID,
    amount: float,
    idempotency_key: str,
) -> tuple[Investment, Property]:
    """A purchase paid with a Nova Sukuk certificate: priced like any purchase (subtotal +
    platform fee, no discount) and its units HELD while staff review the certificate — with no
    time limit, as a review takes time (``expire_reservations`` skips a NULL expiry)."""
    prop, rates, quote = await _lock_and_quote(session, property_id=property_id, amount=amount)
    inv = Investment(
        user_id=user_id,
        property_id=prop.id,
        units=quote["units"],
        amount=quote["subtotal"],
        payment_method=PaymentMethod.nova_sukuk,
        idempotency_key=idempotency_key,
        unit_price_snapshot=prop.unit_price,
        platform_fee_amount=quote["platform_fee"],
        platform_fee_rate=rates["platform_fee_pct"],
        management_fee_rate=rates["management_fee_pct"],
        total_charged=quote["total_charge"],
        fee_settings_snapshot={
            "platform_fee_pct": str(rates["platform_fee_pct"]),
            "management_fee_pct": str(rates["management_fee_pct"]),
        },
        status=InvestmentStatus.pending,
    )
    session.add(inv)
    await session.flush()
    prop.available_units -= inv.units
    await write_audit(
        session,
        action="investment.reserved",
        entity_type="investment",
        entity_id=str(inv.id),
        actor_id=user_id,
        after={"via": "sukuk", "units": inv.units, "total": str(inv.total_charged)},
    )
    return inv, prop


async def confirm_sukuk_purchase(
    session: AsyncSession, *, investment_id: uuid.UUID, certificate_id: uuid.UUID
) -> Investment:
    """Staff approved the Nova Sukuk certificate: the held units become the buyer's, exactly
    as when a checkout is paid."""
    inv = (
        await session.execute(
            select(Investment).where(Investment.id == investment_id).with_for_update()
        )
    ).scalar_one_or_none()
    if inv is None or inv.status != InvestmentStatus.pending:
        raise AppError(
            "INVALID_TRANSITION",
            "This purchase is no longer waiting for its Nova certificate.",
            status_code=409,
        )
    prop = (
        await session.execute(
            select(Property).where(Property.id == inv.property_id).with_for_update()
        )
    ).scalar_one()
    _allocate_units(session, prop, inv, confirmed_via="sukuk")
    await _count_invested(session, inv)
    inv.payment_reference = f"sukuk:{certificate_id}"
    await write_audit(
        session,
        action="investment.confirmed",
        entity_type="investment",
        entity_id=str(inv.id),
        after={"via": "sukuk", "units": inv.units, "property_id": str(prop.id)},
    )
    await _accrue_broker_commission(session, inv)
    return inv


async def release_sukuk_purchase(
    session: AsyncSession, *, investment_id: uuid.UUID, reason: str
) -> dict:
    """Staff rejected the Nova Sukuk certificate: the held units go back on sale."""
    return await _release_pending(session, investment_id=investment_id, reason=reason)


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
        return_units(prop, inv.units, inv.unit_price_snapshot)
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
    refuse_sample(prop)
    require_full_payment(prop)
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
    unit_price); invested + returns come from the wallet totals. No client-side math.

    A running installment plan (0034) is valued as the POSITION it is: all its units at the
    current price, less the principal still to pay (what a buyer would pay for it), instead
    of its vested units alone. ``sold`` is what selling units and positions has brought in,
    so that ``current_value + sold - invested`` is the gain on everything bought so far,
    whether it is still held or was sold."""
    from app.models import (
        InstallmentPayment,
        InstallmentPlan,
        LpExitRequest,
        Transaction,
        Wallet,
    )

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
    # running plans: swap "vested units x price" for the position's equity
    unpaid = (
        select(
            InstallmentPayment.plan_id,
            func.coalesce(func.sum(InstallmentPayment.base_amount), 0).label("remaining"),
        )
        .where(InstallmentPayment.status != "paid")
        .group_by(InstallmentPayment.plan_id)
        .subquery()
    )
    plans = (
        await session.execute(
            select(
                InstallmentPlan.units_total,
                InstallmentPlan.vested_units,
                Property.unit_price,
                func.coalesce(unpaid.c.remaining, 0),
            )
            .join(Property, Property.id == InstallmentPlan.property_id)
            .outerjoin(unpaid, unpaid.c.plan_id == InstallmentPlan.id)
            .where(InstallmentPlan.investor_id == user_id, InstallmentPlan.status == "active")
        )
    ).all()
    for units_total, vested, unit_price, remaining in plans:
        price = decimal.Decimal(unit_price)
        equity = price * int(units_total) - decimal.Decimal(remaining)
        # Never below zero: nobody is made to pay the rest of a plan, so a position worth
        # less than what is still to pay on it is worth nothing, not a debt.
        current_value += max(equity, decimal.Decimal(0)) - price * int(vested)
    sold = await session.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id,
            Transaction.type == TransactionType.secondary_sale,
            Transaction.amount > 0,
        )
    )
    # An exit to a liquidity provider credits the provider's price and then takes the
    # liquidity fee as its own line: what the sale brought is the price less that fee.
    exit_fees = await session.scalar(
        select(func.coalesce(func.sum(-Transaction.amount), 0)).where(
            Transaction.user_id == user_id,
            Transaction.type == TransactionType.fee,
            Transaction.amount < 0,
            Transaction.reference_id.in_(
                select(LpExitRequest.id).where(LpExitRequest.seller_id == user_id)
            ),
        )
    )
    sold = decimal.Decimal(sold or 0) - decimal.Decimal(exit_fees or 0)
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
        "sold": str(_q(decimal.Decimal(sold or 0))),
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
        "payment_id": inv.payment_id,
    }
