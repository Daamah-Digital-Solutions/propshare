"""Wallet service (Phase 4) — the ONLY code allowed to mutate balances.

Every credit/debit happens inside the caller's DB transaction, locks the wallet
row (``SELECT … FOR UPDATE``), writes a matching append-only ``transactions``
row, and an ``audit_log`` entry. Invariant: ``wallet.balance == SUM(ledger)``.
The wallets non-negative CHECK constraints (from 0001) are the last line of
defense against a negative balance.
"""

from __future__ import annotations

import decimal
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import Transaction, Wallet
from app.models.base import PaymentMethod, TransactionType


async def lock_wallets(session: AsyncSession, user_ids: list[uuid.UUID]) -> None:
    """Acquire ``SELECT … FOR UPDATE`` locks on the given users' wallets in the GLOBAL
    wallet lock order (sorted by ``str(user_id)``), one row at a time so acquisition
    order is deterministic. Use this when a single atomic operation must touch more than
    one wallet (e.g. a distribution crediting owners + their referring brokers) so the
    locks are always taken in the same order and concurrent ops can't deadlock. Missing
    wallets are skipped (every user is provisioned a wallet at signup)."""
    for uid in sorted(set(user_ids), key=str):
        await session.execute(select(Wallet.id).where(Wallet.user_id == uid).with_for_update())


async def get_wallet(session: AsyncSession, user_id: uuid.UUID) -> Wallet:
    res = await session.execute(select(Wallet).where(Wallet.user_id == user_id))
    wallet = res.scalar_one_or_none()
    if wallet is None:
        raise AppError("NOT_FOUND", "Wallet not found", status_code=404)
    return wallet


async def credit(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: decimal.Decimal,
    reference_id: uuid.UUID,
    tx_type: TransactionType = TransactionType.deposit,
    payment_method: PaymentMethod | None = None,
    description: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> Wallet:
    """Add ``amount`` to the wallet balance + write the ledger row + audit. Must be
    called inside a transaction; locks the wallet row to serialize concurrent
    credits (e.g. duplicate webhook deliveries)."""
    if amount <= 0:
        raise AppError("INVALID_AMOUNT", "Credit amount must be positive.", status_code=422)
    res = await session.execute(select(Wallet).where(Wallet.user_id == user_id).with_for_update())
    wallet = res.scalar_one_or_none()
    if wallet is None:
        raise AppError("NOT_FOUND", "Wallet not found", status_code=404)

    before = wallet.balance
    wallet.balance = before + amount
    session.add(
        Transaction(
            user_id=user_id,
            type=tx_type,
            amount=amount,
            reference_id=reference_id,
            payment_method=payment_method,
            status="completed",
            description=description,
        )
    )
    await write_audit(
        session,
        action="wallet.credit",
        entity_type="wallet",
        entity_id=str(wallet.id),
        actor_id=actor_id,
        before={"balance": str(before)},
        after={"balance": str(wallet.balance), "amount": str(amount), "ref": str(reference_id)},
    )
    return wallet


async def debit(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    reference_id: uuid.UUID,
    line_items: list[tuple[TransactionType, decimal.Decimal, str | None]],
    payment_method: PaymentMethod | None = None,
    actor_id: uuid.UUID | None = None,
) -> Wallet:
    """Subtract money from the wallet for one logical operation, writing ONE signed
    (negative) ledger row per line item so ``balance == SUM(ledger)`` still holds.

    Locks the wallet row (``FOR UPDATE``) and checks the *total* against the balance
    in the same critical section, so concurrent debits can't drive it negative (the
    wallets balance >= 0 CHECK is the last backstop). Must run inside a transaction.
    """
    total = sum((amt for _t, amt, _d in line_items), start=decimal.Decimal("0"))
    if total <= 0 or any(amt <= 0 for _t, amt, _d in line_items):
        raise AppError("INVALID_AMOUNT", "Debit amounts must be positive.", status_code=422)
    res = await session.execute(select(Wallet).where(Wallet.user_id == user_id).with_for_update())
    wallet = res.scalar_one_or_none()
    if wallet is None:
        raise AppError("NOT_FOUND", "Wallet not found", status_code=404)
    if wallet.balance < total:
        raise AppError(
            "INSUFFICIENT_FUNDS",
            "Wallet balance is insufficient for this transaction.",
            status_code=422,
            details={"balance": str(wallet.balance), "required": str(total)},
        )

    before = wallet.balance
    wallet.balance = before - total
    for tx_type, amt, desc in line_items:
        session.add(
            Transaction(
                user_id=user_id,
                type=tx_type,
                amount=-amt,  # signed: a debit is a negative ledger entry
                reference_id=reference_id,
                payment_method=payment_method,
                status="completed",
                description=desc,
            )
        )
    await write_audit(
        session,
        action="wallet.debit",
        entity_type="wallet",
        entity_id=str(wallet.id),
        actor_id=actor_id,
        before={"balance": str(before)},
        after={"balance": str(wallet.balance), "amount": str(total), "ref": str(reference_id)},
    )
    return wallet


async def hold_for_withdrawal(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: decimal.Decimal,
    reference_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> Wallet:
    """Reserve funds for a withdrawal: debit spendable ``balance`` and mirror the
    in-flight amount in ``pending_balance``, under the wallet row lock. The debit is
    booked immediately as a ``withdrawal`` ledger row (-amount) so ``balance ==
    SUM(ledger)`` holds at once; ``pending_balance`` tracks money in flight. The
    balance check + debit happen in one critical section, so concurrent withdrawals
    cannot over-draw (the wallets balance >= 0 CHECK is the last backstop)."""
    if amount <= 0:
        raise AppError("INVALID_AMOUNT", "Withdrawal amount must be positive.", status_code=422)
    res = await session.execute(select(Wallet).where(Wallet.user_id == user_id).with_for_update())
    wallet = res.scalar_one_or_none()
    if wallet is None:
        raise AppError("NOT_FOUND", "Wallet not found", status_code=404)
    if wallet.balance < amount:
        raise AppError(
            "INSUFFICIENT_FUNDS",
            "Wallet balance is insufficient for this withdrawal.",
            status_code=422,
            details={"balance": str(wallet.balance), "requested": str(amount)},
        )
    before = wallet.balance
    wallet.balance = before - amount
    wallet.pending_balance = wallet.pending_balance + amount
    session.add(
        Transaction(
            user_id=user_id,
            type=TransactionType.withdrawal,
            amount=-amount,
            reference_id=reference_id,
            status="pending",
            description="Withdrawal hold",
        )
    )
    await write_audit(
        session,
        action="wallet.withdrawal_hold",
        entity_type="wallet",
        entity_id=str(wallet.id),
        actor_id=actor_id,
        before={"balance": str(before), "pending": str(wallet.pending_balance - amount)},
        after={"balance": str(wallet.balance), "pending": str(wallet.pending_balance)},
    )
    return wallet


async def settle_withdrawal(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: decimal.Decimal,
    reference_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> Wallet:
    """Money has actually left: clear the in-flight hold (``pending_balance -=``). The
    ``balance`` was already debited at hold time, so no ledger row is written here."""
    res = await session.execute(select(Wallet).where(Wallet.user_id == user_id).with_for_update())
    wallet = res.scalar_one_or_none()
    if wallet is None:
        raise AppError("NOT_FOUND", "Wallet not found", status_code=404)
    before_pending = wallet.pending_balance
    wallet.pending_balance = max(decimal.Decimal("0"), before_pending - amount)
    await write_audit(
        session,
        action="wallet.withdrawal_settled",
        entity_type="wallet",
        entity_id=str(wallet.id),
        actor_id=actor_id,
        before={"pending": str(before_pending)},
        after={"pending": str(wallet.pending_balance), "ref": str(reference_id)},
    )
    return wallet


async def release_hold(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: decimal.Decimal,
    reference_id: uuid.UUID,
    reason: str,
    actor_id: uuid.UUID | None = None,
) -> Wallet:
    """Return held funds to spendable balance (reject / failed / returned payout):
    credit ``balance`` back with a compensating ``withdrawal`` ledger row (+amount)
    and drop the in-flight ``pending_balance``. Idempotency is the caller's job (it
    guards on the withdrawal status under FOR UPDATE before calling this)."""
    res = await session.execute(select(Wallet).where(Wallet.user_id == user_id).with_for_update())
    wallet = res.scalar_one_or_none()
    if wallet is None:
        raise AppError("NOT_FOUND", "Wallet not found", status_code=404)
    before = wallet.balance
    wallet.balance = before + amount
    wallet.pending_balance = max(decimal.Decimal("0"), wallet.pending_balance - amount)
    session.add(
        Transaction(
            user_id=user_id,
            type=TransactionType.withdrawal,
            amount=amount,  # compensating credit reverses the hold's negative row
            reference_id=reference_id,
            status="reversed",
            description=f"Withdrawal reversed: {reason}",
        )
    )
    await write_audit(
        session,
        action="wallet.withdrawal_released",
        entity_type="wallet",
        entity_id=str(wallet.id),
        actor_id=actor_id,
        before={"balance": str(before)},
        after={"balance": str(wallet.balance), "reason": reason, "ref": str(reference_id)},
    )
    return wallet


async def list_transactions(
    session: AsyncSession, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0
) -> tuple[list[Transaction], int]:
    total = (
        await session.scalar(
            select(func.count()).select_from(Transaction).where(Transaction.user_id == user_id)
        )
    ) or 0
    res = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .limit(min(limit, 200))
        .offset(max(offset, 0))
    )
    return list(res.scalars().all()), int(total)
