"""Admin DTOs (Phase 1 subset: users + role management)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    email_verified: bool
    roles: list[str]
    active_role: str | None
    created_at: dt.datetime


class GrantRoleIn(BaseModel):
    role: str


class RoleRequestOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    status: str
    # Task 12 — the applicant's join-form data + document refs ({"fields","documents"}).
    application: dict = {}
    created_at: dt.datetime


class RoleDecisionIn(BaseModel):
    approve: bool
