"""Withdrawal + Stripe Connect routes (Phase 7).

- POST /wallet/withdrawals       request a payout (KYC-gated, Idempotency-Key).
- GET  /wallet/withdrawals       the caller's withdrawals.
- POST /wallet/connect/onboard   start/continue Stripe Connect bank onboarding.
- GET  /wallet/connect/status    the caller's Connect onboarding status.

Funds are held on request; the provider is called later by the admin/cron executor;
settlement is webhook-only (see routes/payments.py). Honest 503 per rail.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import KycVerifiedDep, PrincipalDep, SessionDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.identity import User
from app.schemas.withdrawal import (
    ConnectOnboardOut,
    ConnectStatusOut,
    WithdrawalCreateIn,
    WithdrawalCreateOut,
    WithdrawalListOut,
    WithdrawalOut,
)
from app.services import connect_service, withdrawal_service

router = APIRouter(prefix="/api/v1/wallet", tags=["withdrawals"])


@router.post("/withdrawals", response_model=WithdrawalCreateOut)
async def create_withdrawal(
    body: WithdrawalCreateIn, request: Request, session: SessionDep, principal: KycVerifiedDep
):
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "An Idempotency-Key header is required for withdrawals.",
            status_code=400,
        )
    email = await session.scalar(select(User.email).where(User.id == principal.user_id))
    result = await withdrawal_service.request_withdrawal(
        session,
        user_id=principal.user_id,
        amount=body.amount,
        method=body.method,
        address=body.address,
        idempotency_key=idempotency_key,
        user_email=str(email or ""),
    )
    return WithdrawalCreateOut(**result)


@router.get("/withdrawals", response_model=WithdrawalListOut)
async def my_withdrawals(principal: PrincipalDep, session: SessionDep):
    rows = await withdrawal_service.list_my_withdrawals(session, principal.user_id)
    items = [
        WithdrawalOut(
            id=w.id,
            amount=str(w.amount),
            method=w.method,
            provider=w.provider,
            status=w.status,
            failure_reason=w.failure_reason,
            created_at=w.created_at,
            completed_at=w.completed_at,
        )
        for w in rows
    ]
    return WithdrawalListOut(items=items, total=len(items))


@router.post("/connect/onboard", response_model=ConnectOnboardOut)
async def connect_onboard(request: Request, session: SessionDep, principal: KycVerifiedDep):
    email = await session.scalar(select(User.email).where(User.id == principal.user_id))
    app_base = get_settings().app_base_url.rstrip("/")
    result = await connect_service.start_onboarding(
        session,
        user_id=principal.user_id,
        email=str(email or ""),
        refresh_url=f"{app_base}/dashboard?connect=refresh",
        return_url=f"{app_base}/dashboard?connect=done",
    )
    return ConnectOnboardOut(**result)


@router.get("/connect/status", response_model=ConnectStatusOut)
async def connect_status(principal: PrincipalDep, session: SessionDep):
    acct = await connect_service.get_account(session, principal.user_id)
    if acct is None:
        return ConnectStatusOut(
            status="none", payouts_enabled=False, details_submitted=False, stripe_account_id=None
        )
    return ConnectStatusOut(
        status=acct.status,
        payouts_enabled=acct.payouts_enabled,
        details_submitted=acct.details_submitted,
        stripe_account_id=acct.stripe_account_id,
    )
