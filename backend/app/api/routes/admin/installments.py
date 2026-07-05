"""Admin installment maintenance (Group 6) — the due-payment executor.

POST /admin/installments/run-due  send due-soon reminders, then charge due installments from
                                  the wallet (progressive vesting). A payment that can't be
                                  charged is marked overdue + the investor notified (grace, no
                                  forfeit); retried next run. Cron target (admin OR
                                  X-Cron-Secret); idempotent (SKIP LOCKED + status guards).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminOrCronDep, SessionDep
from app.schemas.installments import InstallmentRunOut
from app.services import installment_service

router = APIRouter(prefix="/api/v1/admin/installments", tags=["admin"])


@router.post("/run-due", response_model=InstallmentRunOut)
async def run_due(session: SessionDep, caller: AdminOrCronDep) -> InstallmentRunOut:
    return InstallmentRunOut(**await installment_service.run_due(session))
