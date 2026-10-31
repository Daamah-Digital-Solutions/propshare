"""Transfers: property units or wallet balance to another person (client, 2026-10-28).

  GET  /api/v1/transfers               the caller's transfers (sent, and delivered to them)
  GET  /api/v1/transfers/options       what they can send: free units per property, balance,
                                       the fee rate and the rules
  POST /api/v1/transfers/quote         the review step: what will be held and sent, and the fee
  POST /api/v1/transfers               send it (Idempotency-Key): held at once, delivered now
                                       when due and the recipient is verified
  POST /api/v1/transfers/{id}/cancel   take back one not delivered yet (everything returns)

Sending is for investors with a confirmed email and verified identity (checked again in the
service). See transfer_service.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import KycVerifiedDep, PrincipalDep, SessionDep, require_active_role_db
from app.core.ratelimit import TRANSFER_LIMIT, limiter
from app.schemas.transfers import (
    TransferIn,
    TransferListOut,
    TransferOptionsOut,
    TransferOut,
    TransferQuoteOut,
)
from app.services import transfer_service

router = APIRouter(prefix="/api/v1/transfers", tags=["transfers"])

InvestorDep = Annotated[object, Depends(require_active_role_db("investor"))]


@router.get("", response_model=TransferListOut)
async def my_transfers(session: SessionDep, principal: PrincipalDep):
    return TransferListOut(items=await transfer_service.list_for_user(session, principal.user_id))


@router.get("/options", response_model=TransferOptionsOut)
async def options(session: SessionDep, principal: PrincipalDep, _investor: InvestorDep):
    return TransferOptionsOut(**await transfer_service.options(session, principal.user_id))


@router.post("/quote", response_model=TransferQuoteOut)
async def quote(
    body: TransferIn, session: SessionDep, principal: KycVerifiedDep, _investor: InvestorDep
):
    out = await transfer_service.quote(session, sender_id=principal.user_id, data=body.model_dump())
    return TransferQuoteOut(**out)


@router.post("", response_model=TransferOut, status_code=201)
@limiter.limit(TRANSFER_LIMIT)
async def send(
    request: Request,
    body: TransferIn,
    session: SessionDep,
    principal: KycVerifiedDep,
    _investor: InvestorDep,
):
    out = await transfer_service.create(
        session,
        sender_id=principal.user_id,
        data=body.model_dump(),
        idempotency_key=request.headers.get("Idempotency-Key") or "",
    )
    return TransferOut(**out)


@router.post("/{transfer_id}/cancel", response_model=TransferOut)
async def cancel(transfer_id: uuid.UUID, session: SessionDep, principal: PrincipalDep):
    out = await transfer_service.cancel(
        session, sender_id=principal.user_id, transfer_id=transfer_id
    )
    return TransferOut(**out)
