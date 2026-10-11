"""Estate / inheritance DTOs (Group 4; certificate, documents and claims: 0035)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, EmailStr, Field


class EstateBeneficiaryIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    relationship: str | None = Field(default=None, max_length=80)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    allocation_pct: int = Field(ge=0, le=100)
    notes: str | None = Field(default=None, max_length=2000)
    meta: dict = Field(default_factory=dict)  # UI extras (role/scope/trigger/id) — round-trip


class EstateBeneficiaryUpdateIn(BaseModel):
    """Only the fields sent change; an optional field sent as null is cleared."""

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    relationship: str | None = Field(default=None, max_length=80)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    allocation_pct: int | None = Field(default=None, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=2000)
    meta: dict | None = None


class BeneficiaryDocumentOut(BaseModel):
    """A copy of the person's identity document, by name (the file is fetched by its id)."""

    id: str
    filename: str
    content_type: str
    size: int
    uploaded_at: str | None = None


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
    updated_at: dt.datetime | None = None
    # the number printed on the person's certificate, and how many times what it prints changed
    certificate_no: str | None = None
    version: int = 1
    documents: list[BeneficiaryDocumentOut] = []
    # true once a transfer event was recorded for the holder: the register is read-only
    locked: bool = False


class EstateExecutionOut(BaseModel):
    estate_event_id: str
    executed: bool
    replayed: bool
    transfers: int


class ClaimDocumentOut(BaseModel):
    kind: str
    filename: str


class EstateClaimOut(BaseModel):
    """A claim as its claimant sees it."""

    id: str
    reference: str
    status: str  # submitted | in_review | needs_info | approved | rejected
    status_label: str
    reason: str
    holder_name: str
    certificate_no: str | None
    message: str | None  # staff's last message to the claimant
    documents: list[ClaimDocumentOut]
    can_add_documents: bool
    created_at: str | None
    updated_at: str | None
