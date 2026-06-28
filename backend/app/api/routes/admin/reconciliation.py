"""Admin reconciliation (Phase 13) — read-only DB-wide invariant drift report.

GET /admin/reconciliation  scan the whole DB for invariant drift (balance == Σ ledger,
                           pending == Σ non-terminal withdrawals, property unit accounting,
                           ownership non-negativity, family pending ≤ holding, distribution
                           split). Returns {ok, checks[]} — ok == zero drift. Read-only;
                           never repairs. Cron target (admin OR X-Cron-Secret).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminOrCronDep, SessionDep
from app.services import reconciliation_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/reconciliation")
async def reconciliation(session: SessionDep, caller: AdminOrCronDep) -> dict:
    return await reconciliation_service.run(session)
