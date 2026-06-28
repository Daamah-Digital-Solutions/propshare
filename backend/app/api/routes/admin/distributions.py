"""Admin distribution trigger (Phase 6).

POST /api/v1/admin/properties/{id}/distributions — run a pro-rata return
distribution for a property + period. Admin-gated (action-time DB re-check),
idempotent (a period can be distributed at most once → 409 DISTRIBUTION_EXISTS).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.api.deps import AdminDep, SessionDep
from app.core.errors import AppError
from app.schemas.distribution import DistributionRunIn, DistributionRunOut
from app.services import distribution_service

router = APIRouter(prefix="/api/v1/admin/properties", tags=["admin"])


@router.post("/{prop_id}/distributions", response_model=DistributionRunOut)
async def run_distribution(
    prop_id: uuid.UUID,
    body: DistributionRunIn,
    request: Request,
    session: SessionDep,
    admin: AdminDep,
):
    if body.gross_pool <= 0:
        raise AppError("INVALID_AMOUNT", "gross_pool must be positive.", status_code=422)
    import decimal

    result = await distribution_service.run_distribution(
        session,
        property_id=prop_id,
        kind=body.kind,
        period_key=body.period_key,
        period_start=body.period_start,
        period_end=body.period_end,
        gross_pool=decimal.Decimal(str(body.gross_pool)),
        created_by=admin.user_id,
        idempotency_key=request.headers.get("Idempotency-Key"),
    )
    return DistributionRunOut(**result)
