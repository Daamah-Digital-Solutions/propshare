"""Investment certificate DTOs (client, 2026-10-28). Money as decimal-exact STRINGS."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel


class MyCertificateOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    property_title: str
    number: str
    verification_code: str
    verify_path: str  # the public verification page, on the site
    verify_url: str
    units: int
    ownership: str
    spv_name: str | None
    location: str | None
    status: str
    issued_at: dt.datetime


class MyCertificatesOut(BaseModel):
    items: list[MyCertificateOut]


class CertificateVerificationOut(BaseModel):
    """What the public verification page shows (no account ids, emails or file paths)."""

    number: str
    status: str  # valid | superseded | revoked
    issued_at: dt.datetime
    superseded_at: dt.datetime | None
    revoked_at: dt.datetime | None
    revocation_reason: str | None
    holder_name: str
    holder_ref: str
    property_title: str
    location: str | None
    spv_name: str | None
    jurisdiction: str | None
    units: int
    ownership: str
    unit_price: str
    value: str
    verification_code: str
    signature: str
    issuer: str
    verified_at: dt.datetime
