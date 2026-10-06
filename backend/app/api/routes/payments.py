"""Payment routes (Phase 4).

- GET  /payments/{id}                 own payment status (SPA polls after redirect).
- POST /payments/webhooks/stripe      PUBLIC, signature-verified (Stripe-Signature).
- POST /payments/webhooks/nowpayments PUBLIC, signature-verified (x-nowpayments-sig).

The webhooks are the AUTOMATION CORE: verify signature -> idempotently credit the
wallet with the provider-captured amount. Never credit on a browser redirect.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.api.deps import AdminOrCronDep, PrincipalDep, SessionDep
from app.core.ratelimit import WEBHOOK_LIMIT, limiter
from app.schemas.wallet import (
    CryptoCoinOut,
    CryptoCoinsOut,
    OpenCryptoPaymentOut,
    PaymentStatusOut,
)
from app.services import payment_service, withdrawal_service
from app.services.integrations.payments import nowpayments_gateway

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


@router.get("/crypto/coins", response_model=CryptoCoinsOut)
async def crypto_coins(principal: PrincipalDep):
    """The coins a crypto payment can be made in: the ones switched on in the platform's
    NOWPayments account, stablecoins first. The member picks one here and the payment page
    then asks for that coin only."""
    coins = await nowpayments_gateway.list_coins()
    return CryptoCoinsOut(items=[CryptoCoinOut(**c) for c in coins], total=len(coins))


@router.get("/crypto/open", response_model=list[OpenCryptoPaymentOut])
async def open_crypto_payments(principal: PrincipalDep, session: SessionDep):
    """The caller's crypto payments that have not settled yet (deposits, purchases, down
    payments), so the wallet can say what is on its way and where to finish it."""
    rows = await payment_service.open_crypto_payments(session, user_id=principal.user_id)
    return [OpenCryptoPaymentOut(**row) for row in rows]


@router.get("/{payment_id}", response_model=PaymentStatusOut)
async def get_payment(payment_id: uuid.UUID, principal: PrincipalDep, session: SessionDep):
    p = await payment_service.get_payment(session, user_id=principal.user_id, payment_id=payment_id)
    # The return page polls this while the payment is pending: if the webhook has not landed
    # yet (or never will), ask the provider directly so the payer sees the credit anyway.
    await payment_service.sync_on_read(session, p)
    return PaymentStatusOut(
        id=p.id,
        provider=p.provider,
        status=p.status,
        amount=str(p.amount),
        amount_captured=str(p.amount_captured) if p.amount_captured is not None else None,
        created_at=p.created_at,
    )


@router.post("/maintenance/reconcile")
async def reconcile_payments(caller: AdminOrCronDep, session: SessionDep) -> dict:
    """Settle pending card/crypto payments by asking the provider directly — the safety net
    for a webhook that never arrived (endpoint created after the payment, wrong signing
    secret, delivery failure). Cron target (admin OR a valid ``X-Cron-Secret``); idempotent;
    also runs on demand. Honest no-op when no provider key is configured."""
    return await payment_service.reconcile_pending(session)


@router.post("/webhooks/stripe")
@limiter.limit(WEBHOOK_LIMIT)
async def stripe_webhook(request: Request, session: SessionDep) -> dict:
    raw = await request.body()
    return await payment_service.process_webhook(
        session,
        provider="stripe",
        raw_body=raw,
        signature=request.headers.get("stripe-signature"),
    )


@router.post("/webhooks/nowpayments")
@limiter.limit(WEBHOOK_LIMIT)
async def nowpayments_webhook(request: Request, session: SessionDep) -> dict:
    raw = await request.body()
    return await payment_service.process_webhook(
        session,
        provider="nowpayments",
        raw_body=raw,
        signature=request.headers.get("x-nowpayments-sig"),
    )


# --- Payout (money-OUT) settlement webhooks (Phase 7) ----------------------- #
@router.post("/webhooks/stripe-payouts")
@limiter.limit(WEBHOOK_LIMIT)
async def stripe_payout_webhook(request: Request, session: SessionDep) -> dict:
    """Stripe's "Connected accounts" endpoint: onboarding (account.updated) and the payouts
    investors' Stripe accounts make to their bank or card. Signed with its own secret."""
    raw = await request.body()
    return await withdrawal_service.process_payout_webhook(
        session,
        provider="stripe",
        raw_body=raw,
        signature=request.headers.get("stripe-signature"),
    )


@router.post("/webhooks/nowpayments-payouts")
@limiter.limit(WEBHOOK_LIMIT)
async def nowpayments_payout_webhook(request: Request, session: SessionDep) -> dict:
    """NOWPayments crypto payout settlement IPN."""
    raw = await request.body()
    return await withdrawal_service.process_payout_webhook(
        session,
        provider="nowpayments",
        raw_body=raw,
        signature=request.headers.get("x-nowpayments-sig"),
    )
