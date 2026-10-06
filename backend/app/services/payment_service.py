"""Payment service (Phase 4) — deposit intents + the webhook-driven credit.

Two-layer idempotency so a replayed webhook can NEVER double-credit:
  1. ``payment_events`` UNIQUE(provider, event_id) — a duplicate delivery is
     skipped before any work.
  2. the credit only fires when ``payments.status`` transitions
     ``pending → succeeded`` *inside a FOR UPDATE row lock* — a second delivery
     that slips past layer 1 sees ``succeeded`` and does nothing.

The wallet is credited with the amount the PROVIDER reports as captured, never an
amount the client supplied.
"""

from __future__ import annotations

import datetime
import decimal
import logging
import time
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import InstallmentPlan, Investment, Payment, PaymentEvent, Property
from app.models.base import PaymentMethod
from app.services import notification_service, payment_method_service, wallet_service
from app.services.integrations.payments import ParsedWebhook, nowpayments_gateway, stripe_gateway

# "pronova" is a BRANDED rail that settles via Stripe card (D5 owner decision) — the buyer
# sees the Pronova experience + discount, the money moves on Stripe. Kept as a distinct method
# from plain "card" so it's recorded/branded separately.
_PROVIDER_FOR_METHOD = {"card": "stripe", "crypto": "nowpayments", "pronova": "stripe"}

# Human label shown on the hosted-checkout line item (branding). Deposits keep the wallet
# label; investments name the property purchase, and Pronova carries its brand.
_CHECKOUT_LABEL = {
    "card": "Capimax investment",
    "pronova": "Capimax investment · Pronova",
}
# ...and an installment plan's down payment (0032).
_PLAN_CHECKOUT_LABEL = {
    "card": "Capimax installment plan · down payment",
    "pronova": "Capimax installment plan · down payment · Pronova",
}


logger = logging.getLogger(__name__)


def _locked(payment_id: uuid.UUID):
    """SELECT … FOR UPDATE that refreshes the row even when the session already holds it.

    Without ``populate_existing`` SQLAlchemy returns the object already in the session with
    the values it read BEFORE the lock, so a payment another transaction just settled would
    still look pending here — and the webhook and the provider lookup (different event keys)
    could both credit it. The status guard below must see the locked row."""
    return (
        select(Payment)
        .where(Payment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _gateway(provider: str):
    return stripe_gateway if provider == "stripe" else nowpayments_gateway


def _with_payment(url: str, payment_id: uuid.UUID) -> str:
    """The return URL with our payment id, so the page the provider sends the payer back to
    can follow that payment (poll its status, refresh the balance) instead of guessing."""
    return f"{url}{'&' if '?' in url else '?'}payment={payment_id}"


def provider_for(method: str) -> str:
    return _PROVIDER_FOR_METHOD[method]


def provider_configured(method: str) -> bool:
    """Whether the rail behind ``method`` (card->stripe, crypto->nowpayments) is set up."""
    return _gateway(_PROVIDER_FOR_METHOD[method]).is_configured()


def purchase_options() -> dict[str, bool]:
    """Which ways to pay for a property are live right now. Every property offers the SAME
    list (client feedback 2026-09-27); a rail whose provider is not set up is shown as not
    available, never hidden. Card, Apple Pay, Google Pay and Pronova settle on Stripe (Apple /
    Google Pay appear on Stripe's checkout on devices that support them); crypto on
    NOWPayments; the wallet and a Nova Sukuk certificate need no provider."""
    card = provider_configured("card")
    return {
        "wallet": True,
        "card": card,
        "apple_pay": card,
        "google_pay": card,
        "crypto": provider_configured("crypto"),
        "pronova": provider_configured("pronova"),
        "sukuk": True,
    }


async def create_deposit(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: float,
    method: str,
    idempotency_key: str | None,
    success_url: str,
    cancel_url: str,
    ipn_url: str,
    pay_currency: str | None = None,
) -> dict:
    """``pay_currency``: the coin a crypto deposit is paid in (nowpayments_gateway.list_coins)."""
    provider = _PROVIDER_FOR_METHOD[method]
    gateway = _gateway(provider)
    if not gateway.is_configured():
        raise AppError(
            "PAYMENTS_NOT_CONFIGURED",
            f"{provider} is not configured yet.",
            status_code=503,
        )

    # Idempotency-Key replay -> return the existing intent, don't create a second.
    if idempotency_key:
        existing = (
            await session.execute(select(Payment).where(Payment.idempotency_key == idempotency_key))
        ).scalar_one_or_none()
        if existing is not None:
            url = (
                (existing.raw_payload or {}).get("checkout_url")
                if isinstance(existing.raw_payload, dict)
                else None
            )
            return {
                "payment_id": existing.id,
                "provider": existing.provider,
                "status": existing.status,
                "checkout_url": url,
            }

    amount_dec = decimal.Decimal(str(amount)).quantize(decimal.Decimal("0.01"))
    currency = get_settings().wallet_currency
    payment = Payment(
        user_id=user_id,
        provider=provider,
        amount=amount_dec,
        currency=currency,
        status="pending",
        purpose="deposit",
        payment_method=method,
        idempotency_key=idempotency_key,
    )
    session.add(payment)
    await session.flush()  # assign payment.id
    success_url = _with_payment(success_url, payment.id)
    cancel_url = _with_payment(cancel_url, payment.id)

    if provider == "stripe":
        result = await stripe_gateway.create_checkout(
            payment_id=payment.id,
            amount=amount_dec,
            currency=currency,
            success_url=success_url,
            cancel_url=cancel_url,
            idempotency_key=idempotency_key,
            customer_id=await payment_method_service.checkout_customer(session, user_id),
        )
    else:
        result = await nowpayments_gateway.create_checkout(
            payment_id=payment.id,
            amount=amount_dec,
            currency=currency,
            success_url=success_url,
            cancel_url=cancel_url,
            ipn_url=ipn_url,
            pay_currency=pay_currency,
        )

    payment.provider_payment_id = result.provider_payment_id
    payment.raw_payload = _checkout_payload(result.checkout_url, provider, pay_currency)
    await write_audit(
        session,
        action="payment.create",
        entity_type="payment",
        entity_id=str(payment.id),
        actor_id=user_id,
        after={"provider": provider, "amount": str(amount_dec), "purpose": "deposit"},
    )
    return {
        "payment_id": payment.id,
        "provider": provider,
        "status": "pending",
        "checkout_url": result.checkout_url,
    }


async def _purchase_checkout(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    purpose: str,
    amount: decimal.Decimal,
    method: str,
    success_url: str,
    cancel_url: str,
    ipn_url: str,
    product_name: str,
    investment_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
    pay_currency: str | None = None,
) -> dict:
    """A hosted-checkout intent that pays for units (a purchase, or an installment plan's
    down payment). Idempotency is anchored on the investment / plan row (its unique
    ``idempotency_key``), so the Payment itself carries no key. The amount is server-computed,
    never client-supplied."""
    provider = _PROVIDER_FOR_METHOD[method]
    gateway = _gateway(provider)
    if not gateway.is_configured():
        raise AppError(
            "PAYMENTS_NOT_CONFIGURED", f"{provider} is not configured yet.", status_code=503
        )
    currency = get_settings().wallet_currency
    amount_dec = amount.quantize(decimal.Decimal("0.01"))
    payment = Payment(
        user_id=user_id,
        provider=provider,
        amount=amount_dec,
        currency=currency,
        status="pending",
        purpose=purpose,
        payment_method=method,
        related_investment_id=investment_id,
        related_plan_id=plan_id,
    )
    session.add(payment)
    await session.flush()
    success_url = _with_payment(success_url, payment.id)
    cancel_url = _with_payment(cancel_url, payment.id)

    if provider == "stripe":
        result = await stripe_gateway.create_checkout(
            payment_id=payment.id,
            amount=amount_dec,
            currency=currency,
            success_url=success_url,
            cancel_url=cancel_url,
            idempotency_key=None,
            product_name=product_name,
            customer_id=await payment_method_service.checkout_customer(session, user_id),
        )
    else:
        result = await nowpayments_gateway.create_checkout(
            payment_id=payment.id,
            amount=amount_dec,
            currency=currency,
            success_url=success_url,
            cancel_url=cancel_url,
            ipn_url=ipn_url,
            pay_currency=pay_currency,
        )

    payment.provider_payment_id = result.provider_payment_id
    payment.raw_payload = _checkout_payload(result.checkout_url, provider, pay_currency)
    await write_audit(
        session,
        action="payment.create",
        entity_type="payment",
        entity_id=str(payment.id),
        actor_id=user_id,
        after={"provider": provider, "amount": str(amount_dec), "purpose": purpose},
    )
    return {
        "payment_id": payment.id,
        "provider": provider,
        "status": "pending",
        "checkout_url": result.checkout_url,
    }


async def create_investment_checkout(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    investment_id: uuid.UUID,
    amount: decimal.Decimal,
    method: str,
    success_url: str,
    cancel_url: str,
    ipn_url: str,
    pay_currency: str | None = None,
) -> dict:
    """Create a hosted-checkout intent for a DIRECT-PAY investment (purpose=investment); the
    amount is the server-computed total charge (subtotal + platform fee − any discount)."""
    return await _purchase_checkout(
        session,
        user_id=user_id,
        purpose="investment",
        amount=amount,
        method=method,
        success_url=success_url,
        cancel_url=cancel_url,
        ipn_url=ipn_url,
        product_name=_CHECKOUT_LABEL.get(method, "Capimax investment"),
        investment_id=investment_id,
        pay_currency=pay_currency,
    )


async def create_plan_checkout(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    plan_id: uuid.UUID,
    amount: decimal.Decimal,
    method: str,
    success_url: str,
    cancel_url: str,
    ipn_url: str,
    pay_currency: str | None = None,
) -> dict:
    """Create a hosted-checkout intent for an installment plan's DOWN PAYMENT
    (purpose=installment); its settlement starts the plan (installment_service)."""
    return await _purchase_checkout(
        session,
        user_id=user_id,
        purpose="installment",
        amount=amount,
        method=method,
        success_url=success_url,
        cancel_url=cancel_url,
        ipn_url=ipn_url,
        product_name=_PLAN_CHECKOUT_LABEL.get(method, _PLAN_CHECKOUT_LABEL["card"]),
        plan_id=plan_id,
        pay_currency=pay_currency,
    )


async def get_payment(
    session: AsyncSession, *, user_id: uuid.UUID, payment_id: uuid.UUID
) -> Payment:
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.user_id != user_id:
        raise AppError("NOT_FOUND", "Payment not found", status_code=404)
    return payment


async def process_webhook(
    session: AsyncSession, *, provider: str, raw_body: bytes, signature: str | None
) -> dict:
    """Verify + idempotently apply a provider webhook. The route passes the raw
    body; the gateway raises 401 on a bad signature before we touch the DB."""
    parsed: ParsedWebhook = _gateway(provider).verify_and_parse(raw_body, signature)

    # Layer 1: dedupe on (provider, event_id).
    seen = (
        await session.execute(
            select(PaymentEvent.id).where(
                PaymentEvent.provider == provider, PaymentEvent.event_id == parsed.event_id
            )
        )
    ).first() is not None
    # A notification seen before is dropped. NOWPayments' are looked at once more: staff send
    # one again from its dashboard ("IPN") to settle money that is still owed, and only that
    # is settled then (_np_replay_wanted; each NOWPayments payment is settled once).
    if seen and provider != "nowpayments":
        return {"status": "duplicate"}

    payment = await _locate(session, provider, parsed)
    if not seen:
        session.add(
            PaymentEvent(
                provider=provider,
                event_id=parsed.event_id,
                payment_id=payment.id if payment else None,
                type=parsed.type,
            )
        )
    if payment is None:
        if seen:
            return {"status": "duplicate"}
        await write_audit(
            session,
            action="payment.webhook.unmatched",
            entity_type="payment",
            entity_id=parsed.provider_payment_id,
            after={"type": parsed.type},
        )
        return {"status": "ignored_unknown_payment"}

    return await _apply(
        session, provider=provider, parsed=parsed, payment=payment, source="webhook", replay=seen
    )


async def _apply(
    session: AsyncSession,
    *,
    provider: str,
    parsed: ParsedWebhook,
    payment: Payment,
    source: str,
    replay: bool = False,
) -> dict:
    """Apply a provider outcome to a located payment. Shared by the webhook and the direct
    provider lookup (``sync_payment``), so both settle through exactly the same guarded path.
    ``replay``: the provider sent this very notification before."""
    if provider == "nowpayments":
        return await _apply_nowpayments(
            session, parsed=parsed, payment=payment, source=source, replay=replay
        )
    return await _apply_outcome(
        session, provider=provider, parsed=parsed, payment=payment, source=source
    )


async def _apply_outcome(
    session: AsyncSession, *, provider: str, parsed: ParsedWebhook, payment: Payment, source: str
) -> dict:
    """A payment paid or failed, as one payment has one outcome: the row lock + status guard
    below is what makes a webhook and a lookup that both report the same payment paid credit
    it once."""
    if parsed.status == "succeeded":
        # Layer 2: lock the row + guard the state transition (exactly-once credit).
        locked = (await session.execute(_locked(payment.id))).scalar_one()
        if locked.status == "succeeded":
            return {"status": "already_processed"}
        locked.status = "succeeded"
        locked.amount_captured = decimal.Decimal(
            str(parsed.captured_amount or locked.amount)
        ).quantize(decimal.Decimal("0.01"))
        await write_audit(
            session,
            action="payment.webhook.succeeded" if source == "webhook" else "payment.sync.succeeded",
            entity_type="payment",
            entity_id=str(locked.id),
            after={"captured": str(locked.amount_captured), "purpose": locked.purpose},
        )
        if locked.purpose == "investment":
            # Direct-pay investment: confirm the reservation (units already held), or
            # reconcile if its reservation already expired. No wallet credit.
            from app.services import investment_service

            return await investment_service.confirm_investment(session, payment=locked)
        if locked.purpose == "installment":
            # An installment plan's down payment: start the plan. No wallet credit.
            from app.services import installment_service

            return await installment_service.confirm_down_payment(session, payment=locked)

        # Deposit: credit the wallet with the provider-captured amount.
        pm = PaymentMethod.crypto if locked.payment_method == "crypto" else None
        await wallet_service.credit(
            session,
            user_id=locked.user_id,
            amount=locked.amount_captured,
            reference_id=locked.id,
            payment_method=pm,
            description=f"Deposit via {provider}",
        )
        await notification_service.notify(
            session,
            user_id=locked.user_id,
            type="wallet",
            title="Deposit received",
            message=f"Your deposit of {locked.amount_captured} {locked.currency} was credited.",
            email_category="investment_updates",
        )
        return {"status": "processed", "result": "credited"}

    if parsed.status == "failed":
        locked = (await session.execute(_locked(payment.id))).scalar_one()
        if locked.status != "pending":
            # Already settled (or already failed): a late failure event changes nothing.
            return {"status": "already_processed"}
        locked.status = "failed"
        await write_audit(
            session,
            action="payment.webhook.failed" if source == "webhook" else "payment.sync.failed",
            entity_type="payment",
            entity_id=str(locked.id),
            after={"type": parsed.type, "purpose": locked.purpose},
        )
        if locked.purpose == "investment":
            # Release the units held for this abandoned/failed direct-pay reservation.
            from app.services import investment_service

            await investment_service.release_reservation_for_payment(
                session, payment=locked, reason=f"payment_{parsed.status}"
            )
        elif locked.purpose == "installment":
            # The plan never started: its units go back on sale.
            from app.services import installment_service

            await installment_service.release_plan_for_payment(
                session, payment=locked, reason=f"payment_{parsed.status}"
            )
        return {"status": "processed", "result": "failed"}

    return {"status": "ignored", "result": parsed.status}


# --- NOWPayments: each payment under an invoice is settled once ------------------------------ #
# One invoice (our ``payments`` row) can hold several NOWPayments payments: the one for the
# coin chosen, another if the member picks a second coin on their page, and the deposits
# NOWPayments adds by itself — a second transfer to the same address ("Re-deposit") or one it
# recovered from another coin or network ("Wrong Asset"). All carry our order. Each is real
# money, so each is settled exactly once, and what was done is kept on the row
# (``raw_payload["nowpayments"][<their payment id>]``):
#   * the invoice paid as asked ("finished"): the deposit is credited at the invoice's price,
#     or the purchase is confirmed (``_apply_outcome``);
#   * anything else that arrived (an under-payment, an extra deposit): what it is worth goes
#     to the member's wallet. A purchase it was meant for is not completed with it: its units
#     go back on sale and the member buys from the wallet;
#   * money that cannot be valued: nothing is credited and staff get a case at once.
_NP = "nowpayments"
_NP_IN_FLIGHT = frozenset({"confirming", "confirmed", "sending"})
# how long an unpaid crypto payment stays on the member's wallet page
OPEN_CRYPTO_WINDOW = datetime.timedelta(hours=24)
# ... and one NOWPayments never reported anything about: no payment page was opened for it,
# so no address was ever shown and nothing can be on its way
OPEN_CRYPTO_UNSEEN_WINDOW = datetime.timedelta(hours=1)


def _checkout_payload(checkout_url: str, provider: str, pay_currency: str | None) -> dict:
    """What a payment keeps about its checkout: the page to finish it on and, for crypto, the
    coin the member chose."""
    payload = {"checkout_url": checkout_url}
    if provider == _NP and pay_currency:
        payload["pay_currency"] = pay_currency.lower()
    return payload


def _np_records(payment: Payment) -> dict[str, dict]:
    raw = payment.raw_payload if isinstance(payment.raw_payload, dict) else {}
    kept = raw.get(_NP)
    return {str(k): dict(v) for k, v in kept.items()} if isinstance(kept, dict) else {}


def _keep_np_records(payment: Payment, records: dict[str, dict]) -> None:
    """Write the records on the row. Copies all the way down: the row must not share a dict
    with the caller, or a later edit of ``records`` changes the value already on the row and
    the next write looks like no change (it is then never saved)."""
    raw = dict(payment.raw_payload) if isinstance(payment.raw_payload, dict) else {}
    raw[_NP] = {record_id: dict(entry) for record_id, entry in records.items()}
    payment.raw_payload = raw


def _plain(value: object) -> str | None:
    """A provider number as plain text (no exponent), None when it gave none."""
    if value in (None, ""):
        return None
    try:
        return format(decimal.Decimal(str(value)), "f")
    except (decimal.InvalidOperation, ValueError):
        return None


def _np_replay_wanted(parsed: ParsedWebhook, kept: dict | None, row_status: str) -> bool:
    """Whether a notification NOWPayments sends AGAIN still has money to settle. Only money
    that arrived and was never credited:
      * a payment waiting for a person because it could not be valued (it may be valued now);
      * an under-payment recorded before each payment's outcome was kept (until 2026-10 it was
        left for a person), while nothing was ever settled on its row.
    Anything else sent again changes nothing: it was settled, or there was nothing to settle."""
    if parsed.status != "received":
        return False
    if kept is None:
        return parsed.type == "partially_paid" and row_status == "pending"
    return bool(kept.get("review")) and kept.get("credited") is None


async def _apply_nowpayments(
    session: AsyncSession,
    *,
    parsed: ParsedWebhook,
    payment: Payment,
    source: str,
    replay: bool = False,
) -> dict:
    data = parsed.raw
    record_id = parsed.provider_payment_id or parsed.event_id
    kept = _np_records(payment).get(record_id)
    if replay and not _np_replay_wanted(parsed, kept, payment.status):
        return {"status": "duplicate"}
    value, valued_by = parsed.captured_amount, "notification"
    if parsed.status == "received" and value is None and (kept or {}).get("credited") is None:
        # Money arrived and its notification does not say what it is worth: NOWPayments is
        # asked, before the row is locked (the answer can take seconds).
        looked = await nowpayments_gateway.value_now(data)
        if looked is not None:
            value, valued_by = looked

    locked = (await session.execute(_locked(payment.id))).scalar_one()
    records = _np_records(locked)
    entry = records.setdefault(record_id, {})
    entry.update(
        status=parsed.type,
        coin=str(data.get("pay_currency") or entry.get("coin") or "") or None,
        asked=_plain(data.get("pay_amount")),
        received=_plain(data.get("actually_paid")),
        parent=str(data["parent_payment_id"]) if nowpayments_gateway.is_extra(data) else None,
    )
    _keep_np_records(locked, records)

    if parsed.status not in ("succeeded", "received", "failed"):
        return {"status": "ignored", "result": parsed.status}
    if parsed.status == "failed":
        if entry["parent"] is not None:
            # an extra deposit that did not go through says nothing about the invoice itself
            return {"status": "ignored", "result": "extra_failed"}
        if locked.status != "pending":
            return {"status": "already_processed"}
        return await _apply_outcome(
            session, provider=_NP, parsed=parsed, payment=locked, source=source
        )
    if entry.get("credited") is not None:
        return {"status": "already_processed"}

    if parsed.status == "succeeded" and locked.status != "succeeded":
        # the invoice paid as asked: the deposit credited, or the purchase confirmed
        earlier = sum(
            (decimal.Decimal(r["credited"]) for r in records.values() if r.get("credited")),
            decimal.Decimal(0),
        )
        result = await _apply_outcome(
            session, provider=_NP, parsed=parsed, payment=locked, source=source
        )
        records = _np_records(locked)
        records.setdefault(record_id, {})["credited"] = str(locked.amount_captured)
        _keep_np_records(locked, records)
        # the row says everything that arrived for it, an earlier extra deposit included
        locked.amount_captured = (locked.amount_captured or decimal.Decimal(0)) + earlier
        return result

    # An under-payment, an extra deposit, or the invoice paid a second time.
    if parsed.status == "succeeded" and value is None:
        value = locked.amount
    if value is None or value <= 0:
        if entry.get("review"):
            return {"status": "already_processed"}  # its case is open: said once
        return await _np_needs_review(session, locked, records, record_id)
    return await _np_credit_wallet(session, locked, records, record_id, value, valued_by=valued_by)


async def _purchase_title(session: AsyncSession, payment: Payment) -> str:
    """The property a purchase or down-payment checkout is for (for the member's message)."""
    property_id = None
    if payment.related_investment_id is not None:
        property_id = await session.scalar(
            select(Investment.property_id).where(Investment.id == payment.related_investment_id)
        )
    elif payment.related_plan_id is not None:
        property_id = await session.scalar(
            select(InstallmentPlan.property_id).where(InstallmentPlan.id == payment.related_plan_id)
        )
    title = None
    if property_id is not None:
        title = await session.scalar(select(Property.title).where(Property.id == property_id))
    return title or "your property"


async def _np_credit_wallet(
    session: AsyncSession,
    locked: Payment,
    records: dict[str, dict],
    record_id: str,
    value: decimal.Decimal,
    *,
    valued_by: str = "notification",
) -> dict:
    """Money arrived that is not the invoice simply paid: it goes to the member's wallet.
    ``valued_by``: where its value came from (the notification, or what NOWPayments answered
    when asked: its record of the payment, or its rate for the coin)."""
    value = value.quantize(decimal.Decimal("0.01"))
    purchase = locked.purpose in ("investment", "installment")
    # the row was settled before this arrived: a further payment, said as one
    again = locked.status == "succeeded"
    what = "installment plan" if locked.purpose == "installment" else "purchase"
    title = await _purchase_title(session, locked) if purchase else ""
    released = False
    if purchase and locked.status == "pending":
        # the purchase is not completed with it: its units go back on sale
        if locked.purpose == "investment":
            from app.services import investment_service

            await investment_service.release_reservation_for_payment(
                session, payment=locked, reason="payment_short_credited"
            )
        else:
            from app.services import installment_service

            await installment_service.release_plan_for_payment(
                session, payment=locked, reason="payment_short_credited"
            )
        locked.status = "failed"
        released = True
    elif not purchase and locked.status != "succeeded":
        locked.status = "succeeded"

    await wallet_service.credit(
        session,
        user_id=locked.user_id,
        amount=value,
        reference_id=locked.id,
        payment_method=PaymentMethod.crypto,
        description=(
            f"Crypto payment for {title}: credited to the wallet"
            if purchase
            else "Deposit via nowpayments"
        ),
    )
    locked.amount_captured = (locked.amount_captured or decimal.Decimal(0)) + value
    entry = records.setdefault(record_id, {})
    entry["credited"] = str(value)
    if valued_by != "notification":
        entry["valued_by"] = valued_by
    # it waited for a person and could be valued after all: their case is answered
    reviewed = bool(entry.pop("review", False))
    _keep_np_records(locked, records)
    await write_audit(
        session,
        action="payment.webhook.received_credited",
        entity_type="payment",
        entity_id=str(locked.id),
        after={
            "nowpayments_payment": record_id,
            "credited": str(value),
            "valued_by": valued_by,
            "invoice": str(locked.amount),
            "purpose": locked.purpose,
            "released": released,
        },
    )
    if reviewed:
        from app.services import ops_case_service

        await ops_case_service.settle_payment_review(
            session,
            payment=locked,
            note=(
                f"Settled without a person: NOWPayments payment {record_id} could be valued "
                f"when its notification arrived again, and {value} {locked.currency} was "
                "credited to the member's wallet. Nothing more to do."
            ),
        )
    money, due = f"{value} {locked.currency}", f"{locked.amount} {locked.currency}"
    if not purchase:
        heading = "Deposit received"
        message = (
            f"Another crypto payment arrived for a deposit that was already credited. {money} "
            "more was credited to your wallet."
            if again
            else f"Your crypto payment arrived as {money}, not the {due} of the deposit you "
            "started: a smaller amount, or a coin or network other than the one you chose. "
            f"{money} was credited to your wallet."
        )
    else:
        heading = "Crypto payment credited to your wallet"
        message = (
            f"Your crypto payment for {title} arrived as {money}, not the {due} due: a smaller "
            f"amount, or a coin or network other than the one you chose. The {what} was not "
            f"completed and its units were released. {money} is in your wallet: you can buy "
            "from your wallet."
            if released
            else f"A crypto payment of {money} arrived for {title} outside its checkout. It "
            "was credited to your wallet."
        )
    await notification_service.notify(
        session,
        user_id=locked.user_id,
        type="wallet",
        title=heading,
        message=message,
        email_category="investment_updates",
    )
    return {"status": "processed", "result": "credited_received"}


async def _np_needs_review(
    session: AsyncSession, locked: Payment, records: dict[str, dict], record_id: str
) -> dict:
    """Money arrived that could not be valued: a person looks at it. Said once. The same
    notification sent again later is tried again (``_np_replay_wanted``)."""
    records.setdefault(record_id, {})["review"] = True
    _keep_np_records(locked, records)
    from app.services import ops_case_service

    await ops_case_service.open_payment_review(
        session,
        payment=locked,
        subject=f"Crypto payment received but not valued ({locked.amount} {locked.currency})",
        summary=(
            f"NOWPayments reported money for a crypto {locked.purpose} of {locked.amount} "
            f"{locked.currency} (its payment {record_id}, invoice {locked.provider_payment_id}) "
            "without saying what it is worth, and gave no value or rate when asked: an extra "
            "deposit or one in another coin. Nothing was credited. Open the payment in the "
            "NOWPayments dashboard: once it shows what the deposit is worth, press IPN on it to "
            "send its notification again. The platform then credits the member and resolves "
            "this case by itself. If it still cannot be valued, the developer has to credit it."
        ),
    )
    await notification_service.notify(
        session,
        user_id=locked.user_id,
        type="wallet",
        title="Crypto payment received",
        message=(
            "A crypto payment arrived for you in a coin or an amount we could not value "
            "automatically. Our team is checking it and will credit your wallet."
        ),
        email_category="investment_updates",
    )
    return {"status": "processed", "result": "needs_review"}


async def open_crypto_payments(
    session: AsyncSession, *, user_id: uuid.UUID, now: datetime.datetime | None = None
) -> list[dict]:
    """The member's crypto payments still on their way, newest first: started within
    ``OPEN_CRYPTO_WINDOW`` (``OPEN_CRYPTO_UNSEEN_WINDOW`` when no payment page was ever opened
    for it), or older with funds already seen on the network. Each says the coin chosen, how
    far it is, and the page to finish it on."""
    now = now or datetime.datetime.now(datetime.UTC)
    rows = (
        (
            await session.execute(
                select(Payment)
                .where(
                    Payment.user_id == user_id,
                    Payment.provider == _NP,
                    Payment.status == "pending",
                    Payment.created_at >= now - SYNC_MAX_AGE,
                )
                .order_by(Payment.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    out = []
    for payment in rows:
        records = _np_records(payment)
        in_flight = any(r.get("status") in _NP_IN_FLIGHT for r in records.values())
        window = OPEN_CRYPTO_WINDOW if records else OPEN_CRYPTO_UNSEEN_WINDOW
        if not in_flight and payment.created_at < now - window:
            continue
        raw = payment.raw_payload if isinstance(payment.raw_payload, dict) else {}
        coin = raw.get("pay_currency") or next(
            (r["coin"] for r in records.values() if r.get("coin")), None
        )
        out.append(
            {
                "id": payment.id,
                "purpose": payment.purpose,
                "amount": str(payment.amount),
                "currency": payment.currency,
                "coin": coin,
                "stage": "confirming" if in_flight else "awaiting_transfer",
                "checkout_url": raw.get("checkout_url"),
                "created_at": payment.created_at,
                "title": (
                    await _purchase_title(session, payment)
                    if payment.purpose in ("investment", "installment")
                    else None
                ),
            }
        )
    return out


# --- Provider lookup: the safety net when the webhook never arrives ---------- #
# A card payment used to be credited ONLY by the webhook. If the endpoint was created after
# the payment, its signing secret was wrong, or the delivery failed, the money left the
# customer and nothing moved here. These paths ask Stripe directly (by the Checkout Session
# id we store) and settle through ``_apply`` — the same guarded code the webhook uses, so
# nothing can be credited twice.
# Crypto is not looked up: for a NOWPayments invoice we store the INVOICE id, and its payment
# id only arrives with the IPN, so there is nothing reliable to ask by. A crypto payment still
# pending too long opens a staff case (ops_case_service) instead.
SYNC_PROVIDERS = ("stripe",)
# providers whose payments may be stuck waiting for a webhook (a staff case after a while)
WEBHOOK_PROVIDERS = ("stripe", "nowpayments")
# A fresh payment is still on the hosted checkout page: do not ask about it yet.
SYNC_MIN_AGE = datetime.timedelta(minutes=2)
# Older than this and the provider has long expired the session; leave it to staff.
SYNC_MAX_AGE = datetime.timedelta(days=7)
# The SPA polls a returning payment every few seconds; ask the provider at most this often.
ON_READ_SYNC_INTERVAL_SECONDS = 15.0
_last_sync_at: dict[uuid.UUID, float] = {}


def _lookup_configured(provider: str) -> bool:
    return provider == "stripe" and stripe_gateway.lookup_configured()


async def _lookup(provider: str, provider_payment_id: str) -> ParsedWebhook:
    return await stripe_gateway.get_checkout_status(provider_payment_id)


async def sync_payment(session: AsyncSession, payment: Payment) -> dict:
    """Ask the provider about one pending card payment and settle it if it ended.
    Returns the same shape as ``process_webhook``; ``still_pending`` when the provider has no
    outcome yet. Raises the gateway's AppError / httpx error on a provider failure — the
    callers decide whether that is fatal (an admin click) or counted (the cron sweep)."""
    if payment.provider not in SYNC_PROVIDERS or not payment.provider_payment_id:
        return {"status": "ignored", "result": "not_syncable"}
    if payment.status != "pending":
        return {"status": "already_processed"}
    if not _lookup_configured(payment.provider):
        return {"status": "ignored", "result": "provider_not_configured"}
    parsed = await _lookup(payment.provider, payment.provider_payment_id)
    if parsed.status not in ("succeeded", "failed"):
        return {"status": "still_pending", "result": parsed.status}
    # The webhook (or another lookup) may have settled it while we asked: lock the row, read
    # it fresh, and stop if it is no longer pending. Concurrent lookups wait here in turn.
    current = (await session.execute(_locked(payment.id))).scalar_one()
    if current.status != "pending":
        return {"status": "already_processed"}
    seen = await session.execute(
        select(PaymentEvent.id).where(
            PaymentEvent.provider == payment.provider, PaymentEvent.event_id == parsed.event_id
        )
    )
    if seen.first() is not None:
        return {"status": "duplicate"}
    session.add(
        PaymentEvent(
            provider=payment.provider,
            event_id=parsed.event_id,
            payment_id=payment.id,
            type=parsed.type,
        )
    )
    return await _apply(
        session, provider=payment.provider, parsed=parsed, payment=payment, source="sync"
    )


async def sync_on_read(session: AsyncSession, payment: Payment) -> None:
    """Best-effort lookup when the payer is looking at a pending payment (the return page
    polls ``GET /payments/{id}``): converge within seconds even if the webhook never comes.
    Throttled per payment and never raises — a provider hiccup must not break the read."""
    if payment.status != "pending" or payment.provider not in SYNC_PROVIDERS:
        return
    if not payment.provider_payment_id or not _lookup_configured(payment.provider):
        return
    age = datetime.datetime.now(datetime.UTC) - payment.created_at
    if age < datetime.timedelta(seconds=10) or age > SYNC_MAX_AGE:
        return
    now = time.monotonic()
    last = _last_sync_at.get(payment.id)
    if last is not None and now - last < ON_READ_SYNC_INTERVAL_SECONDS:
        return
    if len(_last_sync_at) > 2000:
        _last_sync_at.clear()
    _last_sync_at[payment.id] = now
    try:
        await sync_payment(session, payment)
    except (AppError, httpx.HTTPError) as exc:
        logger.warning("Payment %s: provider lookup failed on read: %s", payment.id, exc)


async def reconcile_pending(
    session: AsyncSession,
    *,
    now: datetime.datetime | None = None,
    min_age: datetime.timedelta = SYNC_MIN_AGE,
    max_age: datetime.timedelta = SYNC_MAX_AGE,
    limit: int = 200,
) -> dict:
    """Cron sweep: settle every pending card payment Stripe says has ended.

    Each payment is settled in its OWN transaction, committed before the next Stripe call:
    no lock is held across the batch, and one payment's failure (provider error, a row
    another worker is settling) never rolls back the others. Idempotent — a settled row is
    skipped by the locked status guard. Honest no-op when Stripe is not configured."""
    now = now or datetime.datetime.now(datetime.UTC)
    providers = [p for p in SYNC_PROVIDERS if _lookup_configured(p)]
    out = {
        "configured": bool(providers),
        "checked": 0,
        "settled": 0,
        "failed": 0,
        "pending": 0,
        "errors": 0,
    }
    if not providers:
        return out
    ids = (
        (
            await session.execute(
                select(Payment.id)
                .where(
                    Payment.status == "pending",
                    Payment.provider.in_(providers),
                    Payment.provider_payment_id.isnot(None),
                    Payment.created_at <= now - min_age,
                    Payment.created_at >= now - max_age,
                )
                .order_by(Payment.created_at)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    from app.core.db import session_scope  # local: the per-payment transactions

    for payment_id in ids:
        out["checked"] += 1
        try:
            async with session_scope() as own:
                payment = await own.get(Payment, payment_id)
                if payment is None or payment.status != "pending":
                    out["settled"] += 1  # settled meanwhile (webhook / another sweep)
                    continue
                result = await sync_payment(own, payment)
        except (AppError, httpx.HTTPError) as exc:
            logger.warning("Payment %s: provider lookup failed in reconcile: %s", payment_id, exc)
            out["errors"] += 1
            continue
        except IntegrityError:
            # another worker recorded the same outcome first: it settled this payment
            out["settled"] += 1
            continue
        if result.get("status") == "still_pending":
            out["pending"] += 1
        elif result.get("result") == "failed":
            out["failed"] += 1
        elif result.get("status") in ("processed", "duplicate", "already_processed"):
            out["settled"] += 1
    return out


async def _locate(session: AsyncSession, provider: str, parsed: ParsedWebhook) -> Payment | None:
    if parsed.order_id:
        try:
            pid = uuid.UUID(parsed.order_id)
        except ValueError:
            pid = None
        if pid is not None:
            payment = await session.get(Payment, pid)
            if payment is not None and payment.provider == provider:
                return payment
    if parsed.provider_payment_id:
        res = await session.execute(
            select(Payment).where(
                Payment.provider == provider,
                Payment.provider_payment_id == parsed.provider_payment_id,
            )
        )
        payment = res.scalar_one_or_none()
        if payment is not None:
            return payment
    if provider == _NP:
        # A deposit NOWPayments added to an invoice may come without our order: it still
        # names the invoice (what the row keeps), or the payment it was added to.
        invoice = parsed.raw.get("invoice_id")
        if invoice not in (None, ""):
            payment = (
                await session.execute(
                    select(Payment).where(
                        Payment.provider == _NP, Payment.provider_payment_id == str(invoice)
                    )
                )
            ).scalar_one_or_none()
            if payment is not None:
                return payment
        if nowpayments_gateway.is_extra(parsed.raw):
            parent = str(parsed.raw["parent_payment_id"])
            return (
                await session.execute(
                    select(Payment)
                    .where(Payment.provider == _NP, Payment.raw_payload[_NP].has_key(parent))
                    .limit(1)
                )
            ).scalar_one_or_none()
    return None
