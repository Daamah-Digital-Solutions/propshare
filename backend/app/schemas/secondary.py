"""Secondary-market DTOs (Phase 8). Money as decimal-exact STRINGS, never float.

The client sends only the listing/property + units + price; the SERVER computes the
gross, the buyer-side resale fee and the total charge (server-authoritative).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ListingCreateIn(BaseModel):
    property_id: uuid.UUID
    units: int = Field(gt=0, le=10_000_000)
    price_per_unit: float = Field(gt=0, le=1_000_000_000)


class ListingOut(BaseModel):
    listing_id: uuid.UUID
    property_id: str | None
    property_title: str | None
    property_location: str | None
    seller_id: str
    units_for_sale: int
    units_remaining: int
    price_per_unit: str
    unit_price_ref: str | None
    status: str
    created_at: str | None


class ListingListOut(BaseModel):
    items: list[ListingOut]
    total: int


class BuyIn(BaseModel):
    units: int = Field(gt=0, le=10_000_000)


class TradeOut(BaseModel):
    trade_id: uuid.UUID
    listing_id: uuid.UUID
    property_id: str
    units: int
    price_per_unit: str
    gross: str
    resale_fee: str
    total_charged: str
    created_at: str | None


class HoldingOut(BaseModel):
    property_id: str
    title: str | None
    location: str | None
    units: int
    listed_units: int
    sellable_units: int
    unit_price: str


class HoldingListOut(BaseModel):
    items: list[HoldingOut]
    total: int


class SecondarySettingsOut(BaseModel):
    resale_fee_pct: str
    lockup_days: int
    price_min_pct: str | None
    price_max_pct: str | None


class CancelOut(BaseModel):
    listing_id: uuid.UUID
    status: str
