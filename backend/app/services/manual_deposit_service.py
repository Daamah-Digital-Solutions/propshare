"""Manual bank-transfer deposits (Task 3).

A user who pays by bank transfer submits a CLAIM (amount + which platform account they
sent to + a reference) which lands as a ``pending`` Payment (provider='manual_bank').
An admin verifies the transfer arrived and CONFIRMS — only then is the wallet credited
(via wallet_service, the sole balance mutator). Reject leaves the wallet untouched.

Idempotent: an Idempotency-Key replay returns the existing claim; confirm/reject guard
on the Payment status under a row lock, so a double-click can't double-credit.
"""

from __future__ import annotations

import decimal
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import Payment, PlatformBankAccount
from app.models.base import TransactionType
from app.models.identity import User
from app.services import notification_service, wallet_service

_CENTS = decimal.Decimal("0.01")
_PROVIDER = "manual_bank"


async def create_bank_claim(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: float,
    platform_account_id: uuid.UUID | None,
    reference: str | None,
    sender_name: str | None,
    idempotency_key: str | None,
) -> Payment:
    if idempotency_key:
        existing = (
            await session.execute(
                select(Payment).where(Payment.idempotency_key == idempotency_key)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    amount_dec = decimal.Decimal(str(amount)).quantize(_CENTS)
    if amount_dec <= 0:
        raise AppError("INVALID_AMOUNT", "Deposit amount must be positive.", status_code=422)

    # Validate the target account exists + is active (if one was chosen).
    if platform_account_id is not None:
        acct = await session.get(PlatformBankAccount, platform_account_id)
        if acct is None or not acct.is_active:
            raise AppError("NOT_FOUND", "Selected bank account is unavailable.", status_code=404)

    payment = Payment(
        user_id=user_id,
        provider=_PROVIDER,
        amount=amount_dec,
        currency="USD",
        status="pending",
        purpose="deposit",
        payment_method="bank_transfer",
        idempotency_key=idempotency_key,
        raw_payload={
            "platform_account_id": str(platform_account_id) if platform_account_id else None,
            "reference": (reference or "").strip() or None,
            "sender_name": (sender_name or "").strip() or None,
        },
    )
    session.add(payment)
    await session.flush()
    await write_audit(
        session,
        action="deposit.bank_claim.created",
        entity_type="payment",
        entity_id=str(payment.id),
        actor_id=user_id,
        after={"amount": str(amount_dec)},
    )
    return payment


async def list_pending_for_admin(session: AsyncSession) -> list[tuple[Payment, str | None]]:
    """Pending manual bank-transfer claims (newest first), each with the claimant's email."""
    res = await session.execute(
        select(Payment, User.email)
        .join(User, User.id == Payment.user_id, isouter=True)
        .where(Payment.provider == _PROVIDER, Payment.status == "pending")
        .order_by(Payment.created_at.desc())
    )
    return [(row[0], row[1]) for row in res.all()]


async def admin_confirm(
    session: AsyncSession, *, payment_id: uuid.UUID, actor_id: uuid.UUID
) -> Payment:
    """Confirm a claim: credit the wallet (idempotent — guarded on status under FOR UPDATE)."""
    payment = (
        await session.execute(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
    ).scalar_one_or_none()
    if payment is None or payment.provider != _PROVIDER:
        raise AppError("NOT_FOUND", "Deposit claim not found.", status_code=404)
    if payment.status == "succeeded":
        return payment  # already credited
    if payment.status != "pending":
        raise AppError(
            "INVALID_TRANSITION", "Only a pending claim can be confirmed.", status_code=409
        )
    payment.status = "succeeded"
    payment.amount_captured = payment.amount
    payload = payment.raw_payload if isinstance(payment.raw_payload, dict) else {}
    ref = payload.get("reference")
    await wallet_service.credit(
        session,
        user_id=payment.user_id,
        amount=payment.amount,
        reference_id=payment.id,
        tx_type=TransactionType.deposit,
        payment_method=None,
        description=f"Bank transfer deposit{f' — ref {ref}' if ref else ''}",
        actor_id=actor_id,
    )
    await notification_service.notify(
        session,
        user_id=payment.user_id,
        type="wallet",
        title="Deposit confirmed",
        message=f"Your ${payment.amount} bank-transfer deposit has been credited to your wallet.",
    )
    await write_audit(
        session,
        action="deposit.bank_claim.confirmed",
        entity_type="payment",
        entity_id=str(payment.id),
        actor_id=actor_id,
        after={"amount": str(payment.amount)},
    )
    return payment


async def admin_reject(
    session: AsyncSession, *, payment_id: uuid.UUID, actor_id: uuid.UUID, reason: str | None
) -> Payment:
    payment = (
        await session.execute(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
    ).scalar_one_or_none()
    if payment is None or payment.provider != _PROVIDER:
        raise AppError("NOT_FOUND", "Deposit claim not found.", status_code=404)
    if payment.status != "pending":
        raise AppError(
            "INVALID_TRANSITION", "Only a pending claim can be rejected.", status_code=409
        )
    payment.status = "cancelled"
    payload = dict(payment.raw_payload) if isinstance(payment.raw_payload, dict) else {}
    payload["reject_reason"] = (reason or "Rejected by admin").strip()
    payment.raw_payload = payload
    await notification_service.notify(
        session,
        user_id=payment.user_id,
        type="wallet",
        title="Deposit claim rejected",
        message=(
            f"Your ${payment.amount} bank-transfer deposit claim was not confirmed. "
            f"{payload['reject_reason']}"
        ),
    )
    await write_audit(
        session,
        action="deposit.bank_claim.rejected",
        entity_type="payment",
        entity_id=str(payment.id),
        actor_id=actor_id,
        after={"reason": payload["reject_reason"]},
    )
    return payment
