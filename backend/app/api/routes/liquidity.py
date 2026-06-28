"""Liquidity-provider routes (Phase 9) — ACTIVE rail.

Seller side (instant-buyout exit requests):
- POST /liquidity/exit-requests            list an instant exit (KYC-gated).
- GET  /liquidity/exit-requests            the open order book.
- GET  /liquidity/exit-requests/mine       the seller's own requests.
- POST /liquidity/exit-requests/{id}/cancel  cancel an open request.

LP side:
- POST /liquidity/exit-requests/{id}/fund  fund a request (KYC + liquidity_provider
                                           role + Idempotency-Key; atomic buyback).
- GET  /liquidity/positions                the LP's ACTIVE acquisition history (audit).
- GET  /liquidity/holdings                 the LP's CURRENT holdings (ownership_ledger).
- GET  /liquidity/settings                 discount/fee/ttl/band + PASSIVE flag + tiers.

The PASSIVE pool is intentionally absent here — its engine ships behind a hard lock in
a later step. Pricing is server-authoritative; the seller payout is snapshot-locked.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.deps import KycVerifiedDep, Principal, PrincipalDep, SessionDep, require_active_role_db
from app.core.errors import AppError
from app.models import LpPoolTier
from app.schemas.liquidity import (
    CancelOut,
    ExitRequestCreateIn,
    ExitRequestListOut,
    ExitRequestOut,
    FundIn,
    LiquiditySettingsOut,
    PoolTierOut,
    PositionListOut,
    PositionOut,
)
from app.schemas.secondary import HoldingListOut, HoldingOut
from app.services import liquidity_service, secondary_service, settings_service

router = APIRouter(prefix="/api/v1/liquidity", tags=["liquidity"])

# Funding an exit request requires the liquidity_provider active role (DB re-checked).
LpRoleDep = Annotated[Principal, Depends(require_active_role_db("liquidity_provider"))]


@router.post("/exit-requests", response_model=ExitRequestOut)
async def create_exit_request(
    body: ExitRequestCreateIn, request: Request, session: SessionDep, principal: KycVerifiedDep
):
    result = await liquidity_service.create_exit_request(
        session,
        seller_id=principal.user_id,
        property_id=body.property_id,
        units=body.units,
        idempotency_key=request.headers.get("Idempotency-Key"),
    )
    return ExitRequestOut(**result)


@router.get("/exit-requests", response_model=ExitRequestListOut)
async def open_requests(
    session: SessionDep, principal: PrincipalDep, property_id: uuid.UUID | None = None
):
    rows = await liquidity_service.list_open_requests(session, property_id=property_id)
    return ExitRequestListOut(items=[ExitRequestOut(**r) for r in rows], total=len(rows))


@router.get("/exit-requests/mine", response_model=ExitRequestListOut)
async def my_requests(session: SessionDep, principal: PrincipalDep):
    rows = await liquidity_service.list_my_exit_requests(session, principal.user_id)
    return ExitRequestListOut(items=[ExitRequestOut(**r) for r in rows], total=len(rows))


@router.post("/exit-requests/{request_id}/cancel", response_model=CancelOut)
async def cancel_request(request_id: uuid.UUID, session: SessionDep, principal: PrincipalDep):
    result = await liquidity_service.cancel_exit_request(
        session, seller_id=principal.user_id, request_id=request_id
    )
    return CancelOut(**result)


@router.post("/exit-requests/{request_id}/fund", response_model=PositionOut)
async def fund_request(
    request_id: uuid.UUID,
    body: FundIn,
    request: Request,
    session: SessionDep,
    principal: KycVerifiedDep,
    _lp: LpRoleDep,
):
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "An Idempotency-Key header is required to fund a request.",
            status_code=400,
        )
    result = await liquidity_service.fund_exit_request(
        session,
        lp_user_id=principal.user_id,
        request_id=request_id,
        units=body.units,
        idempotency_key=idempotency_key,
    )
    return PositionOut(**result)


@router.get("/positions", response_model=PositionListOut)
async def my_positions(session: SessionDep, principal: PrincipalDep):
    rows = await liquidity_service.list_my_positions(session, principal.user_id)
    return PositionListOut(items=[PositionOut(**r) for r in rows], total=len(rows))


@router.get("/holdings", response_model=HoldingListOut)
async def my_holdings(session: SessionDep, principal: PrincipalDep):
    """Current LP holdings — the source of truth is ownership_ledger (NOT position rows)."""
    rows = await secondary_service.my_holdings(session, principal.user_id)
    return HoldingListOut(items=[HoldingOut(**r) for r in rows], total=len(rows))


@router.get("/settings", response_model=LiquiditySettingsOut)
async def liquidity_settings(session: SessionDep, principal: PrincipalDep):
    sett = await settings_service.get_liquidity_settings(session)
    tiers = (
        (
            await session.execute(
                select(LpPoolTier)
                .where(LpPoolTier.active.is_(True))
                .order_by(LpPoolTier.period_months)
            )
        )
        .scalars()
        .all()
    )
    return LiquiditySettingsOut(
        discount_pct=str(sett["discount_pct"]),
        fee_pct=str(sett["fee_pct"]),
        ttl_minutes=int(sett["ttl_minutes"]),
        band_pct=str(sett["band_pct"]),
        passive_enabled=bool(sett["passive_enabled"]),
        tiers=[
            PoolTierOut(
                period_months=t.period_months,
                apy_pct=str(t.apy_pct),
                min_amount=str(t.min_amount),
            )
            for t in tiers
        ],
    )
