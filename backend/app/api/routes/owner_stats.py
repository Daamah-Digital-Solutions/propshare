"""Phase 15 — Owner/Developer real-stats read endpoints.

Both dashboards are gated to the ``owner`` role, so both endpoints use the
action-time DB role re-check (``require_active_role_db("owner")``). Read-only
aggregation over existing tables — no money mutation, no new tables.

- GET /api/v1/owner/portfolio-stats   owner overview cards + monthly-revenue series.
- GET /api/v1/owner/funding-stats      developer funding series + repeat investors.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import Principal, SessionDep, require_active_role_db
from app.schemas.owner_stats import DeveloperFundingStatsOut, OwnerPortfolioStatsOut
from app.services import owner_stats_service

router = APIRouter(prefix="/api/v1", tags=["owner-stats"])

OwnerDep = Annotated[Principal, Depends(require_active_role_db("owner"))]


@router.get("/owner/portfolio-stats", response_model=OwnerPortfolioStatsOut)
async def owner_portfolio_stats(principal: OwnerDep, session: SessionDep):
    data = await owner_stats_service.portfolio_stats(session, principal.user_id)
    return OwnerPortfolioStatsOut(**data)


@router.get("/owner/funding-stats", response_model=DeveloperFundingStatsOut)
async def owner_funding_stats(principal: OwnerDep, session: SessionDep):
    data = await owner_stats_service.funding_stats(session, principal.user_id)
    return DeveloperFundingStatsOut(**data)
