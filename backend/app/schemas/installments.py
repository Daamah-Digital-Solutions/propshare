"""Installment plan DTOs (Group 6)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class InstallmentPlanCreateIn(BaseModel):
    property_id: uuid.UUID
    amount: float = Field(gt=0)  # USD; server floors to whole units at the locked unit_price
    duration_months: int = Field(description="6 | 12 | 18 | 24")


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
    units_total: int
    unit_price: str
    down_payment_pct: int
    duration_months: int
    fee_rate: str
    vested_units: int
    status: str
    created_at: dt.datetime
    completed_at: dt.datetime | None
    payments: list[InstallmentPaymentOut]


class InstallmentRunOut(BaseModel):
    reminders_sent: int
    paid: int
    overdue: int
