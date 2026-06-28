"""Distribution / returns DTOs (Phase 6). Money as decimal-exact STRINGS."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class DistributionRunIn(BaseModel):
    kind: str = Field(default="rental", pattern="^(rental|appreciation|other)$")
    period_key: str = Field(min_length=1, max_length=40)
    period_start: dt.date
    period_end: dt.date
    gross_pool: float = Field(gt=0, le=1_000_000_000)


class DistributionRunOut(BaseModel):
    distribution_id: uuid.UUID
    property_id: uuid.UUID
    period_key: str
    gross_pool: str
    total_net: str
    total_management_fee: str
    investors: int
    status: str


class ReturnItemOut(BaseModel):
    distribution_id: str
    property_id: str
    kind: str
    period_key: str
    period_end: str
    units: int
    gross_amount: str
    management_fee: str
    net_amount: str


class MonthlyReturnOut(BaseModel):
    month: str
    net: str


class MyReturnsOut(BaseModel):
    total_net: str
    total_management_fee: str
    count: int
    monthly: list[MonthlyReturnOut]
    items: list[ReturnItemOut]
