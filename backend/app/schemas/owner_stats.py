"""Phase 15 — Owner/Developer real-stats read schemas.

All money values are strings (matches every existing money API). ``occupancy`` is
``None`` on purpose: there is no occupancy/tenancy domain in the schema yet, so the
card renders an honest empty state rather than a fabricated number.
"""

from __future__ import annotations

from pydantic import BaseModel


class MonthlyPoint(BaseModel):
    month: str  # "YYYY-MM"
    amount: str  # decimal, as string


class PerPropertyStat(BaseModel):
    property_id: str
    revenue_generated: str  # all-time completed distributions on this property
    occupancy: float | None = None  # honest empty — no occupancy domain yet


class OwnerPortfolioStatsOut(BaseModel):
    total_portfolio_value: str
    total_investors: int
    occupancy: float | None = None  # honest empty
    monthly_revenue_current: str
    monthly_revenue_series: list[MonthlyPoint]
    per_property: list[PerPropertyStat]


class RepeatInvestors(BaseModel):
    repeat: int
    total: int
    pct: str  # one-decimal percentage as string, e.g. "50.0"


class DeveloperFundingStatsOut(BaseModel):
    monthly_funding_series: list[MonthlyPoint]
    funding_this_month: str
    repeat_investors: RepeatInvestors
    distinct_investors: int
