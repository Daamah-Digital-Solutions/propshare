"""Broker routes (Phase 11) — referrals & commissions.

All endpoints require the admin-approved ``broker`` active role (DB re-checked at action
time). Brokers are read-only consumers here: they fetch their shareable code, their
dashboard stats, their referred-client list, and their commission ledger. Commission
accrual itself happens server-side inside the Phase-5/Phase-6 money flows — there is no
endpoint that mints a commission.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import Principal, SessionDep, require_active_role_db
from app.core.config import get_settings
from app.schemas.broker import (
    BrokerDashboardOut,
    CommissionItemOut,
    CommissionListOut,
    ReferralCodeOut,
    ReferralItemOut,
    ReferralListOut,
)
from app.services import broker_service

router = APIRouter(prefix="/api/v1/broker", tags=["broker"])

BrokerRoleDep = Annotated[Principal, Depends(require_active_role_db("broker"))]


@router.get("/referral-code", response_model=ReferralCodeOut)
async def referral_code(session: SessionDep, principal: BrokerRoleDep):
    code = await broker_service.get_or_create_code(session, principal.user_id)
    base = get_settings().app_base_url.rstrip("/")
    return ReferralCodeOut(code=code.code, share_link=f"{base}/auth?ref={code.code}")


@router.get("/dashboard", response_model=BrokerDashboardOut)
async def dashboard(session: SessionDep, principal: BrokerRoleDep):
    return BrokerDashboardOut(**await broker_service.dashboard(session, principal.user_id))


@router.get("/referrals", response_model=ReferralListOut)
async def referrals(session: SessionDep, principal: BrokerRoleDep):
    rows = await broker_service.list_referrals(session, principal.user_id)
    return ReferralListOut(items=[ReferralItemOut(**r) for r in rows], total=len(rows))


@router.get("/commissions", response_model=CommissionListOut)
async def commissions(
    session: SessionDep, principal: BrokerRoleDep, limit: int = 50, offset: int = 0
):
    items, total = await broker_service.list_commissions(
        session, principal.user_id, limit=limit, offset=offset
    )
    return CommissionListOut(items=[CommissionItemOut(**i) for i in items], total=total)
