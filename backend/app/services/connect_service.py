"""Stripe Connect onboarding (Phase 7, bank withdrawals).

Each investor onboards as a Stripe Express connected account; a bank payout is a
Transfer to that account. Bank withdrawals are gated on a payouts-enabled account.
We persist only the tokenized ``stripe_account_id`` + onboarding flags — never raw
bank PII (Stripe holds the bank details).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import ConnectAccount
from app.services.integrations.payments import stripe_gateway


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _status_for(payouts_enabled: bool, details_submitted: bool) -> str:
    if payouts_enabled:
        return "verified"
    if details_submitted:
        return "pending"
    return "pending"


async def get_account(session: AsyncSession, user_id: uuid.UUID) -> ConnectAccount | None:
    return (
        await session.execute(select(ConnectAccount).where(ConnectAccount.user_id == user_id))
    ).scalar_one_or_none()


async def start_onboarding(
    session: AsyncSession, *, user_id: uuid.UUID, email: str, refresh_url: str, return_url: str
) -> dict:
    """Create (or reuse) the connected account and return a fresh onboarding link."""
    if not stripe_gateway.connect_configured():
        raise AppError(
            "PAYOUTS_NOT_CONFIGURED", "Stripe Connect is not configured.", status_code=503
        )
    acct = await get_account(session, user_id)
    if acct is None:
        acct = ConnectAccount(user_id=user_id, status="none")
        session.add(acct)
        await session.flush()
    if not acct.stripe_account_id:
        acct.stripe_account_id = await stripe_gateway.create_connected_account(email)
        acct.status = "pending"
        await write_audit(
            session,
            action="connect.account_created",
            entity_type="connect_account",
            entity_id=str(acct.id),
            actor_id=user_id,
            after={"stripe_account_id": acct.stripe_account_id},
        )
    link = await stripe_gateway.create_account_link(
        acct.stripe_account_id, refresh_url=refresh_url, return_url=return_url
    )
    return {"onboarding_url": link, "account_id": acct.stripe_account_id, "status": acct.status}


async def refresh_status(session: AsyncSession, *, user_id: uuid.UUID) -> ConnectAccount:
    """Pull live status from Stripe and persist payouts_enabled/details_submitted."""
    acct = await get_account(session, user_id)
    if acct is None or not acct.stripe_account_id:
        raise AppError("CONNECT_NOT_STARTED", "No Connect account for this user.", status_code=404)
    live = await stripe_gateway.get_account_status(acct.stripe_account_id)
    _apply_status(acct, live["payouts_enabled"], live["details_submitted"])
    return acct


async def update_from_webhook(
    session: AsyncSession, *, account_id: str, payouts_enabled: bool, details_submitted: bool
) -> None:
    acct = (
        await session.execute(
            select(ConnectAccount).where(ConnectAccount.stripe_account_id == account_id)
        )
    ).scalar_one_or_none()
    if acct is None:
        return
    _apply_status(acct, payouts_enabled, details_submitted)


def _apply_status(acct: ConnectAccount, payouts_enabled: bool, details_submitted: bool) -> None:
    acct.payouts_enabled = payouts_enabled
    acct.details_submitted = details_submitted
    acct.status = _status_for(payouts_enabled, details_submitted)
    acct.updated_at = _utcnow()
