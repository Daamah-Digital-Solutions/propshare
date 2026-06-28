"""Admin LP maintenance (Phase 13) — the exit-request expiry sweep.

POST /admin/liquidity/expire-requests  flip lapsed `open` exit requests to `expired`
                                       so their units stop being reserved across both
                                       markets. Cron target (admin OR X-Cron-Secret);
                                       idempotent (SKIP LOCKED).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminOrCronDep, SessionDep
from app.services import liquidity_service

router = APIRouter(prefix="/api/v1/admin/liquidity", tags=["admin"])


@router.post("/expire-requests")
async def expire_requests(session: SessionDep, caller: AdminOrCronDep) -> dict:
    count = await liquidity_service.expire_open_requests(session)
    return {"expired": count}
