"""Withdrawal engine (Phase 7) — money LEAVES the platform here.

Safeguards (there is no auto-reversing webhook for a wrong send):
  * **Hold-on-request**: funds are debited to ``pending_balance`` atomically; the
    provider is NEVER called inside the request transaction.
  * **Three double-pay guards**: ``withdrawals.idempotency_key`` UNIQUE (request
    replay), the **provider idempotency key = withdrawal.id** (a retried submit can't
    send twice), and a **status-transition guard under FOR UPDATE** (executor only
    acts on ``approved``; webhook only settles ``processing``).
  * **Settlement only via signed webhook**, deduped on ``payout_events``.
  * **Failure/return → idempotent compensating credit** (funds returned, never lost).
  * **Reconciliation sweep** re-queries the provider for stuck ``processing`` rows.

Threshold: ``withdrawal_auto_approve_limit`` (platform_settings, default $5000). ≤ limit
auto-approves; above it goes to the admin review queue.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import ConnectAccount, PayoutEvent, Withdrawal
from app.models.identity import User
from app.services import (
    connect_service,
    notification_service,
    payout_methods_service,
    settings_service,
    wallet_service,
)
from app.services.integrations.payments import nowpayments_gateway, stripe_gateway

_CENTS = decimal.Decimal("0.01")
_PROVIDER_FOR_METHOD = {"bank": "stripe", "crypto": "nowpayments"}
RECONCILE_AFTER = dt.timedelta(hours=24)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _provider_configured(method: str) -> bool:
    return (
        stripe_gateway.connect_configured()
        if method == "bank"
        else nowpayments_gateway.payout_configured()
    )


async def _manual_enabled(session: AsyncSession) -> bool:
    """Manual mode (owner default): withdrawals are settled by hand by an admin — no Stripe
    Connect / NOWPayments payout. Held on request, then admin mark-paid / reject."""
    raw = await settings_service.get_setting(session, "manual_payouts_enabled")
    return (raw or "true").strip().lower() in ("true", "1", "yes", "on")


async def _auto_limit(session: AsyncSession) -> decimal.Decimal:
    raw = await settings_service.get_setting(session, "withdrawal_auto_approve_limit")
    try:
        return decimal.Decimal(raw)
    except (decimal.InvalidOperation, TypeError):
        return decimal.Decimal("5000")


# --- request (hold) -------------------------------------------------------- #
async def request_withdrawal(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: float,
    method: str,
    address: str | None,
    idempotency_key: str,
    user_email: str,
    payout_method_id: uuid.UUID | None = None,
) -> dict:
    if method not in _PROVIDER_FOR_METHOD:
        raise AppError("INVALID_METHOD", "method must be 'bank' or 'crypto'.", status_code=422)

    # Idempotency-Key replay -> return the existing withdrawal (no second hold).
    existing = (
        await session.execute(
            select(Withdrawal).where(Withdrawal.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _result(existing)

    manual = await _manual_enabled(session)
    provider = "manual" if manual else _PROVIDER_FOR_METHOD[method]

    if not manual and not _provider_configured(method):
        raise AppError(
            "PAYOUTS_NOT_CONFIGURED", f"{provider} payouts are not configured yet.", status_code=503
        )

    amount_dec = decimal.Decimal(str(amount)).quantize(_CENTS)
    if amount_dec <= 0:
        raise AppError("INVALID_AMOUNT", "Withdrawal amount must be positive.", status_code=422)

    if manual:
        # Snapshot the chosen saved destination; ALL manual payouts wait for the admin.
        destination = await _resolve_manual_destination(
            session, user_id, method, payout_method_id, address
        )
        status = "pending_review"
    else:
        destination = await _resolve_destination(session, user_id, method, address)
        limit = await _auto_limit(session)
        status = "approved" if amount_dec <= limit else "pending_review"

    wd = Withdrawal(
        user_id=user_id,
        amount=amount_dec,
        method=method,
        provider=provider,
        destination=destination,
        status=status,
        idempotency_key=idempotency_key,
    )
    session.add(wd)
    await session.flush()  # assign wd.id

    # Hold the funds (debit spendable -> pending_balance). Over-balance -> 422 and the
    # whole request rolls back (no withdrawal row left behind).
    await wallet_service.hold_for_withdrawal(
        session, user_id=user_id, amount=amount_dec, reference_id=wd.id, actor_id=user_id
    )
    await write_audit(
        session,
        action="withdrawal.requested",
        entity_type="withdrawal",
        entity_id=str(wd.id),
        actor_id=user_id,
        after={"amount": str(amount_dec), "method": method, "status": status, "provider": provider},
    )
    if status == "pending_review":
        await notification_service.notify(
            session,
            user_id=user_id,
            type="withdrawal",
            title="Withdrawal requested" if manual else "Withdrawal under review",
            message=(
                f"Your ${amount_dec} withdrawal request has been received and is being processed."
                if manual
                else f"Your ${amount_dec} withdrawal is over the auto-approve limit "
                "and is being reviewed."
            ),
        )
    return _result(wd)


async def _resolve_destination(
    session: AsyncSession, user_id: uuid.UUID, method: str, address: str | None
) -> dict:
    if method == "crypto":
        if not address:
            raise AppError("ADDRESS_REQUIRED", "A payout address is required.", status_code=422)
        return {"address": address}  # tokenized: the address only
    # bank -> require a payouts-enabled Connect account
    acct: ConnectAccount | None = await connect_service.get_account(session, user_id)
    if acct is None or not acct.payouts_enabled or not acct.stripe_account_id:
        raise AppError(
            "CONNECT_NOT_READY",
            "Link your bank (complete Stripe onboarding) before withdrawing to bank.",
            status_code=409,
        )
    return {"connect_account_id": acct.stripe_account_id}  # tokenized: account id only


async def _resolve_manual_destination(
    session: AsyncSession,
    user_id: uuid.UUID,
    method: str,
    payout_method_id: uuid.UUID | None,
    address: str | None,
) -> dict:
    """Snapshot the chosen saved destination onto the withdrawal so an admin can pay it out
    by hand: bank -> a saved UserBankAccount; crypto -> a saved UserCryptoWallet (or, as a
    fallback, an inline address). Raise NO_PAYOUT_METHOD if the user has nothing saved."""
    if method == "bank":
        if payout_method_id is not None:
            acct = await payout_methods_service.get_bank_account(
                session, user_id, payout_method_id
            )
        else:
            accts = await payout_methods_service.list_bank_accounts(session, user_id)
            acct = next((a for a in accts if a.is_default), accts[0] if accts else None)
        if acct is None:
            raise AppError(
                "NO_PAYOUT_METHOD",
                "Add a bank account before withdrawing to bank.",
                status_code=409,
            )
        return {
            "type": "bank",
            "label": acct.label,
            "account_holder": acct.account_holder,
            "bank_name": acct.bank_name,
            "iban": acct.iban,
            "account_number": acct.account_number,
            "swift_bic": acct.swift_bic,
            "country": acct.country,
            "currency": acct.currency,
        }
    # crypto
    if payout_method_id is not None:
        w = await payout_methods_service.get_crypto_wallet(session, user_id, payout_method_id)
        return {"type": "crypto", "label": w.label, "network": w.network, "address": w.address}
    if address and address.strip():
        return {"type": "crypto", "network": None, "address": address.strip()}
    wallets = await payout_methods_service.list_crypto_wallets(session, user_id)
    default = next((w for w in wallets if w.is_default), wallets[0] if wallets else None)
    if default is None:
        raise AppError(
            "NO_PAYOUT_METHOD",
            "Add a crypto wallet before withdrawing to crypto.",
            status_code=409,
        )
    return {
        "type": "crypto",
        "label": default.label,
        "network": default.network,
        "address": default.address,
    }


# --- executor (provider call, AFTER commit of the request) ----------------- #
async def execute_approved(session: AsyncSession, *, limit: int = 50) -> int:
    """Submit approved withdrawals to the provider, idempotently. Cron/admin-triggered.
    Each provider call uses idempotency key = withdrawal.id (no double-send on retry)."""
    rows = (
        (
            await session.execute(
                select(Withdrawal)
                .where(Withdrawal.status == "approved")
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    processed = 0
    for wd in rows:
        dest = wd.destination if isinstance(wd.destination, dict) else {}
        try:
            if wd.provider == "stripe":
                result = await stripe_gateway.create_payout(
                    withdrawal_id=wd.id,
                    account_id=str(dest.get("connect_account_id")),
                    amount=wd.amount,
                    currency="usd",
                    idempotency_key=str(wd.id),
                )
            else:
                result = await nowpayments_gateway.create_payout(
                    withdrawal_id=wd.id,
                    address=str(dest.get("address")),
                    amount=wd.amount,
                    currency="usd",
                    idempotency_key=str(wd.id),
                )
            wd.provider_payout_id = result.provider_payout_id
            wd.status = "processing"
            wd.updated_at = _utcnow()
            await write_audit(
                session,
                action="withdrawal.submitted",
                entity_type="withdrawal",
                entity_id=str(wd.id),
                after={"provider_payout_id": wd.provider_payout_id},
            )
        except AppError as exc:
            # Submission failed -> return funds, mark failed (idempotent compensating credit).
            wd.status = "failed"
            wd.failure_reason = exc.message
            await wallet_service.release_hold(
                session,
                user_id=wd.user_id,
                amount=wd.amount,
                reference_id=wd.id,
                reason="payout submit failed",
            )
            await write_audit(
                session,
                action="withdrawal.submit_failed",
                entity_type="withdrawal",
                entity_id=str(wd.id),
                after={"reason": exc.message},
            )
        processed += 1
    return processed


# --- admin review ---------------------------------------------------------- #
async def admin_review(
    session: AsyncSession,
    *,
    withdrawal_id: uuid.UUID,
    approve: bool,
    actor_id: uuid.UUID | None,
    reason: str | None = None,
) -> Withdrawal:
    wd = (
        await session.execute(
            select(Withdrawal).where(Withdrawal.id == withdrawal_id).with_for_update()
        )
    ).scalar_one_or_none()
    if wd is None:
        raise AppError("NOT_FOUND", "Withdrawal not found", status_code=404)
    if wd.status != "pending_review":
        raise AppError(
            "INVALID_TRANSITION",
            "Only a pending-review withdrawal can be decided.",
            status_code=409,
        )
    wd.reviewed_by = actor_id
    wd.reviewed_at = _utcnow()
    if approve:
        wd.status = "approved"  # executor will submit it
        action = "withdrawal.approved"
    else:
        wd.status = "rejected"
        wd.failure_reason = reason or "Rejected by reviewer"
        await wallet_service.release_hold(
            session,
            user_id=wd.user_id,
            amount=wd.amount,
            reference_id=wd.id,
            reason="review rejected",
            actor_id=actor_id,
        )
        action = "withdrawal.rejected"
    await write_audit(
        session,
        action=action,
        entity_type="withdrawal",
        entity_id=str(wd.id),
        actor_id=actor_id,
        after={"status": wd.status, "reason": reason},
    )
    return wd


async def admin_mark_paid(
    session: AsyncSession,
    *,
    withdrawal_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    reference: str | None = None,
    note: str | None = None,
) -> Withdrawal:
    """Manual settlement — an admin sent the money by hand: clear the hold + complete.
    Idempotent (a completed row is returned untouched); guards the transition under the row
    lock so a double-click can't settle twice."""
    wd = (
        await session.execute(
            select(Withdrawal).where(Withdrawal.id == withdrawal_id).with_for_update()
        )
    ).scalar_one_or_none()
    if wd is None:
        raise AppError("NOT_FOUND", "Withdrawal not found", status_code=404)
    if wd.status == "completed":
        return wd
    if wd.status not in ("pending_review", "approved"):
        raise AppError(
            "INVALID_TRANSITION",
            "Only a pending or approved withdrawal can be marked paid.",
            status_code=409,
        )
    wd.status = "completed"
    wd.completed_at = _utcnow()
    wd.reviewed_by = actor_id
    wd.reviewed_at = _utcnow()
    if reference and reference.strip():
        wd.provider_payout_id = reference.strip()
    if note and note.strip():
        dest = dict(wd.destination) if isinstance(wd.destination, dict) else {}
        dest["admin_note"] = note.strip()
        wd.destination = dest
    # Money has actually left: clear the in-flight hold (balance was already debited at request).
    await wallet_service.settle_withdrawal(
        session, user_id=wd.user_id, amount=wd.amount, reference_id=wd.id, actor_id=actor_id
    )
    await notification_service.notify(
        session,
        user_id=wd.user_id,
        type="withdrawal",
        title="Withdrawal sent",
        message=f"Your ${wd.amount} withdrawal has been paid out.",
        email_category="security",
    )
    await write_audit(
        session,
        action="withdrawal.marked_paid",
        entity_type="withdrawal",
        entity_id=str(wd.id),
        actor_id=actor_id,
        after={"status": "completed", "reference": reference},
    )
    return wd


async def list_for_admin(
    session: AsyncSession, *, status: str | None = None
) -> list[tuple[Withdrawal, str | None]]:
    """Withdrawals for the admin queue (optionally filtered by status), newest first, each
    paired with the requester's email."""
    q = select(Withdrawal, User.email).join(
        User, User.id == Withdrawal.user_id, isouter=True
    )
    if status:
        q = q.where(Withdrawal.status == status)
    q = q.order_by(Withdrawal.created_at.desc())
    res = await session.execute(q)
    return [(row[0], row[1]) for row in res.all()]


# --- webhook settlement ---------------------------------------------------- #
async def process_payout_webhook(
    session: AsyncSession, *, provider: str, raw_body: bytes, signature: str | None
) -> dict:
    parsed = (
        stripe_gateway.parse_payout_event(raw_body, signature)
        if provider == "stripe"
        else nowpayments_gateway.verify_payout_ipn(raw_body, signature)
    )

    # Connect onboarding status updates (Stripe account.updated).
    if parsed.kind == "account":
        if parsed.account_id:
            live = await stripe_gateway.get_account_status(parsed.account_id)
            await connect_service.update_from_webhook(
                session,
                account_id=parsed.account_id,
                payouts_enabled=live["payouts_enabled"],
                details_submitted=live["details_submitted"],
            )
        return {"status": "account_updated"}

    if parsed.kind != "payout" or parsed.status == "ignored":
        return {"status": "ignored"}

    # Dedupe layer: a replayed settlement webhook can't double-process.
    seen = await session.execute(
        select(PayoutEvent.id).where(
            PayoutEvent.provider == provider, PayoutEvent.event_id == parsed.event_id
        )
    )
    if seen.first() is not None:
        return {"status": "duplicate"}

    wd = await _locate(session, parsed)
    session.add(
        PayoutEvent(
            provider=provider,
            event_id=parsed.event_id,
            withdrawal_id=wd.id if wd else None,
            type=parsed.status,
        )
    )
    if wd is None:
        await write_audit(
            session,
            action="withdrawal.webhook.unmatched",
            entity_type="withdrawal",
            entity_id=parsed.provider_payout_id,
            after={"status": parsed.status},
        )
        return {"status": "ignored_unknown_withdrawal"}

    # Status-transition guard under the row lock (exactly-once).
    locked = (
        await session.execute(select(Withdrawal).where(Withdrawal.id == wd.id).with_for_update())
    ).scalar_one()

    if parsed.status == "settled":
        if locked.status == "completed":
            return {"status": "already_completed"}
        if locked.status not in ("processing", "approved"):
            return {"status": "ignored_state"}
        locked.status = "completed"
        locked.completed_at = _utcnow()
        await wallet_service.settle_withdrawal(
            session, user_id=locked.user_id, amount=locked.amount, reference_id=locked.id
        )
        await notification_service.notify(
            session,
            user_id=locked.user_id,
            type="withdrawal",
            title="Withdrawal sent",
            message=f"Your ${locked.amount} withdrawal has been paid out.",
            email_category="security",
        )
        await write_audit(
            session,
            action="withdrawal.completed",
            entity_type="withdrawal",
            entity_id=str(locked.id),
        )
        return {"status": "processed", "result": "completed"}

    # failed or returned -> release funds (idempotent: only from a live state).
    if locked.status in ("completed",) and parsed.status == "returned":
        return await _return(session, locked)
    if locked.status in ("processing", "approved") and parsed.status == "failed":
        return await _fail(session, locked, reason="payout failed")
    return {"status": "ignored_state"}


async def _fail(session: AsyncSession, wd: Withdrawal, *, reason: str) -> dict:
    wd.status = "failed"
    wd.failure_reason = reason
    await wallet_service.release_hold(
        session, user_id=wd.user_id, amount=wd.amount, reference_id=wd.id, reason=reason
    )
    await notification_service.notify(
        session,
        user_id=wd.user_id,
        type="withdrawal",
        title="Withdrawal returned",
        message=f"Your ${wd.amount} withdrawal could not be sent and was returned to your wallet.",
    )
    await write_audit(
        session, action="withdrawal.failed", entity_type="withdrawal", entity_id=str(wd.id)
    )
    return {"status": "processed", "result": "failed"}


async def _return(session: AsyncSession, wd: Withdrawal) -> dict:
    wd.status = "returned"
    wd.failure_reason = "payout returned by provider"
    await wallet_service.release_hold(
        session, user_id=wd.user_id, amount=wd.amount, reference_id=wd.id, reason="payout returned"
    )
    await write_audit(
        session, action="withdrawal.returned", entity_type="withdrawal", entity_id=str(wd.id)
    )
    return {"status": "processed", "result": "returned"}


async def _locate(session: AsyncSession, parsed) -> Withdrawal | None:
    if parsed.withdrawal_id:
        try:
            wid = uuid.UUID(str(parsed.withdrawal_id))
        except ValueError:
            wid = None
        if wid is not None:
            wd = await session.get(Withdrawal, wid)
            if wd is not None:
                return wd
    if parsed.provider_payout_id:
        return (
            await session.execute(
                select(Withdrawal).where(Withdrawal.provider_payout_id == parsed.provider_payout_id)
            )
        ).scalar_one_or_none()
    return None


# --- reconciliation sweep -------------------------------------------------- #
async def reconcile_processing(session: AsyncSession, *, now: dt.datetime | None = None) -> int:
    """Safety net: for withdrawals stuck in ``processing`` past the window, re-query the
    provider and settle/fail accordingly (the webhook may have been missed)."""
    cutoff = (now or _utcnow()) - RECONCILE_AFTER
    rows = (
        (
            await session.execute(
                select(Withdrawal).where(
                    Withdrawal.status == "processing", Withdrawal.updated_at < cutoff
                )
            )
        )
        .scalars()
        .all()
    )
    settled = 0
    for wd in rows:
        if not wd.provider_payout_id:
            continue
        if wd.provider == "stripe":
            state = await stripe_gateway.get_payout_status(wd.provider_payout_id)
        else:
            state = await nowpayments_gateway.get_payout_status(wd.provider_payout_id)
        locked = (
            await session.execute(
                select(Withdrawal).where(Withdrawal.id == wd.id).with_for_update()
            )
        ).scalar_one()
        if locked.status != "processing":
            continue
        if state == "settled":
            locked.status = "completed"
            locked.completed_at = _utcnow()
            await wallet_service.settle_withdrawal(
                session, user_id=locked.user_id, amount=locked.amount, reference_id=locked.id
            )
            await write_audit(
                session,
                action="withdrawal.reconciled_completed",
                entity_type="withdrawal",
                entity_id=str(locked.id),
            )
            settled += 1
        elif state == "failed":
            await _fail(session, locked, reason="reconcile: provider reported failed")
            settled += 1
    return settled


# --- reads ----------------------------------------------------------------- #
async def list_my_withdrawals(session: AsyncSession, user_id: uuid.UUID) -> list[Withdrawal]:
    res = await session.execute(
        select(Withdrawal)
        .where(Withdrawal.user_id == user_id)
        .order_by(Withdrawal.created_at.desc())
    )
    return list(res.scalars().all())


def _result(wd: Withdrawal) -> dict:
    return {
        "withdrawal_id": wd.id,
        "amount": str(wd.amount),
        "method": wd.method,
        "status": wd.status,
        "created_at": wd.created_at.isoformat() if wd.created_at else None,
    }
