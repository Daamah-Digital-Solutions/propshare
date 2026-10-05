"""Secondary-market DTOs (Phase 8). Money as decimal-exact STRINGS, never float.

The client sends only the listing/property + units + price; the SERVER computes the
gross, the buyer-side resale fee and the total charge (server-authoritative).

0034: a listing can offer a whole installment plan POSITION instead of ordinary units. Its
``position`` block is what the buyer needs to decide: what they pay the seller now
(``cash``), what they take over (``remaining_principal`` + ``remaining_fees``, on the dates in
``schedule``) and what the seller has paid. The buyer sends back the ``cash`` they agreed to.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field, model_validator


class ListingCreateIn(BaseModel):
    # ordinary units: property_id + units. An installment position: plan_id (sold whole).
    property_id: uuid.UUID | None = None
    units: int | None = Field(default=None, gt=0, le=10_000_000)
    plan_id: uuid.UUID | None = None
    price_per_unit: float = Field(gt=0, le=1_000_000_000)

    @model_validator(mode="after")
    def _one_kind(self) -> ListingCreateIn:
        if self.plan_id is not None:
            if self.property_id is not None or self.units is not None:
                raise ValueError("an installment position is listed by plan_id alone")
        elif self.property_id is None or self.units is None:
            raise ValueError("send property_id and units, or plan_id")
        return self


class PositionInstallmentOut(BaseModel):
    seq: int
    kind: str
    due_date: dt.date
    base_amount: str
    fee_amount: str
    total_amount: str
    status: str


class PositionOut(BaseModel):
    """An installment plan as a position, valued at ``price`` per unit."""

    plan_id: uuid.UUID
    units: int
    vested_units: int
    locked_price: str  # the unit price the plan was started at
    price: str  # the price per unit the figures below use
    value: str  # units x price
    paid_principal: str
    # the seller's own: the price per unit they got in at, and what they have put in
    # (cash = cost + gain)
    entry_price: str
    cost: str
    remaining_principal: str  # what the holder still pays, on the schedule's dates
    remaining_fees: str  # the plan's installment fee on those payments
    gain: str  # units x (price - entry_price)
    cash: str  # value - remaining_principal: what a buyer pays the seller now
    resale_fee: str  # the buyer-side fee on that cash
    total_now: str  # cash + resale_fee
    installments_left: int
    overdue: int
    next_due: dt.date | None
    schedule: list[PositionInstallmentOut]


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
    # an installment position (sold whole; the buyer takes the plan over)
    plan_id: uuid.UUID | None = None
    position: PositionOut | None = None
    # a position: what the buyer pays the seller now, or what it was sold for
    cash: str | None = None


class ListingListOut(BaseModel):
    items: list[ListingOut]
    total: int


class BuyIn(BaseModel):
    units: int = Field(gt=0, le=10_000_000)
    # an installment position only: the ``cash`` the buyer saw and agreed to pay the seller,
    # and the resale fee shown on top of it
    expected_cash: str | None = Field(default=None, max_length=24)
    expected_fee: str | None = Field(default=None, max_length=24)


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
    # the sale of an installment position: ``gross`` is the cash paid to the seller
    plan_id: uuid.UUID | None = None
    position_value: str | None = None
    paid_principal: str | None = None
    assumed_principal: str | None = None
    assumed_fees: str | None = None


class HoldingOut(BaseModel):
    property_id: str
    title: str | None
    location: str | None
    units: int
    listed_units: int
    # held for Nova Finance until staff release the pledge (0032)
    pledged_units: int = 0
    sellable_units: int
    unit_price: str
    # why units cannot be listed: listed | lp_exit | family_pending | gift |
    # installment_plan | pledged -> units
    held_back: dict[str, int] = {}
    # vested under a running installment plan: sold with the plan as a position
    plan_units: int = 0
    # the price line of the property (0034) and what this holding cost per unit
    launch_price: str | None = None
    price_change_pct: str | None = None
    price_updated_at: dt.datetime | None = None
    average_cost: str | None = None


class HoldingListOut(BaseModel):
    items: list[HoldingOut]
    total: int


class MyPositionOut(PositionOut):
    """One of the caller's running plans as a position they could sell, at the property's
    current unit price. ``blocked``: pledged | lockup | listed (None = can be listed)."""

    property_id: str
    property_title: str | None
    property_location: str | None
    unit_price: str
    listing_id: uuid.UUID | None
    blocked: str | None
    lockup_until: dt.datetime | None


class MyPositionListOut(BaseModel):
    items: list[MyPositionOut]
    total: int


class SecondarySettingsOut(BaseModel):
    resale_fee_pct: str
    lockup_days: int
    price_min_pct: str | None
    price_max_pct: str | None


class CancelOut(BaseModel):
    listing_id: uuid.UUID
    status: str
