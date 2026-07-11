"""Saved payout destinations (Task 3) — a user's own bank accounts + crypto wallets.

These feed the MANUAL withdrawal flow (the admin pays out to the chosen destination by
hand). CRUD only — no money moves here — so plain authentication (not KYC) is enough.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import PrincipalDep, SessionDep
from app.models import UserBankAccount, UserCryptoWallet
from app.schemas.payout_methods import (
    BankAccountIn,
    BankAccountOut,
    CryptoWalletIn,
    CryptoWalletOut,
)
from app.services import payout_methods_service

router = APIRouter(prefix="/api/v1/wallet", tags=["payout-methods"])


def _bank_out(a: UserBankAccount) -> BankAccountOut:
    return BankAccountOut(
        id=a.id,
        label=a.label,
        account_holder=a.account_holder,
        bank_name=a.bank_name,
        iban=a.iban,
        account_number=a.account_number,
        swift_bic=a.swift_bic,
        country=a.country,
        currency=a.currency,
        is_default=a.is_default,
        created_at=a.created_at,
    )


def _crypto_out(w: UserCryptoWallet) -> CryptoWalletOut:
    return CryptoWalletOut(
        id=w.id,
        label=w.label,
        network=w.network,
        address=w.address,
        is_default=w.is_default,
        created_at=w.created_at,
    )


# --- bank accounts --------------------------------------------------------- #
@router.get("/bank-accounts", response_model=list[BankAccountOut])
async def list_bank_accounts(principal: PrincipalDep, session: SessionDep):
    rows = await payout_methods_service.list_bank_accounts(session, principal.user_id)
    return [_bank_out(a) for a in rows]


@router.post("/bank-accounts", response_model=BankAccountOut)
async def add_bank_account(body: BankAccountIn, principal: PrincipalDep, session: SessionDep):
    acct = await payout_methods_service.add_bank_account(
        session,
        user_id=principal.user_id,
        account_holder=body.account_holder,
        bank_name=body.bank_name,
        iban=body.iban,
        account_number=body.account_number,
        swift_bic=body.swift_bic,
        country=body.country,
        currency=body.currency,
        label=body.label,
    )
    return _bank_out(acct)


@router.post("/bank-accounts/{account_id}/default", response_model=BankAccountOut)
async def default_bank_account(
    account_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
):
    acct = await payout_methods_service.set_default_bank_account(
        session, principal.user_id, account_id
    )
    return _bank_out(acct)


@router.delete("/bank-accounts/{account_id}")
async def delete_bank_account(account_id: uuid.UUID, principal: PrincipalDep, session: SessionDep):
    await payout_methods_service.delete_bank_account(session, principal.user_id, account_id)
    return Response(status_code=204)


# --- crypto wallets -------------------------------------------------------- #
@router.get("/crypto-wallets", response_model=list[CryptoWalletOut])
async def list_crypto_wallets(principal: PrincipalDep, session: SessionDep):
    rows = await payout_methods_service.list_crypto_wallets(session, principal.user_id)
    return [_crypto_out(w) for w in rows]


@router.post("/crypto-wallets", response_model=CryptoWalletOut)
async def add_crypto_wallet(body: CryptoWalletIn, principal: PrincipalDep, session: SessionDep):
    w = await payout_methods_service.add_crypto_wallet(
        session,
        user_id=principal.user_id,
        network=body.network,
        address=body.address,
        label=body.label,
    )
    return _crypto_out(w)


@router.post("/crypto-wallets/{wallet_id}/default", response_model=CryptoWalletOut)
async def default_crypto_wallet(
    wallet_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
):
    w = await payout_methods_service.set_default_crypto_wallet(
        session, principal.user_id, wallet_id
    )
    return _crypto_out(w)


@router.delete("/crypto-wallets/{wallet_id}")
async def delete_crypto_wallet(wallet_id: uuid.UUID, principal: PrincipalDep, session: SessionDep):
    await payout_methods_service.delete_crypto_wallet(session, principal.user_id, wallet_id)
    return Response(status_code=204)
