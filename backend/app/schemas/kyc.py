"""KYC DTOs (Phase 2)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel


class KycStatusOut(BaseModel):
    status: str
    manual_review_required: bool
    provider: str | None
    submitted_at: dt.datetime | None
    verified_at: dt.datetime | None
    rejection_reason: str | None


class KycStartOut(BaseModel):
    sdk_token: str
    applicant_id: str | None
    provider: str


class AdminKycOut(BaseModel):
    user_id: uuid.UUID
    status: str
    manual_review_required: bool
    last_review_answer: str | None
    submitted_at: dt.datetime | None
    rejection_reason: str | None


class AdminKycDecisionIn(BaseModel):
    approve: bool
    reason: str | None = None
