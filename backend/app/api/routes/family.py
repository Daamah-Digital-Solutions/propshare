"""Family groups & gifting routes (Phase 10).

Owner (a KYC'd investor) manages a family group: members (incl. invite), allocate/
transfer REAL units, allocate returns, reinvest at the family discount. Unit-/money-
moving actions are KYC-gated + Idempotency-Key. The owner is the group's first member.

- POST /family/groups                 create the caller's group (one per owner).
- GET  /family/groups/me              the group + members (+ live real/pending units).
- POST /family/members                add a member (links if a KYC'd user exists).
- POST /family/transfers              allocate/transfer units (real or pending).
- POST /family/transfers/{id}/cancel  cancel a pending allocation.
- POST /family/allocations            allocate returns ($) to a member.
- POST /family/reinvest               reinvest at the family discount.
- POST /family/materialize            pull the caller's own pending allocations (after KYC).
- GET  /family/transfers              transfer history.
- GET  /family/settings               discount + transfer-fee knobs.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import KycVerifiedDep, PrincipalDep, SessionDep
from app.core.errors import AppError
from app.models.identity import User
from app.schemas.family import (
    AllocateReturnsIn,
    FamilySettingsOut,
    GroupCreateIn,
    GroupOut,
    MemberCreateIn,
    MemberOut,
    ReinvestIn,
    TransferCreateIn,
    TransferListOut,
    TransferOut,
)
from app.services import family_service, settings_service

router = APIRouter(prefix="/api/v1/family", tags=["family"])


def _idem(request: Request) -> str:
    key = request.headers.get("Idempotency-Key")
    if not key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED", "An Idempotency-Key header is required.", status_code=400
        )
    return key


@router.post("/groups", response_model=GroupOut)
async def create_group(body: GroupCreateIn, session: SessionDep, principal: KycVerifiedDep):
    email = await session.scalar(select(User.email).where(User.id == principal.user_id))
    await family_service.get_or_create_group(
        session, owner_id=principal.user_id, owner_email=email, name=body.name
    )
    view = await family_service.get_group_view(session, principal.user_id)
    return GroupOut(**view)  # type: ignore[arg-type]


@router.get("/groups/me", response_model=GroupOut | None)
async def my_group(session: SessionDep, principal: PrincipalDep):
    view = await family_service.get_group_view(session, principal.user_id)
    return GroupOut(**view) if view else None


@router.post("/members", response_model=MemberOut)
async def add_member(body: MemberCreateIn, session: SessionDep, principal: KycVerifiedDep):
    result = await family_service.add_member(
        session,
        owner_id=principal.user_id,
        name=body.name,
        email=str(body.email) if body.email else None,
        relationship=body.relationship,
    )
    return MemberOut(**result)


@router.post("/transfers", response_model=TransferOut)
async def create_transfer(
    body: TransferCreateIn, request: Request, session: SessionDep, principal: KycVerifiedDep
):
    result = await family_service.create_transfer(
        session,
        owner_id=principal.user_id,
        from_member_id=body.from_member_id,
        to_member_id=body.to_member_id,
        property_id=body.property_id,
        units=body.units,
        idempotency_key=_idem(request),
    )
    return TransferOut(**result)


@router.post("/transfers/{transfer_id}/cancel", response_model=TransferOut)
async def cancel_transfer(transfer_id: uuid.UUID, session: SessionDep, principal: KycVerifiedDep):
    result = await family_service.cancel_transfer(
        session, owner_id=principal.user_id, transfer_id=transfer_id
    )
    return TransferOut(**result)


@router.post("/allocations")
async def allocate_returns(
    body: AllocateReturnsIn, request: Request, session: SessionDep, principal: KycVerifiedDep
) -> dict:
    return await family_service.allocate_returns(
        session,
        owner_id=principal.user_id,
        member_id=body.member_id,
        amount=body.amount,
        idempotency_key=_idem(request),
    )


@router.post("/reinvest")
async def reinvest(
    body: ReinvestIn, request: Request, session: SessionDep, principal: KycVerifiedDep
) -> dict:
    return await family_service.reinvest(
        session,
        owner_id=principal.user_id,
        property_id=body.property_id,
        amount=body.amount,
        idempotency_key=_idem(request),
    )


@router.post("/materialize")
async def materialize(session: SessionDep, principal: KycVerifiedDep) -> dict:
    count = await family_service.materialize_for_user(session, user_id=principal.user_id)
    return {"materialized": count}


@router.get("/transfers", response_model=TransferListOut)
async def list_transfers(session: SessionDep, principal: PrincipalDep):
    rows = await family_service.list_transfers(session, principal.user_id)
    return TransferListOut(items=[TransferOut(**t) for t in rows], total=len(rows))


@router.get("/settings", response_model=FamilySettingsOut)
async def family_settings(session: SessionDep, principal: PrincipalDep):
    sett = await settings_service.get_family_settings(session)
    return FamilySettingsOut(
        reinvest_discount_pct=str(sett["reinvest_discount_pct"]),
        transfer_fee_pct=str(sett["transfer_fee_pct"]),
    )
