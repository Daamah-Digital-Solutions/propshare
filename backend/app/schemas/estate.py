"""Estate / inheritance DTOs (Group 4)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class EstateBeneficiaryIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    relationship: str | None = None
    email: str | None = None
    phone: str | None = None
    allocation_pct: int = Field(ge=0, le=100)
    notes: str | None = None
    meta: dict = Field(default_factory=dict)  # UI extras (role/scope/trigger/id) — round-trip


class EstateBeneficiaryUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    relationship: str | None = None
    email: str | None = None
    phone: str | None = None
    allocation_pct: int | None = Field(default=None, ge=0, le=100)
    notes: str | None = None
    meta: dict | None = None


class EstateBeneficiaryOut(BaseModel):
    id: uuid.UUID
    full_name: str
    relationship: str | None
    email: str | None
    phone: str | None
    allocation_pct: int
    notes: str | None
    status: str
    is_user: bool
    meta: dict
    created_at: dt.datetime


class EstateExecutionOut(BaseModel):
    estate_event_id: str
    executed: bool
    replayed: bool
    transfers: int
