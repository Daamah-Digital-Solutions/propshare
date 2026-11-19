"""Admin installment maintenance (Group 6) — the due-payment executor.

POST /admin/installments/run-due  send due-soon reminders, then charge due installments from
                                  the wallet (progressive vesting). A payment that can't be
                                  charged is marked overdue + the investor notified (grace, no
                                  forfeit); retried next run. Cron target (admin OR
                                  X-Cron-Secret); idempotent (SKIP LOCKED + status guards).
                                  The same hourly run reminds the admins of under-construction
                                  listings whose quarterly valuation is due (valuation_service).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.api.deps import AdminOrCronDep, SessionDep
from app.schemas.installments import InstallmentRunOut
from app.services import installment_service, valuation_service

log = logging.getLogger("capimax.installments")

router = APIRouter(prefix="/api/v1/admin/installments", tags=["admin"])


@router.post("/run-due", response_model=InstallmentRunOut)
async def run_due(session: SessionDep, caller: AdminOrCronDep) -> InstallmentRunOut:
    result = await installment_service.run_due(session)
    reminders = 0
    try:
        async with session.begin_nested():
            reminders = await valuation_service.remind_due(session)
    except Exception:  # noqa: BLE001 — a reminder never stops the installment run
        log.exception("quarterly valuation reminders failed")
    return InstallmentRunOut(**result, valuation_reminders=reminders)
