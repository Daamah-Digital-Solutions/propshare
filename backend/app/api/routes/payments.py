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

from app.api.deps import PrincipalDep, SessionDep
from app.core.ratelimit import WEBHOOK_LIMIT, limiter
from app.schemas.wallet import PaymentStatusOut
from app.services import payment_service, withdrawal_service

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


@router.get("/{payment_id}", response_model=PaymentStatusOut)
async def get_payment(payment_id: uuid.UUID, principal: PrincipalDep, session: SessionDep):
    p = await payment_service.get_payment(session, user_id=principal.user_id, payment_id=payment_id)
    return PaymentStatusOut(
        id=p.id,
        provider=p.provider,
        status=p.status,
        amount=str(p.amount),
        amount_captured=str(p.amount_captured) if p.amount_captured is not None else None,
        created_at=p.created_at,
    )


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
    """Stripe payout/transfer settlement + Connect account.updated events."""
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
