"""Property-milestone service (Phase 15b).

Owner-scoped CRUD + reorder over ``property_milestones``, the computed
construction-progress roll-up, and the PURE converter that turns the legacy
``content.timeline[]`` JSONB into milestone rows (shared by the 0015 backfill,
the seed script, and the tests — one tested source of truth).

constructionProgress rule (owner-confirmed): the CURRENT milestone's progress —
the ``progress_pct`` of the ``in_progress`` milestone (highest ``sort_index`` if
several), else 0. This avoids the admin-step skew of a naive max-completed (the
first "Listed/Down Payment" milestone carries progress 100 as an admin step).
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Property
from app.models.base import MilestoneStatus
from app.models.milestones import PropertyMilestone
from app.schemas.milestone import MILESTONE_STATUSES

# Legacy content.timeline status -> the real enum.
_STATUS_FROM_TIMELINE = {
    "done": "completed",
    "active": "in_progress",
    "upcoming": "planned",
}


# --- pure converter (no DB; importable by the migration / seed / tests) ----- #
def _add_months(d: dt.date, n: int) -> dt.date:
    total = d.month - 1 + n
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def parse_relative_date(token: str, anchor: dt.date) -> dt.date | None:
    """Convert a legacy relative date ('Today', '+30d', '+6m', '+1y') to a concrete date."""
    t = (token or "").strip().lower()
    if not t:
        return None
    if t == "today":
        return anchor
    m = re.fullmatch(r"\+\s*(\d+)\s*([dmy])", t)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if unit == "d":
        return anchor + dt.timedelta(days=n)
    if unit == "m":
        return _add_months(anchor, n)
    return _add_months(anchor, n * 12)  # 'y'


def _as_int(v: object) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def timeline_to_milestone_rows(
    timeline: list,
    *,
    anchor: dt.date,
    created_by: uuid.UUID | None = None,
) -> list[dict]:
    """Convert a property's ``content.timeline[]`` into property_milestones row dicts.

    Deterministic: relative dates anchored on ``anchor`` (the property's created_at
    date), status mapped, ``value_index`` carried, ``sort_index`` = array order.
    """
    rows: list[dict] = []
    for i, entry in enumerate(timeline or []):
        if not isinstance(entry, dict):
            continue
        status = _STATUS_FROM_TIMELINE.get(str(entry.get("status", "")).lower(), "planned")
        target = parse_relative_date(str(entry.get("date", "")), anchor)
        completed_at: dt.datetime | None = None
        if status == "completed" and target is not None:
            completed_at = dt.datetime.combine(target, dt.time(0, 0), tzinfo=dt.UTC)
        rows.append(
            {
                "title": str(entry.get("label") or "Milestone"),
                "description": entry.get("description"),
                "status": status,
                "progress_pct": _as_int(entry.get("progress")),
                "value_index": _as_int(entry.get("valueIndex")),
                "target_date": target,
                "completed_at": completed_at,
                "sort_index": i,
                "created_by": created_by,
            }
        )
    return rows


# --- construction-progress roll-up ----------------------------------------- #
def construction_progress_from_rows(rows: list[PropertyMilestone]) -> int:
    """Current-milestone rule: the in_progress milestone's progress (highest
    sort_index if several), else 0."""
    in_prog = [
        r for r in rows if r.status == MilestoneStatus.in_progress and r.progress_pct is not None
    ]
    if not in_prog:
        return 0
    current = max(in_prog, key=lambda r: r.sort_index)
    return int(current.progress_pct or 0)


async def construction_progress_map(
    session: AsyncSession, property_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Compute construction_progress for many properties in one query (no N+1)."""
    if not property_ids:
        return {}
    res = await session.execute(
        select(PropertyMilestone)
        .where(PropertyMilestone.property_id.in_(property_ids))
        .order_by(PropertyMilestone.property_id, PropertyMilestone.sort_index)
    )
    by_prop: dict[uuid.UUID, list[PropertyMilestone]] = defaultdict(list)
    for row in res.scalars().all():
        by_prop[row.property_id].append(row)
    return {pid: construction_progress_from_rows(by_prop.get(pid, [])) for pid in property_ids}


# --- serialization ---------------------------------------------------------- #
def serialize(m: PropertyMilestone) -> dict:
    return {
        "id": m.id,
        "property_id": m.property_id,
        "title": m.title,
        "description": m.description,
        "status": str(m.status),
        "progress_pct": m.progress_pct,
        "value_index": m.value_index,
        "target_date": m.target_date,
        "completed_at": m.completed_at,
        "sort_index": m.sort_index,
    }


# --- owner-scoped CRUD ------------------------------------------------------ #
async def _get_owned_property(
    session: AsyncSession, owner_id: uuid.UUID, prop_id: uuid.UUID
) -> Property:
    prop = await session.get(Property, prop_id)
    if prop is None:
        raise AppError("PROPERTY_NOT_FOUND", "Property not found.", status_code=404)
    if prop.owner_id != owner_id:
        raise AppError("NOT_PROPERTY_OWNER", "You do not own this property.", status_code=403)
    return prop


def _validate_status(status: str) -> str:
    if status not in MILESTONE_STATUSES:
        raise AppError(
            "INVALID_STATUS",
            f"status must be one of {list(MILESTONE_STATUSES)}",
            status_code=422,
        )
    return status


async def list_for_property(session: AsyncSession, prop_id: uuid.UUID) -> list[PropertyMilestone]:
    res = await session.execute(
        select(PropertyMilestone)
        .where(PropertyMilestone.property_id == prop_id)
        .order_by(PropertyMilestone.sort_index, PropertyMilestone.created_at)
    )
    return list(res.scalars().all())


async def list_owned(
    session: AsyncSession, owner_id: uuid.UUID, prop_id: uuid.UUID
) -> list[PropertyMilestone]:
    await _get_owned_property(session, owner_id, prop_id)
    return await list_for_property(session, prop_id)


async def create(
    session: AsyncSession, owner_id: uuid.UUID, prop_id: uuid.UUID, data: dict
) -> PropertyMilestone:
    await _get_owned_property(session, owner_id, prop_id)
    status = _validate_status(data.get("status") or "planned")
    res = await session.execute(
        select(func.coalesce(func.max(PropertyMilestone.sort_index), -1)).where(
            PropertyMilestone.property_id == prop_id
        )
    )
    next_sort = int(res.scalar_one()) + 1
    m = PropertyMilestone(
        property_id=prop_id,
        title=data["title"],
        description=data.get("description"),
        status=MilestoneStatus(status),
        progress_pct=data.get("progress_pct"),
        value_index=data.get("value_index"),
        target_date=data.get("target_date"),
        sort_index=next_sort,
        created_by=owner_id,
    )
    if status == "completed":
        m.completed_at = dt.datetime.now(dt.UTC)
    session.add(m)
    await session.commit()
    await session.refresh(m)
    return m


async def update(
    session: AsyncSession,
    owner_id: uuid.UUID,
    prop_id: uuid.UUID,
    milestone_id: uuid.UUID,
    data: dict,
) -> PropertyMilestone:
    await _get_owned_property(session, owner_id, prop_id)
    m = await session.get(PropertyMilestone, milestone_id)
    if m is None or m.property_id != prop_id:
        raise AppError("MILESTONE_NOT_FOUND", "Milestone not found.", status_code=404)
    if "title" in data and data["title"] is not None:
        m.title = data["title"]
    if "description" in data:
        m.description = data["description"]
    if "progress_pct" in data:
        m.progress_pct = data["progress_pct"]
    if "value_index" in data:
        m.value_index = data["value_index"]
    if "target_date" in data:
        m.target_date = data["target_date"]
    if "status" in data and data["status"] is not None:
        new_status = _validate_status(data["status"])
        was_completed = m.status == MilestoneStatus.completed
        m.status = MilestoneStatus(new_status)
        if new_status == "completed" and not was_completed:
            m.completed_at = dt.datetime.now(dt.UTC)
        elif new_status != "completed":
            m.completed_at = None
    m.updated_at = dt.datetime.now(dt.UTC)
    await session.commit()
    await session.refresh(m)
    return m


async def delete(
    session: AsyncSession,
    owner_id: uuid.UUID,
    prop_id: uuid.UUID,
    milestone_id: uuid.UUID,
) -> None:
    await _get_owned_property(session, owner_id, prop_id)
    m = await session.get(PropertyMilestone, milestone_id)
    if m is None or m.property_id != prop_id:
        raise AppError("MILESTONE_NOT_FOUND", "Milestone not found.", status_code=404)
    await session.delete(m)
    await session.commit()


async def reorder(
    session: AsyncSession,
    owner_id: uuid.UUID,
    prop_id: uuid.UUID,
    ordered_ids: list[uuid.UUID],
) -> list[PropertyMilestone]:
    await _get_owned_property(session, owner_id, prop_id)
    rows = await list_for_property(session, prop_id)
    existing = {r.id for r in rows}
    given = list(ordered_ids)
    if len(given) != len(existing) or set(given) != existing:
        raise AppError(
            "INVALID_REORDER",
            "ordered_ids must be exactly this property's milestone ids.",
            status_code=422,
        )
    by_id = {r.id: r for r in rows}
    for idx, mid in enumerate(given):
        by_id[mid].sort_index = idx
    await session.commit()
    return await list_for_property(session, prop_id)
