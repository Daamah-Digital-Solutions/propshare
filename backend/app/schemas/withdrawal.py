"""Withdrawal / Connect DTOs (Phase 7). Money as decimal-exact STRINGS."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class WithdrawalCreateIn(BaseModel):
    amount: float = Field(gt=0, le=1_000_000_000)
    method: str = Field(pattern="^(bank|crypto)$")
    address: str | None = None  # required for crypto; bank uses the Connect account


class WithdrawalCreateOut(BaseModel):
    withdrawal_id: uuid.UUID
    amount: str
    method: str
    status: str
    created_at: str | None


class WithdrawalOut(BaseModel):
    id: uuid.UUID
    amount: str
    method: str
    provider: str
    status: str
    failure_reason: str | None
    created_at: dt.datetime
    completed_at: dt.datetime | None


class WithdrawalListOut(BaseModel):
    items: list[WithdrawalOut]
    total: int


class ConnectStatusOut(BaseModel):
    status: str  # none | pending | verified | restricted
    payouts_enabled: bool
    details_submitted: bool
    stripe_account_id: str | None


class ConnectOnboardOut(BaseModel):
    onboarding_url: str
    account_id: str
    status: str
