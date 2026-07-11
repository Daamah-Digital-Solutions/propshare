"""User payout destinations (Task 3) — a user's own saved bank accounts + crypto wallets.

These are the destinations a MANUAL withdrawal is paid out to. Money never moves here;
this is CRUD only (the admin reads the snapshot on the withdrawal and pays out by hand).
At most one default per user per kind is enforced by a partial unique index (0021), so a
new default is set only after clearing the previous one in the same transaction.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import UserBankAccount, UserCryptoWallet


# --- bank accounts --------------------------------------------------------- #
async def list_bank_accounts(session: AsyncSession, user_id: uuid.UUID) -> list[UserBankAccount]:
    res = await session.execute(
        select(UserBankAccount)
        .where(UserBankAccount.user_id == user_id)
        .order_by(UserBankAccount.is_default.desc(), UserBankAccount.created_at.desc())
    )
    return list(res.scalars().all())


async def get_bank_account(
    session: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID
) -> UserBankAccount:
    acct = await session.get(UserBankAccount, account_id)
    if acct is None or acct.user_id != user_id:
        raise AppError("NOT_FOUND", "Bank account not found.", status_code=404)
    return acct


async def add_bank_account(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    account_holder: str,
    bank_name: str,
    iban: str | None = None,
    account_number: str | None = None,
    swift_bic: str | None = None,
    country: str | None = None,
    currency: str = "USD",
    label: str | None = None,
) -> UserBankAccount:
    if not account_holder.strip() or not bank_name.strip():
        raise AppError(
            "INVALID_INPUT", "Account holder and bank name are required.", status_code=422
        )
    if not (iban and iban.strip()) and not (account_number and account_number.strip()):
        raise AppError(
            "INVALID_INPUT", "Provide an IBAN or an account number.", status_code=422
        )
    # First account of this kind becomes the default automatically.
    existing = await session.scalar(
        select(UserBankAccount.id).where(UserBankAccount.user_id == user_id).limit(1)
    )
    is_default = existing is None
    acct = UserBankAccount(
        user_id=user_id,
        account_holder=account_holder.strip(),
        bank_name=bank_name.strip(),
        iban=(iban or "").strip() or None,
        account_number=(account_number or "").strip() or None,
        swift_bic=(swift_bic or "").strip() or None,
        country=(country or "").strip() or None,
        currency=(currency or "USD").strip() or "USD",
        label=(label or "").strip() or None,
        is_default=is_default,
    )
    session.add(acct)
    await session.flush()
    await write_audit(
        session,
        action="payout_method.bank.added",
        entity_type="user_bank_account",
        entity_id=str(acct.id),
        actor_id=user_id,
        after={"bank_name": acct.bank_name, "is_default": acct.is_default},
    )
    return acct


async def set_default_bank_account(
    session: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID
) -> UserBankAccount:
    acct = await get_bank_account(session, user_id, account_id)
    # Clear the current default FIRST (partial unique index forbids two defaults at once).
    await session.execute(
        update(UserBankAccount)
        .where(UserBankAccount.user_id == user_id, UserBankAccount.is_default.is_(True))
        .values(is_default=False)
    )
    acct.is_default = True
    await session.flush()
    return acct


async def delete_bank_account(
    session: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    acct = await get_bank_account(session, user_id, account_id)
    was_default = acct.is_default
    await session.delete(acct)
    await session.flush()
    if was_default:  # promote the most recent remaining account to default
        nxt = await session.scalar(
            select(UserBankAccount)
            .where(UserBankAccount.user_id == user_id)
            .order_by(UserBankAccount.created_at.desc())
            .limit(1)
        )
        if nxt is not None:
            nxt.is_default = True
    await write_audit(
        session,
        action="payout_method.bank.deleted",
        entity_type="user_bank_account",
        entity_id=str(account_id),
        actor_id=user_id,
    )


# --- crypto wallets -------------------------------------------------------- #
async def list_crypto_wallets(session: AsyncSession, user_id: uuid.UUID) -> list[UserCryptoWallet]:
    res = await session.execute(
        select(UserCryptoWallet)
        .where(UserCryptoWallet.user_id == user_id)
        .order_by(UserCryptoWallet.is_default.desc(), UserCryptoWallet.created_at.desc())
    )
    return list(res.scalars().all())


async def get_crypto_wallet(
    session: AsyncSession, user_id: uuid.UUID, wallet_id: uuid.UUID
) -> UserCryptoWallet:
    w = await session.get(UserCryptoWallet, wallet_id)
    if w is None or w.user_id != user_id:
        raise AppError("NOT_FOUND", "Crypto wallet not found.", status_code=404)
    return w


async def add_crypto_wallet(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    network: str,
    address: str,
    label: str | None = None,
) -> UserCryptoWallet:
    if not network.strip() or not address.strip():
        raise AppError("INVALID_INPUT", "Network and address are required.", status_code=422)
    existing = await session.scalar(
        select(UserCryptoWallet.id).where(UserCryptoWallet.user_id == user_id).limit(1)
    )
    w = UserCryptoWallet(
        user_id=user_id,
        network=network.strip(),
        address=address.strip(),
        label=(label or "").strip() or None,
        is_default=existing is None,
    )
    session.add(w)
    await session.flush()
    await write_audit(
        session,
        action="payout_method.crypto.added",
        entity_type="user_crypto_wallet",
        entity_id=str(w.id),
        actor_id=user_id,
        after={"network": w.network, "is_default": w.is_default},
    )
    return w


async def set_default_crypto_wallet(
    session: AsyncSession, user_id: uuid.UUID, wallet_id: uuid.UUID
) -> UserCryptoWallet:
    w = await get_crypto_wallet(session, user_id, wallet_id)
    await session.execute(
        update(UserCryptoWallet)
        .where(UserCryptoWallet.user_id == user_id, UserCryptoWallet.is_default.is_(True))
        .values(is_default=False)
    )
    w.is_default = True
    await session.flush()
    return w


async def delete_crypto_wallet(
    session: AsyncSession, user_id: uuid.UUID, wallet_id: uuid.UUID
) -> None:
    w = await get_crypto_wallet(session, user_id, wallet_id)
    was_default = w.is_default
    await session.delete(w)
    await session.flush()
    if was_default:
        nxt = await session.scalar(
            select(UserCryptoWallet)
            .where(UserCryptoWallet.user_id == user_id)
            .order_by(UserCryptoWallet.created_at.desc())
            .limit(1)
        )
        if nxt is not None:
            nxt.is_default = True
    await write_audit(
        session,
        action="payout_method.crypto.deleted",
        entity_type="user_crypto_wallet",
        entity_id=str(wallet_id),
        actor_id=user_id,
    )
