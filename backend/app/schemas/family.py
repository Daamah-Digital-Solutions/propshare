"""Family groups & gifting DTOs (Phase 10). Money as decimal-exact STRINGS."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class GroupCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class MemberCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    relationship: str = Field(min_length=1, max_length=60)


class MemberOut(BaseModel):
    member_id: str
    name: str
    email: str | None
    relationship: str
    is_verified: bool
    is_user: bool
    pending_units: int
    allocated_returns: str
    real_units: int = 0


class GroupOut(BaseModel):
    group_id: str
    name: str
    total_returns: str
    members: list[MemberOut]


class TransferCreateIn(BaseModel):
    from_member_id: uuid.UUID
    to_member_id: uuid.UUID
    property_id: uuid.UUID
    units: int = Field(gt=0, le=10_000_000)


class TransferOut(BaseModel):
    transfer_id: str
    from_member_id: str | None
    to_member_id: str
    property_id: str | None
    units: int
    transfer_fee: str
    status: str
    created_at: str | None


class TransferListOut(BaseModel):
    items: list[TransferOut]
    total: int


class AllocateReturnsIn(BaseModel):
    member_id: uuid.UUID
    amount: float = Field(gt=0, le=1_000_000_000)


class ReinvestIn(BaseModel):
    property_id: uuid.UUID
    amount: float = Field(gt=0, le=1_000_000_000)


class FamilySettingsOut(BaseModel):
    reinvest_discount_pct: str
    transfer_fee_pct: str
