"""Admin gifting maintenance (Group 5) — the scheduled-gift executor.

POST /admin/gifts/run-due  send due 7-day reminders, then execute due gifts on their date
                           (real atomic transfer / wallet credit; non-user recipient → pending
                           materializing on KYC; recurring → re-enqueue next occurrence).
                           Cron target (admin OR X-Cron-Secret); idempotent (SKIP LOCKED +
                           UNIQUE(series_id, scheduled_for)).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminOrCronDep, SessionDep
from app.schemas.gifts import GiftRunOut
from app.services import gift_service

router = APIRouter(prefix="/api/v1/admin/gifts", tags=["admin"])


@router.post("/run-due", response_model=GiftRunOut)
async def run_due(session: SessionDep, caller: AdminOrCronDep) -> GiftRunOut:
    return GiftRunOut(**await gift_service.run_due(session))
