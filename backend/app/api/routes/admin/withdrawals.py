"""Admin withdrawal review + executor/reconcile triggers (Phase 7).

- POST /admin/withdrawals/{id}/approve  approve a pending-review withdrawal.
- POST /admin/withdrawals/{id}/reject   reject it -> funds released back to wallet.
- POST /admin/withdrawals/execute       submit approved withdrawals to the provider
                                         (cron target; idempotent).
- POST /admin/withdrawals/reconcile      re-query stuck `processing` payouts (cron).
All admin-gated (action-time DB re-check).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import AdminDep, AdminOrCronDep, SessionDep
from app.schemas.property import PropertyModerateIn
from app.services import withdrawal_service

router = APIRouter(prefix="/api/v1/admin/withdrawals", tags=["admin"])


@router.post("/{withdrawal_id}/approve")
async def approve(withdrawal_id: uuid.UUID, session: SessionDep, admin: AdminDep) -> dict:
    wd = await withdrawal_service.admin_review(
        session, withdrawal_id=withdrawal_id, approve=True, actor_id=admin.user_id
    )
    return {"id": str(wd.id), "status": wd.status}


@router.post("/{withdrawal_id}/reject")
async def reject(
    withdrawal_id: uuid.UUID, body: PropertyModerateIn, session: SessionDep, admin: AdminDep
) -> dict:
    wd = await withdrawal_service.admin_review(
        session,
        withdrawal_id=withdrawal_id,
        approve=False,
        actor_id=admin.user_id,
        reason=body.reason,
    )
    return {"id": str(wd.id), "status": wd.status}


@router.post("/execute")
async def execute(session: SessionDep, caller: AdminOrCronDep) -> dict:
    """Cron target (admin OR X-Cron-Secret). Submits approved payouts; idempotent."""
    count = await withdrawal_service.execute_approved(session)
    return {"submitted": count}


@router.post("/reconcile")
async def reconcile(session: SessionDep, caller: AdminOrCronDep) -> dict:
    """Cron target (admin OR X-Cron-Secret). Re-queries stuck processing payouts."""
    count = await withdrawal_service.reconcile_processing(session)
    return {"reconciled": count}
