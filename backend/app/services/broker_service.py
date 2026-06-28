"""Broker referrals & commissions (Phase 11).

A broker shares a code; a client who signs up with it is linked to the broker ONCE, at
signup only. The broker then earns a commission = ``broker_commission_pct`` × the
**platform revenue attributable to that client** (purchase platform fee + rental mgmt
fee) — NEVER a percent of the investment amount.

Design guarantees encoded here:
  * **Signup-only link** — :func:`resolve_signup_referral` is the ONLY writer of
    ``broker_referrals``. A client who signed up without a broker code can never be
    adopted later (no retroactive linking).
  * **Revenue-based, capped** — :func:`accrue_commission` is the single accrual engine.
    Commission = rate × actual platform revenue; the ``commission_amount <=
    revenue_amount`` DB CHECK makes overpayment structurally impossible.
  * **Idempotent** — one platform-revenue event (an ``investments.id`` or a
    ``distribution_items.id``) yields at most one accrual: SELECT-first guard inside the
    atomic tx + UNIQUE(revenue_event_type, revenue_event_id) backstop.
  * **Rate snapshot** — each accrual stores the rate it used, so an admin rate change
    never rewrites history.
  * **No commission on the generic path** — only ``broker_referrals`` (broker→client)
    accrues; the raw ``users.referred_by`` user→user attribution never does.
"""

from __future__ import annotations

import decimal
import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BrokerCode, BrokerCommission, BrokerReferral, Transaction, User
from app.models.base import TransactionType
from app.services import notification_service, settings_service, wallet_service

_CENTS = decimal.Decimal("0.01")
# Unambiguous alphabet (no 0/O/1/I) for human-friendly shareable codes.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LEN = 8

REVENUE_PLATFORM_FEE = "investment_platform_fee"  # Phase 5 — one-time at confirmation
REVENUE_MGMT_FEE = "distribution_mgmt_fee"  # Phase 6 — recurring while holding


def _q(value: decimal.Decimal) -> decimal.Decimal:
    return value.quantize(_CENTS, rounding=decimal.ROUND_HALF_UP)


def _new_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LEN))


# --- broker code ----------------------------------------------------------- #
async def get_or_create_code(session: AsyncSession, broker_id: uuid.UUID) -> BrokerCode:
    """Return the broker's shareable code, creating it on first request. One per broker
    (UNIQUE broker_id); the code is server-generated (the broker can't choose it)."""
    existing = (
        await session.execute(select(BrokerCode).where(BrokerCode.broker_id == broker_id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    code_str = _new_code()
    while await session.scalar(select(BrokerCode.id).where(BrokerCode.code == code_str)):
        code_str = _new_code()  # collision is astronomically unlikely; UNIQUE is the backstop
    code = BrokerCode(broker_id=broker_id, code=code_str)
    session.add(code)
    await session.flush()
    return code


# --- signup-only link ------------------------------------------------------ #
async def resolve_signup_referral(
    session: AsyncSession, *, new_user_id: uuid.UUID, referral_code: str | None
) -> uuid.UUID | None:
    """If ``referral_code`` is a broker code (and not the new user's own), create the
    immutable ``broker_referrals`` link and return the broker_id (so the caller can also
    set ``users.referred_by`` for attribution symmetry). Returns None otherwise — the
    caller then falls back to the generic user-UUID attribution path, which earns no
    commission. This runs ONLY on the signup path: brokers can never adopt existing
    clients retroactively."""
    if not referral_code:
        return None
    code = (
        await session.execute(
            select(BrokerCode).where(BrokerCode.code == referral_code.strip().upper())
        )
    ).scalar_one_or_none()
    if code is None or code.broker_id == new_user_id:
        return None
    session.add(BrokerReferral(broker_id=code.broker_id, client_id=new_user_id, code_id=code.id))
    return code.broker_id


async def referring_broker(session: AsyncSession, client_id: uuid.UUID) -> uuid.UUID | None:
    """The broker who referred this client, or None. Read-only; never creates a link."""
    return await session.scalar(
        select(BrokerReferral.broker_id).where(BrokerReferral.client_id == client_id)
    )


# --- accrual engine -------------------------------------------------------- #
async def accrue_commission(
    session: AsyncSession,
    *,
    client_id: uuid.UUID,
    revenue_event_type: str,
    revenue_event_id: uuid.UUID,
    revenue_amount: decimal.Decimal,
) -> BrokerCommission | None:
    """Accrue + credit a broker commission for ONE platform-revenue event from a
    referred client. No-op (returns None) when the client isn't broker-referred, the
    commission rounds to zero, or this exact revenue event already accrued.

    The caller MUST have locked the broker's wallet as part of its sorted-order union
    lock (``wallet_service.lock_wallets``) before invoking this, so the broker credit
    never violates the global wallet lock hierarchy.
    """
    referral = (
        await session.execute(select(BrokerReferral).where(BrokerReferral.client_id == client_id))
    ).scalar_one_or_none()
    if referral is None:
        return None  # not broker-referred (or generic/self-referral) — no commission

    # Idempotency: one revenue event -> at most one accrual (UNIQUE is the backstop).
    if await session.scalar(
        select(BrokerCommission.id).where(
            BrokerCommission.revenue_event_type == revenue_event_type,
            BrokerCommission.revenue_event_id == revenue_event_id,
        )
    ):
        return None

    rate = await settings_service.get_broker_commission_pct(session)
    commission = _q(revenue_amount * rate / decimal.Decimal(100))
    if commission <= 0:
        return None
    # Defensive cap (the DB CHECK is the hard guarantee): never exceed the revenue.
    if commission > revenue_amount:
        commission = _q(revenue_amount)

    await wallet_service.credit(
        session,
        user_id=referral.broker_id,
        amount=commission,
        reference_id=revenue_event_id,
        tx_type=TransactionType.referral_commission,
        description=f"Referral commission ({revenue_event_type})",
    )
    await session.flush()
    txn_id = await session.scalar(
        select(Transaction.id).where(
            Transaction.user_id == referral.broker_id,
            Transaction.reference_id == revenue_event_id,
            Transaction.type == TransactionType.referral_commission,
        )
    )
    row = BrokerCommission(
        broker_id=referral.broker_id,
        client_id=client_id,
        referral_id=referral.id,
        revenue_event_type=revenue_event_type,
        revenue_event_id=revenue_event_id,
        revenue_amount=_q(revenue_amount),
        commission_rate=rate,
        commission_amount=commission,
        transaction_id=txn_id,
    )
    session.add(row)
    await session.flush()
    # Phase 12: tell the broker they earned (was silent). In-app + email; written in the
    # same money tx via the outbox, sent out-of-tx by the drainer.
    await notification_service.notify(
        session,
        user_id=referral.broker_id,
        type="broker",
        title="Commission earned",
        message=f"You earned ${commission} in referral commission.",
        email_category="investment_updates",
    )
    return row


# --- reads (broker dashboard) ---------------------------------------------- #
async def dashboard(session: AsyncSession, broker_id: uuid.UUID) -> dict:
    rate = await settings_service.get_broker_commission_pct(session)
    total_referrals = (
        await session.scalar(
            select(func.count())
            .select_from(BrokerReferral)
            .where(BrokerReferral.broker_id == broker_id)
        )
    ) or 0
    total_commission = (
        await session.scalar(
            select(func.coalesce(func.sum(BrokerCommission.commission_amount), 0)).where(
                BrokerCommission.broker_id == broker_id
            )
        )
    ) or decimal.Decimal(0)
    return {
        "commission_rate": str(rate),
        "total_referrals": int(total_referrals),
        "total_commission": str(_q(decimal.Decimal(total_commission))),
    }


async def list_referrals(session: AsyncSession, broker_id: uuid.UUID) -> list[dict]:
    """Referred clients + each client's commission-to-date. Client identity is masked
    (privacy): only a masked email is exposed, never the raw account."""
    rows = (
        await session.execute(
            select(BrokerReferral, User.email)
            .join(User, User.id == BrokerReferral.client_id)
            .where(BrokerReferral.broker_id == broker_id)
            .order_by(BrokerReferral.created_at.desc())
        )
    ).all()
    out = []
    for ref, email in rows:
        earned = (
            await session.scalar(
                select(func.coalesce(func.sum(BrokerCommission.commission_amount), 0)).where(
                    BrokerCommission.client_id == ref.client_id,
                    BrokerCommission.broker_id == broker_id,
                )
            )
        ) or decimal.Decimal(0)
        out.append(
            {
                "referral_id": str(ref.id),
                "client_masked": _mask_email(email),
                "created_at": ref.created_at.isoformat(),
                "commission_to_date": str(_q(decimal.Decimal(earned))),
            }
        )
    return out


async def list_commissions(
    session: AsyncSession, broker_id: uuid.UUID, *, limit: int = 50, offset: int = 0
) -> tuple[list[dict], int]:
    total = (
        await session.scalar(
            select(func.count())
            .select_from(BrokerCommission)
            .where(BrokerCommission.broker_id == broker_id)
        )
    ) or 0
    rows = (
        (
            await session.execute(
                select(BrokerCommission)
                .where(BrokerCommission.broker_id == broker_id)
                .order_by(BrokerCommission.created_at.desc())
                .limit(min(limit, 200))
                .offset(max(offset, 0))
            )
        )
        .scalars()
        .all()
    )
    items = [
        {
            "id": str(r.id),
            "revenue_event_type": r.revenue_event_type,
            "revenue_amount": str(r.revenue_amount),
            "commission_rate": str(r.commission_rate),
            "commission_amount": str(r.commission_amount),
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
    return items, int(total)


def _mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return "client"
    local, _, domain = email.partition("@")
    head = local[0] if local else "?"
    return f"{head}***@{domain}"
