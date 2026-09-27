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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Payment, PaymentEvent
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


logger = logging.getLogger(__name__)


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
            product_name=_CHECKOUT_LABEL.get(method, "Capimax investment"),
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

    return await _apply(
        session, provider=provider, parsed=parsed, payment=payment, source="webhook"
    )


async def _apply(
    session: AsyncSession, *, provider: str, parsed: ParsedWebhook, payment: Payment, source: str
) -> dict:
    """Apply a provider outcome to a located payment. Shared by the webhook and the direct
    provider lookup (``sync_payment``), so both settle through exactly the same guarded path:
    the row lock + status guard below is what makes a webhook and a lookup that both report
    the same payment paid credit it once."""
    if parsed.status == "succeeded":
        # Layer 2: lock the row + guard the state transition (exactly-once credit).
        locked = (
            await session.execute(select(Payment).where(Payment.id == payment.id).with_for_update())
        ).scalar_one()
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
        locked = (
            await session.execute(select(Payment).where(Payment.id == payment.id).with_for_update())
        ).scalar_one()
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
        return {"status": "processed", "result": "failed"}

    return {"status": "ignored", "result": parsed.status}


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
    # Layer 1 (same key space as the webhook): NOWPayments keys both by <id>:<status>, so an
    # IPN that already applied this outcome makes the lookup a duplicate.
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
    Idempotent (a settled row is skipped by the status guard); one provider error never
    aborts the batch. Honest no-op per provider that is not configured."""
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
    rows = (
        (
            await session.execute(
                select(Payment)
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
    for payment in rows:
        out["checked"] += 1
        try:
            result = await sync_payment(session, payment)
        except (AppError, httpx.HTTPError) as exc:
            logger.warning("Payment %s: provider lookup failed in reconcile: %s", payment.id, exc)
            out["errors"] += 1
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
        return res.scalar_one_or_none()
    return None
