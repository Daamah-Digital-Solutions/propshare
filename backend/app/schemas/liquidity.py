"""Liquidity-provider DTOs (Phase 9). Money as decimal-exact STRINGS, never float.

Server-authoritative: the client sends only property + units (seller) or units (LP);
the SERVER computes discount/fee/price off ``platform_settings`` and ``unit_price``.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field, model_validator


class ExitRequestCreateIn(BaseModel):
    # ordinary units: property_id + units. Units of a running installment plan (0042):
    # plan_id + units (some of the plan's units, or all).
    property_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    units: int = Field(gt=0, le=10_000_000)

    @model_validator(mode="after")
    def _one_kind(self) -> ExitRequestCreateIn:
        if (self.property_id is None) == (self.plan_id is None):
            raise ValueError("send property_id, or plan_id")
        return self


class PlanInstallmentOut(BaseModel):
    seq: int
    kind: str
    due_date: dt.date
    base_amount: str
    fee_amount: str
    total_amount: str
    status: str


class PlanUnitsOut(BaseModel):
    """Units of a running installment plan offered to providers (0042), at the provider's
    price: the discounted value (``lp_value``), the share of the principal still to pay that
    the provider takes over, and the ``cash`` the provider pays the seller now."""

    plan_id: uuid.UUID
    units: int
    plan_units: int
    vested_units: int
    lp_unit_price: str
    lp_value: str
    paid_principal: str
    remaining_principal: str
    remaining_fees: str
    cash: str
    liquidity_fee: str
    seller_net: str
    installments_left: int
    next_due: dt.date | None
    schedule: list[PlanInstallmentOut]


class PlanUnitsQuoteOut(PlanUnitsOut):
    request_id: uuid.UUID
    units_remaining: int
    whole: bool


class ExitRequestOut(BaseModel):
    request_id: uuid.UUID
    property_id: str
    property_title: str | None
    property_location: str | None
    seller_id: str
    units: int
    units_remaining: int
    unit_price: str
    discount_pct: str
    fee_pct: str
    gross: str
    lp_price: str
    liquidity_fee: str
    seller_net: str
    status: str
    created_at: str | None
    expires_at: str | None
    # 0042: units of a running installment plan, and what those still offered come to (for
    # plan units, lp_price is the cash the provider pays now)
    plan_id: uuid.UUID | None = None
    position: PlanUnitsOut | None = None


class ExitRequestListOut(BaseModel):
    items: list[ExitRequestOut]
    total: int


class FundIn(BaseModel):
    units: int = Field(gt=0, le=10_000_000)
    # units of an installment plan only: the cash the provider was shown
    expected_cash: str | None = Field(default=None, max_length=24)


class PositionOut(BaseModel):
    position_id: uuid.UUID
    classification: str
    property_id: str | None
    units_acquired: int | None
    principal: str
    spread_at_entry: str | None
    status: str
    created_at: str | None
    plan_id: uuid.UUID | None = None  # 0042: the installment plan taken with the units


class PositionListOut(BaseModel):
    items: list[PositionOut]
    total: int


class CancelOut(BaseModel):
    request_id: uuid.UUID
    status: str


class PoolTierOut(BaseModel):
    period_months: int
    apy_pct: str
    min_amount: str


class LiquiditySettingsOut(BaseModel):
    discount_pct: str
    fee_pct: str
    ttl_minutes: int
    band_pct: str
    passive_enabled: bool
    tiers: list[PoolTierOut]
