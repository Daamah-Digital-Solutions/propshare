"""Wallet & deposit routes (Phase 4).

- GET  /wallet/me            balance summary (live).
- POST /wallet/deposit       create a deposit intent -> hosted checkout URL.
                             KYC-gated (verified users only); Idempotency-Key required.
- GET  /wallet/transactions  paginated ledger.

Deposits are credited ONLY by the provider webhook (see routes/payments.py), never
here — this endpoint just creates the intent.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.api.deps import KycVerifiedDep, PrincipalDep, SessionDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.wallet import (
    DepositIn,
    DepositOut,
    TransactionListOut,
    TransactionOut,
    WalletOut,
)
from app.services import payment_service, wallet_service

router = APIRouter(prefix="/api/v1/wallet", tags=["wallet"])


@router.get("/me", response_model=WalletOut)
async def my_wallet(principal: PrincipalDep, session: SessionDep):
    w = await wallet_service.get_wallet(session, principal.user_id)
    return WalletOut(
        balance=str(w.balance),
        pending_balance=str(w.pending_balance),
        total_invested=str(w.total_invested),
        total_returns=str(w.total_returns),
        currency=get_settings().wallet_currency,
    )


@router.post("/deposit", response_model=DepositOut)
async def deposit(
    body: DepositIn,
    request: Request,
    session: SessionDep,
    principal: KycVerifiedDep,
):
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "An Idempotency-Key header is required for deposits.",
            status_code=400,
        )
    app_base = get_settings().app_base_url.rstrip("/")
    api_base = str(request.base_url).rstrip("/")
    result = await payment_service.create_deposit(
        session,
        user_id=principal.user_id,
        amount=body.amount,
        method=body.method,
        idempotency_key=idempotency_key,
        success_url=f"{app_base}/dashboard?deposit=success",
        cancel_url=f"{app_base}/dashboard?deposit=cancelled",
        ipn_url=f"{api_base}/api/v1/payments/webhooks/nowpayments",
    )
    return DepositOut(**result)


@router.get("/transactions", response_model=TransactionListOut)
async def transactions(
    principal: PrincipalDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await wallet_service.list_transactions(
        session, principal.user_id, limit=limit, offset=offset
    )
    items = [
        TransactionOut(
            id=t.id,
            type=str(t.type),
            amount=str(t.amount),
            status=t.status,
            description=t.description,
            payment_method=str(t.payment_method) if t.payment_method is not None else None,
            reference_id=t.reference_id,
            created_at=t.created_at,
        )
        for t in rows
    ]
    return TransactionListOut(items=items, total=total, limit=limit, offset=offset)
