"""Wallet & deposit DTOs (Phase 4).

Money is returned as STRINGS (decimal-exact) — never float. Deposit amounts the
client sends are the *requested* amount; the credited amount is whatever the
provider webhook reports as captured (server-authoritative).
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class WalletOut(BaseModel):
    balance: str
    pending_balance: str
    total_invested: str
    total_returns: str
    currency: str


class TransactionOut(BaseModel):
    id: uuid.UUID
    type: str
    amount: str
    status: str
    description: str | None
    payment_method: str | None
    reference_id: uuid.UUID | None
    created_at: dt.datetime


class TransactionListOut(BaseModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int


class DepositIn(BaseModel):
    amount: float = Field(gt=0, le=1_000_000_000)
    method: str = Field(pattern="^(card|crypto)$")


class DepositOut(BaseModel):
    payment_id: uuid.UUID
    provider: str
    status: str
    checkout_url: str | None  # hosted checkout to redirect to


class PaymentStatusOut(BaseModel):
    id: uuid.UUID
    provider: str
    status: str
    amount: str
    amount_captured: str | None
    created_at: dt.datetime
