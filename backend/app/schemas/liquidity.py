"""Liquidity-provider DTOs (Phase 9). Money as decimal-exact STRINGS, never float.

Server-authoritative: the client sends only property + units (seller) or units (LP);
the SERVER computes discount/fee/price off ``platform_settings`` and ``unit_price``.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ExitRequestCreateIn(BaseModel):
    property_id: uuid.UUID
    units: int = Field(gt=0, le=10_000_000)


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


class ExitRequestListOut(BaseModel):
    items: list[ExitRequestOut]
    total: int


class FundIn(BaseModel):
    units: int = Field(gt=0, le=10_000_000)


class PositionOut(BaseModel):
    position_id: uuid.UUID
    classification: str
    property_id: str | None
    units_acquired: int | None
    principal: str
    spread_at_entry: str | None
    status: str
    created_at: str | None


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
