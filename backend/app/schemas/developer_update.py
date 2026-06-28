"""Investor-communications DTOs (Phase 15c).

The developer sends a per-property update (subject + body); the SERVER resolves the
audience (that property's current net-holders) and snapshots ``recipient_count``.
Metrics are counts only: ``recipient_count`` (snapshot) + ``read_count`` (real, from
``notifications.read``). No open/click/delivered — that infra does not exist.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class DeveloperUpdateCreateIn(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


class DeveloperUpdateOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    subject: str
    body: str
    recipient_count: int
    read_count: int
    created_at: dt.datetime
