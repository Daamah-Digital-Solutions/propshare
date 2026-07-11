"""Payout-method + bank-deposit DTOs (Task 3). Money as decimal STRINGS on the way out."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class BankAccountIn(BaseModel):
    account_holder: str = Field(min_length=1, max_length=200)
    bank_name: str = Field(min_length=1, max_length=200)
    iban: str | None = Field(default=None, max_length=64)
    account_number: str | None = Field(default=None, max_length=64)
    swift_bic: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=64)
    currency: str = Field(default="USD", max_length=8)
    label: str | None = Field(default=None, max_length=100)


class BankAccountOut(BaseModel):
    id: uuid.UUID
    label: str | None
    account_holder: str
    bank_name: str
    iban: str | None
    account_number: str | None
    swift_bic: str | None
    country: str | None
    currency: str
    is_default: bool
    created_at: dt.datetime


class CryptoWalletIn(BaseModel):
    network: str = Field(min_length=1, max_length=64)
    address: str = Field(min_length=1, max_length=256)
    label: str | None = Field(default=None, max_length=100)


class CryptoWalletOut(BaseModel):
    id: uuid.UUID
    label: str | None
    network: str
    address: str
    is_default: bool
    created_at: dt.datetime


class PlatformBankAccountOut(BaseModel):
    """The platform's receiving account, as shown to a depositing user."""

    id: uuid.UUID
    bank_name: str
    account_holder: str
    iban: str | None
    account_number: str | None
    swift_bic: str | None
    currency: str
    country: str | None
    instructions: str | None


class BankClaimIn(BaseModel):
    amount: float = Field(gt=0, le=1_000_000_000)
    platform_account_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=200)
    sender_name: str | None = Field(default=None, max_length=200)
