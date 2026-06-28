"""Property-milestone DTOs (Phase 15b).

Writes are owner-scoped (the route enforces ``property.owner_id``); the SERVER is
authoritative on ``sort_index`` (append on create / reorder endpoint) and
``completed_at`` (auto-set when status flips to ``completed``). ``value_index``
is the NAV step — optional/advanced; regular milestones leave it null.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field

MILESTONE_STATUSES = ("planned", "in_progress", "completed")


class MilestoneOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    title: str
    description: str | None
    status: str
    progress_pct: int | None
    value_index: int | None
    target_date: dt.date | None
    completed_at: dt.datetime | None
    sort_index: int


class MilestoneCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: str = "planned"
    progress_pct: int | None = Field(default=None, ge=0, le=100)
    value_index: int | None = Field(default=None, ge=0)
    target_date: dt.date | None = None


class MilestoneUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None
    progress_pct: int | None = Field(default=None, ge=0, le=100)
    value_index: int | None = Field(default=None, ge=0)
    target_date: dt.date | None = None


class MilestoneReorderIn(BaseModel):
    ordered_ids: list[uuid.UUID] = Field(min_length=1)
