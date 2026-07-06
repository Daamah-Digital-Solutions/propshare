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

import decimal
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Payment, PaymentEvent
from app.models.base import PaymentMethod
from app.services import notification_service, wallet_service
from app.services.integrations.payments import ParsedWebhook, nowpayments_gateway, stripe_gateway

# "pronova" is a BRANDED rail that settles via Stripe card (D5 owner decision) — the buyer
# sees the Pronova experience + discount, the money moves on Stripe. Kept as a distinct method
# from plain "card" so it's recorded/branded separately.
_PROVIDER_FOR_METHOD = {"card": "stripe", "crypto": "nowpayments", "pronova": "stripe"}

# Human label shown on the hosted-checkout line item (branding). Deposits keep the wallet
# label; investments name the property purchase, and Pronova carries its brand.
_CHECKOUT_LABEL = {
    "card": "CapiMax investment",
    "pronova": "CapiMax investment · Pronova",
}


def _gateway(provider: str):
    return stripe_gateway if provider == "stripe" else nowpayments_gateway


def provider_for(method: str) -> str:
    return _PROVIDER_FOR_METHOD[method]


def provider_configured(method: str) -> bool:
    """Whether the rail behind ``method`` (card->stripe, crypto->nowpayments) is set up."""
    return _gateway(_PROVIDER_FOR_METHOD[method]).is_configured()


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
) -> dict:
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

    if provider == "stripe":
        result = await stripe_gateway.create_checkout(
            payment_id=payment.id,
            amount=amount_dec,
            currency=currency,
            success_url=success_url,
            cancel_url=cancel_url,
            idempotency_key=idempotency_key,
        )
    else:
        result = await nowpayments_gateway.create_checkout(
            payment_id=payment.id,
            amount=amount_dec,
            currency=currency,
            success_url=success_url,
            cancel_url=cancel_url,
            ipn_url=ipn_url,
        )

    payment.provider_payment_id = result.provider_payment_id
    payment.raw_payload = {"checkout_url": result.checkout_url}
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
) -> dict:
    """Create a hosted-checkout intent for a DIRECT-PAY investment (purpose=investment).

    Unlike a deposit, idempotency is anchored on the investment row (its unique
    ``idempotency_key``), so the Payment itself carries no key. The amount is the
    server-computed total charge (subtotal + platform fee), never client-supplied.
    """
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
        purpose="investment",
        payment_method=method,
        related_investment_id=investment_id,
    )
    session.add(payment)
    await session.flush()

    if provider == "stripe":
        result = await stripe_gateway.create_checkout(
            payment_id=payment.id,
            amount=amount_dec,
            currency=currency,
            success_url=success_url,
            cancel_url=cancel_url,
            idempotency_key=None,
            product_name=_CHECKOUT_LABEL.get(method, "CapiMax investment"),
        )
    else:
        result = await nowpayments_gateway.create_checkout(
            payment_id=payment.id,
            amount=amount_dec,
            currency=currency,
            success_url=success_url,
            cancel_url=cancel_url,
            ipn_url=ipn_url,
        )

    payment.provider_payment_id = result.provider_payment_id
    payment.raw_payload = {"checkout_url": result.checkout_url}
    await write_audit(
        session,
        action="payment.create",
        entity_type="payment",
        entity_id=str(payment.id),
        actor_id=user_id,
        after={"provider": provider, "amount": str(amount_dec), "purpose": "investment"},
    )
    return {
        "payment_id": payment.id,
        "provider": provider,
        "status": "pending",
        "checkout_url": result.checkout_url,
    }


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
    seen = await session.execute(
        select(PaymentEvent.id).where(
            PaymentEvent.provider == provider, PaymentEvent.event_id == parsed.event_id
        )
    )
    if seen.first() is not None:
        return {"status": "duplicate"}

    payment = await _locate(session, provider, parsed)
    session.add(
        PaymentEvent(
            provider=provider,
            event_id=parsed.event_id,
            payment_id=payment.id if payment else None,
            type=parsed.type,
        )
    )
    if payment is None:
        await write_audit(
            session,
            action="payment.webhook.unmatched",
            entity_type="payment",
            entity_id=parsed.provider_payment_id,
            after={"type": parsed.type},
        )
        return {"status": "ignored_unknown_payment"}

    if parsed.status == "succeeded":
        # Layer 2: lock the row + guard the state transition (exactly-once credit).
        locked = (
            await session.execute(select(Payment).where(Payment.id == payment.id).with_for_update())
        ).scalar_one()
        if locked.status == "succeeded":
            return {"status": "already_processed"}
        locked.status = "succeeded"
        locked.amount_captured = parsed.captured_amount or locked.amount
        await write_audit(
            session,
            action="payment.webhook.succeeded",
            entity_type="payment",
            entity_id=str(locked.id),
            after={"captured": str(locked.amount_captured), "purpose": locked.purpose},
        )
        if locked.purpose == "investment":
            # Direct-pay investment: confirm the reservation (units already held), or
            # reconcile if its reservation already expired. No wallet credit.
            from app.services import investment_service

            return await investment_service.confirm_investment(session, payment=locked)

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
        )
        return {"status": "processed", "result": "credited"}

    if parsed.status == "failed":
        payment.status = "failed"
        await write_audit(
            session,
            action="payment.webhook.failed",
            entity_type="payment",
            entity_id=str(payment.id),
            after={"type": parsed.type, "purpose": payment.purpose},
        )
        if payment.purpose == "investment":
            # Release the units held for this abandoned/failed direct-pay reservation.
            from app.services import investment_service

            await investment_service.release_reservation_for_payment(
                session, payment=payment, reason=f"payment_{parsed.status}"
            )
        return {"status": "processed", "result": "failed"}

    return {"status": "ignored", "result": parsed.status}


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
        return res.scalar_one_or_none()
    return None
