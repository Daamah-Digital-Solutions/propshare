"""Transfers of units or wallet balance to another person (client, 2026-10-28)."""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class TransferIn(BaseModel):
    asset: Literal["units", "balance"]
    recipient_email: EmailStr
    recipient_name: str | None = Field(default=None, max_length=120)
    property_id: uuid.UUID | None = None
    units: int | None = Field(default=None, ge=1)
    amount: str | None = Field(default=None, max_length=20)
    # today when left out; up to a year ahead
    deliver_on: datetime.date | None = None
    message: str | None = Field(default=None, max_length=500)
    occasion: (
        Literal["birthday", "graduation", "wedding", "new_baby", "holiday", "other"] | None
    ) = None
    # what the review step said leaves the wallet; sending refuses if it changed since
    expected_charged: str | None = Field(default=None, max_length=20)


class TransferPositionOut(BaseModel):
    property_id: uuid.UUID
    property_title: str
    units: int
    free_units: int
    unit_price: str


class TransferOptionsOut(BaseModel):
    positions: list[TransferPositionOut]
    balance: str
    fee_pct: str
    claim_days: int
    max_days_ahead: int


class TransferQuoteOut(BaseModel):
    asset: str
    recipient_email: str
    recipient_name: str | None
    property_id: uuid.UUID | None
    property_title: str | None
    units: int | None
    unit_price: str | None
    amount: str
    fee: str
    fee_pct: str
    # what leaves the wallet now: the amount and the fee, or only the fee for units
    charged: str
    deliver_on: datetime.date
    message: str | None
    occasion: str | None
    claim_days: int


class TransferOut(BaseModel):
    id: uuid.UUID
    reference: str
    direction: Literal["sent", "received"]
    counterparty: str
    recipient_email: str | None
    asset: str
    property_id: uuid.UUID | None
    property_title: str | None
    units: int | None
    unit_price: str | None
    amount: str
    fee: str
    message: str | None
    occasion: str | None
    deliver_on: datetime.date
    status: str
    status_label: str
    expires_at: datetime.datetime | None
    delivered_at: datetime.datetime | None
    closed_reason: str | None
    created_at: datetime.datetime
    can_cancel: bool


class TransferListOut(BaseModel):
    items: list[TransferOut]
