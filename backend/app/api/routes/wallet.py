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
from app.schemas.payout_methods import BankClaimIn, PlatformBankAccountOut
from app.schemas.wallet import (
    DepositIn,
    DepositOut,
    TransactionListOut,
    TransactionOut,
    WalletOut,
)
from app.services import (
    manual_deposit_service,
    payment_service,
    platform_accounts_service,
    wallet_service,
)

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


@router.get("/deposit/bank-accounts", response_model=list[PlatformBankAccountOut])
async def deposit_bank_accounts(principal: PrincipalDep, session: SessionDep):
    """The platform's ACTIVE receiving bank accounts — where a user transfers funds before
    submitting a bank-transfer deposit claim. Admin-managed in the /admin panel."""
    accts = await platform_accounts_service.list_active(session)
    return [
        PlatformBankAccountOut(
            id=a.id,
            bank_name=a.bank_name,
            account_holder=a.account_holder,
            iban=a.iban,
            account_number=a.account_number,
            swift_bic=a.swift_bic,
            currency=a.currency,
            country=a.country,
            instructions=a.instructions,
        )
        for a in accts
    ]


@router.post("/deposit/bank-transfer", response_model=DepositOut)
async def deposit_bank_transfer(
    body: BankClaimIn, request: Request, session: SessionDep, principal: KycVerifiedDep
):
    """Submit a bank-transfer deposit CLAIM. After transferring to a platform account the user
    records the amount + reference here; it stays PENDING until an admin confirms the transfer
    arrived and the wallet is credited. KYC-gated; Idempotency-Key required (mirrors deposit)."""
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "An Idempotency-Key header is required for deposits.",
            status_code=400,
        )
    payment = await manual_deposit_service.create_bank_claim(
        session,
        user_id=principal.user_id,
        amount=body.amount,
        platform_account_id=body.platform_account_id,
        reference=body.reference,
        sender_name=body.sender_name,
        idempotency_key=idempotency_key,
    )
    return DepositOut(
        payment_id=payment.id,
        provider=payment.provider,
        status=payment.status,
        checkout_url=None,
    )


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
