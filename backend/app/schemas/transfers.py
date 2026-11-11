"""Transfers of units or wallet balance to another person (client, 2026-10-28)."""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class TransferIn(BaseModel):
    # plan (0042): units of a running installment plan of the sender's (``plan_id``)
    asset: Literal["units", "balance", "plan"]
    recipient_email: EmailStr
    recipient_name: str | None = Field(default=None, max_length=120)
    property_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
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


class TransferPlanOut(BaseModel):
    """A running installment plan of the sender's, part (or all) of which can be sent."""

    plan_id: uuid.UUID
    property_id: uuid.UUID
    property_title: str
    units: int
    free_units: int
    unit_price: str
    overdue_amount: str  # a plan's units go only when nothing is overdue
    pledged: bool  # a Nova Sukuk pledge not released yet: cannot be sent


class TransferOptionsOut(BaseModel):
    positions: list[TransferPositionOut]
    plans: list[TransferPlanOut] = []
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
    # units of an installment plan: the recipient's share of the payments
    plan: TransferPlanQuoteOut | None = None


class TransferPlanPaymentOut(BaseModel):
    seq: int
    kind: str
    due_date: datetime.date
    base_amount: str
    fee_amount: str
    total_amount: str
    status: str


class TransferPlanQuoteOut(BaseModel):
    plan_id: uuid.UUID
    units: int
    plan_units: int
    vested_units: int
    value: str
    paid_principal: str
    remaining_principal: str
    remaining_fees: str
    installments_left: int
    next_due: datetime.date | None
    schedule: list[TransferPlanPaymentOut]


class TransferOut(BaseModel):
    id: uuid.UUID
    reference: str
    direction: Literal["sent", "received"]
    counterparty: str
    recipient_email: str | None
    asset: str
    property_id: uuid.UUID | None
    property_title: str | None
    plan_id: uuid.UUID | None = None
    new_plan_id: uuid.UUID | None = None
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


TransferQuoteOut.model_rebuild()
