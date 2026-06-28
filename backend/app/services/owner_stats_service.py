"""Phase 15 — Owner/Developer real-stats aggregation (read-only, no money mutation).

Every figure is computed by SQL aggregation over EXISTING tables, scoped to the
caller's own properties (``properties.owner_id``). No fabricated numbers, no new
tables. Occupancy has no data domain yet, so it is returned as ``None`` (honest
empty state) — never a faked percentage.

Definitions (owner-confirmed):
- Total Investors = distinct holders with net units > 0 (fully-exited users excluded).
- Monthly Revenue = SUM(distributions.gross_pool) where status='completed', grouped by
  ``date_trunc('month', created_at)``; the card is the CURRENT calendar month, the
  chart is the last 6 months with real zeros for empty months.
- Funding = SUM(investments.amount) where status='confirmed', grouped by
  ``date_trunc('month', confirmed_at)``; 6-month series + current-month value.
- Repeat Investors = investors with >= 2 confirmed investment rows / distinct investors.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Distribution, Investment, OwnershipLedger, Property

_CENTS = decimal.Decimal("0.01")
_MONTHS_WINDOW = 6


def _money(v: object) -> str:
    return str(decimal.Decimal(str(v or 0)).quantize(_CENTS))


def _month_spine(now: dt.datetime, n: int = _MONTHS_WINDOW) -> list[str]:
    """The last ``n`` months including the current one, as 'YYYY-MM' ascending."""
    year, month = now.year, now.month
    out: list[str] = []
    for _ in range(n):
        out.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(out))


def _month_key(d: dt.datetime | dt.date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


async def _owner_property_ids(session: AsyncSession, owner_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await session.execute(select(Property.id).where(Property.owner_id == owner_id))
    return [r[0] for r in rows.all()]


async def portfolio_stats(
    session: AsyncSession, owner_id: uuid.UUID, *, now: dt.datetime | None = None
) -> dict:
    now = now or dt.datetime.now(dt.UTC)
    spine = _month_spine(now)
    prop_ids = await _owner_property_ids(session, owner_id)

    if not prop_ids:
        return {
            "total_portfolio_value": "0.00",
            "total_investors": 0,
            "occupancy": None,
            "monthly_revenue_current": "0.00",
            "monthly_revenue_series": [{"month": m, "amount": "0.00"} for m in spine],
            "per_property": [],
        }

    # Total portfolio value = Σ total_value of the owner's properties.
    pv = await session.execute(
        select(func.coalesce(func.sum(Property.total_value), 0)).where(
            Property.owner_id == owner_id
        )
    )
    total_value = pv.scalar_one()

    # Total investors = distinct holders with net units > 0 across the owner's properties.
    holders = (
        select(OwnershipLedger.user_id)
        .where(OwnershipLedger.property_id.in_(prop_ids))
        .group_by(OwnershipLedger.user_id)
        .having(func.coalesce(func.sum(OwnershipLedger.units), 0) > 0)
        .subquery()
    )
    inv = await session.execute(select(func.count()).select_from(holders))
    total_investors = int(inv.scalar_one() or 0)

    # Monthly revenue = completed distributions on the owner's properties, by created-at month.
    # Bucket in UTC ('YYYY-MM' string) so the key matches the Python (UTC) month spine
    # regardless of the DB session timezone.
    month_expr = func.to_char(func.timezone("UTC", Distribution.created_at), "YYYY-MM")
    rev_rows = await session.execute(
        select(month_expr.label("m"), func.coalesce(func.sum(Distribution.gross_pool), 0))
        .where(Distribution.property_id.in_(prop_ids), Distribution.status == "completed")
        .group_by(month_expr)
    )
    rev_by_month: dict[str, decimal.Decimal] = {
        m: decimal.Decimal(str(amt or 0)) for m, amt in rev_rows.all()
    }
    series = [{"month": m, "amount": _money(rev_by_month.get(m, 0))} for m in spine]
    current = rev_by_month.get(_month_key(now), decimal.Decimal(0))

    # Per-property revenue (all-time completed distributions), keyed for the property cards.
    pp_rows = await session.execute(
        select(Distribution.property_id, func.coalesce(func.sum(Distribution.gross_pool), 0))
        .where(Distribution.property_id.in_(prop_ids), Distribution.status == "completed")
        .group_by(Distribution.property_id)
    )
    pp_map = {pid: decimal.Decimal(str(amt or 0)) for pid, amt in pp_rows.all()}
    per_property = [
        {
            "property_id": str(pid),
            "revenue_generated": _money(pp_map.get(pid, 0)),
            "occupancy": None,
        }
        for pid in prop_ids
    ]

    return {
        "total_portfolio_value": _money(total_value),
        "total_investors": total_investors,
        "occupancy": None,
        "monthly_revenue_current": _money(current),
        "monthly_revenue_series": series,
        "per_property": per_property,
    }


async def funding_stats(
    session: AsyncSession, owner_id: uuid.UUID, *, now: dt.datetime | None = None
) -> dict:
    now = now or dt.datetime.now(dt.UTC)
    spine = _month_spine(now)
    prop_ids = await _owner_property_ids(session, owner_id)

    empty = {
        "monthly_funding_series": [{"month": m, "amount": "0.00"} for m in spine],
        "funding_this_month": "0.00",
        "repeat_investors": {"repeat": 0, "total": 0, "pct": "0.0"},
        "distinct_investors": 0,
    }
    if not prop_ids:
        return empty

    # Monthly funding = confirmed investments on the developer's properties, by confirmed-at
    # month. Bucket in UTC ('YYYY-MM') to match the Python (UTC) month spine.
    month_expr = func.to_char(func.timezone("UTC", Investment.confirmed_at), "YYYY-MM")
    fund_rows = await session.execute(
        select(month_expr.label("m"), func.coalesce(func.sum(Investment.amount), 0))
        .where(
            Investment.property_id.in_(prop_ids),
            Investment.status == "confirmed",
            Investment.confirmed_at.is_not(None),
        )
        .group_by(month_expr)
    )
    fund_by_month: dict[str, decimal.Decimal] = {
        m: decimal.Decimal(str(amt or 0)) for m, amt in fund_rows.all()
    }
    series = [{"month": m, "amount": _money(fund_by_month.get(m, 0))} for m in spine]
    this_month = fund_by_month.get(_month_key(now), decimal.Decimal(0))

    # Repeat investors = per-user count of confirmed investments across the dev's properties.
    per_user = (
        select(Investment.user_id, func.count().label("n"))
        .where(Investment.property_id.in_(prop_ids), Investment.status == "confirmed")
        .group_by(Investment.user_id)
        .subquery()
    )
    agg = await session.execute(
        select(func.count().filter(per_user.c.n >= 2), func.count()).select_from(per_user)
    )
    repeat_count, total_investors = agg.one()
    repeat_count = int(repeat_count or 0)
    total_investors = int(total_investors or 0)
    pct = (
        (decimal.Decimal(repeat_count) / decimal.Decimal(total_investors) * 100).quantize(
            decimal.Decimal("0.1")
        )
        if total_investors
        else decimal.Decimal("0.0")
    )

    return {
        "monthly_funding_series": series,
        "funding_this_month": _money(this_month),
        "repeat_investors": {"repeat": repeat_count, "total": total_investors, "pct": str(pct)},
        "distinct_investors": total_investors,
    }
