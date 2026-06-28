"""Investment DTOs (Phase 5).

Money is returned as STRINGS (decimal-exact), never float. The client sends only
the property, a USD amount, and the funding method — the SERVER computes units,
fees and the total charge (server-authoritative).
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class InvestmentCreateIn(BaseModel):
    property_id: uuid.UUID
    amount: float = Field(gt=0, le=1_000_000_000)
    method: str = Field(pattern="^(wallet|card|crypto)$")


class InvestmentCreateOut(BaseModel):
    investment_id: uuid.UUID
    property_id: uuid.UUID
    status: str
    units: int
    amount: str  # unit subtotal (units * unit_price)
    platform_fee: str  # one-time, charged at purchase
    total_charged: str  # subtotal + platform_fee
    management_fee_rate: str  # annual, disclosed only (charged in Phase 6)
    checkout_url: str | None  # set for direct-pay; null for wallet-funded


class InvestmentOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    status: str
    units: int
    amount: str
    platform_fee: str
    total_charged: str
    confirmed_via: str | None
    created_at: dt.datetime
    confirmed_at: dt.datetime | None


class InvestmentListOut(BaseModel):
    items: list[InvestmentOut]
    total: int


class PortfolioOut(BaseModel):
    """Server-authoritative portfolio summary (decimal-exact strings)."""

    invested: str  # wallet.total_invested
    current_value: str  # Σ held units × property.unit_price (from ownership_ledger)
    total_returns: str  # wallet.total_returns
    properties: int  # distinct properties currently held
    units: int  # total units currently held


class ReinvestIn(BaseModel):
    property_id: uuid.UUID
    amount: float = Field(gt=0, le=1_000_000_000)


class ReinvestOut(BaseModel):
    property_id: str
    amount: str
    discount_pct: str | None = None
    effective_price: str | None = None
    units: int | None = None
    replayed: bool | None = None


class ReinvestSettingsOut(BaseModel):
    discount_pct: str  # admin-configurable reinvest_discount_pct (server-authoritative)
