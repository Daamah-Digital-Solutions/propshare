"""Admin KYC routes (Phase 2) — the EXCEPTION path only.

Lists applicants the provider flagged for manual review and lets an admin
approve/reject them. The default verification path is fully automatic (the
Sumsub webhook); this exists solely for provider-flagged edge cases.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import AdminDep, SessionDep
from app.models import KycVerification
from app.schemas.kyc import AdminKycDecisionIn, AdminKycOut
from app.services import kyc_service

router = APIRouter(prefix="/api/v1/admin/kyc", tags=["admin"])


@router.get("", response_model=list[AdminKycOut])
async def list_review_queue(session: SessionDep, _admin: AdminDep, review_only: bool = True):
    stmt = select(KycVerification)
    if review_only:
        stmt = stmt.where(KycVerification.manual_review_required.is_(True))
    stmt = stmt.order_by(KycVerification.submitted_at.asc())
    rows = (await session.execute(stmt)).scalars().all()
    return [
        AdminKycOut(
            user_id=r.user_id,
            status=str(r.status),
            manual_review_required=r.manual_review_required,
            last_review_answer=r.last_review_answer,
            submitted_at=r.submitted_at,
            rejection_reason=r.rejection_reason,
        )
        for r in rows
    ]


@router.post("/{user_id}/decision", response_model=AdminKycOut)
async def decide(
    user_id: uuid.UUID, body: AdminKycDecisionIn, session: SessionDep, admin: AdminDep
):
    kyc = await kyc_service.admin_decide(
        session,
        user_id=user_id,
        approve=body.approve,
        actor_id=admin.user_id,
        reason=body.reason,
    )
    return AdminKycOut(
        user_id=kyc.user_id,
        status=str(kyc.status),
        manual_review_required=kyc.manual_review_required,
        last_review_answer=kyc.last_review_answer,
        submitted_at=kyc.submitted_at,
        rejection_reason=kyc.rejection_reason,
    )
