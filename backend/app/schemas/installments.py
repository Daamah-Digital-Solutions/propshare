"""Installment plan DTOs (Group 6)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class InstallmentPlanCreateIn(BaseModel):
    property_id: uuid.UUID
    amount: float = Field(gt=0)  # USD; server floors to whole units at the locked unit_price
    duration_months: int = Field(description="6 | 12 | 18 | 24")
    # How the down payment is paid (a Nova Sukuk certificate goes to POST /installments/sukuk).
    method: str = Field(default="wallet", pattern="^(wallet|card|crypto|pronova)$")


class InstallmentPaymentOut(BaseModel):
    id: uuid.UUID
    seq: int
    kind: str
    due_date: dt.date
    base_amount: str
    fee_amount: str
    total_amount: str
    vest_units: int
    status: str
    paid_at: dt.datetime | None


class InstallmentPlanOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    # Which property this plan is for — so the schedule can be shown per-property (Task 6).
    property_title: str
    property_slug: str | None = None
    property_location: str | None = None
    property_city: str | None = None
    property_image: str | None = None
    property_spv: str | None = None
    units_total: int
    unit_price: str
    down_payment_pct: int
    duration_months: int
    fee_rate: str
    vested_units: int
    # active | completed; before it starts: pending_payment | pending_review; never started:
    # cancelled | expired
    status: str
    payment_method: str = "wallet"  # how the down payment is paid
    discount_amount: str = "0"  # Pronova discount on the down payment
    reservation_expires_at: dt.datetime | None = None
    failure_reason: str | None = None
    # a down-payment checkout still open: where to pay it
    checkout_url: str | None = None
    payment_id: uuid.UUID | None = None
    created_at: dt.datetime
    completed_at: dt.datetime | None
    payments: list[InstallmentPaymentOut]


class InstallmentRunOut(BaseModel):
    reminders_sent: int
    paid: int
    overdue: int
