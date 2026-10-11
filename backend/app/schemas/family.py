"""Family groups & gifting DTOs (Phase 10). Money as decimal-exact STRINGS."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, EmailStr, Field


class GroupCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class MemberCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    relationship: str = Field(min_length=1, max_length=60)
    date_of_birth: date | None = None
    phone: str | None = Field(default=None, max_length=40)
    national_id: str | None = Field(default=None, max_length=60)
    nationality: str | None = Field(default=None, max_length=60)
    address: str | None = Field(default=None, max_length=300)


class MemberUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    relationship: str | None = Field(default=None, min_length=1, max_length=60)
    date_of_birth: date | None = None
    phone: str | None = Field(default=None, max_length=40)
    national_id: str | None = Field(default=None, max_length=60)
    nationality: str | None = Field(default=None, max_length=60)
    address: str | None = Field(default=None, max_length=300)


class MemberBankAccountIn(BaseModel):
    bank_name: str = Field(min_length=1, max_length=120)
    account_holder: str | None = Field(default=None, max_length=120)
    iban: str | None = Field(default=None, max_length=64)
    account_number: str | None = Field(default=None, max_length=64)
    swift_bic: str | None = Field(default=None, max_length=32)
    label: str | None = Field(default=None, max_length=80)


class MemberBankAccountOut(BaseModel):
    id: str
    label: str | None
    bank_name: str
    account_holder: str | None
    iban: str | None
    account_number: str | None
    swift_bic: str | None


class MemberOut(BaseModel):
    member_id: str
    name: str
    email: str | None
    relationship: str
    is_verified: bool
    is_user: bool
    pending_units: int
    allocated_returns: str
    # the part of allocated_returns not paid yet (released when the member verifies)
    pending_returns: str = "0"
    # the owner: units held; another member: units that reached them through this group
    real_units: int = 0
    # the group owner's own row (the sender of every transfer)
    is_self: bool = False
    date_of_birth: str | None = None
    phone: str | None = None
    national_id: str | None = None
    nationality: str | None = None
    address: str | None = None
    linked_date: str | None = None
    bank_accounts: list[MemberBankAccountOut] = []


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
    # the history's own fields (the list fills them; a single create/cancel answer does not)
    from_name: str | None = None
    to_name: str | None = None
    property_title: str | None = None
    completed_at: str | None = None


class TransferListOut(BaseModel):
    items: list[TransferOut]
    total: int


class ActivityItemOut(BaseModel):
    """One line of the caller's family activity. ``kind``: transfer | returns | member.
    ``direction``: out (the caller did it) | in (it was done for the caller) | other."""

    id: str
    kind: str
    direction: str
    at: str | None
    counterparty: str
    from_name: str | None = None
    property_id: str | None = None
    property_title: str | None = None
    units: int | None = None
    amount: str | None = None
    fee: str | None = None
    status: str
    completed_at: str | None = None
    relationship: str | None = None


class MembershipOut(BaseModel):
    """A family group the caller was added to (and does not own)."""

    group_name: str
    owner_name: str
    relationship: str
    since: str | None
    is_verified: bool


class ActivityOut(BaseModel):
    items: list[ActivityItemOut]
    memberships: list[MembershipOut]


class AllocateReturnsIn(BaseModel):
    member_id: uuid.UUID
    amount: float = Field(gt=0, le=1_000_000_000)


class ReinvestIn(BaseModel):
    property_id: uuid.UUID
    amount: float = Field(gt=0, le=1_000_000_000)


class FamilySettingsOut(BaseModel):
    reinvest_discount_pct: str
    transfer_fee_pct: str
