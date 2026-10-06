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
    # "pronova" is a branded rail that settles via Stripe card (D5) with a server-applied
    # discount off the total; otherwise identical to "card".
    method: str = Field(pattern="^(wallet|card|crypto|pronova)$")
    # The unit price on the buyer's screen when they confirmed: a different price now is
    # answered with 409 PRICE_CHANGED instead of a purchase at a price they did not see.
    expected_unit_price: float | None = Field(default=None, gt=0)
    # crypto: the coin the buyer chose to pay in (GET /payments/crypto/coins)
    pay_currency: str | None = Field(default=None, pattern="^[A-Za-z0-9]{2,24}$")


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
    payment_id: uuid.UUID | None = None  # the payment behind a direct-pay checkout


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

    invested: str  # wallet.total_invested (everything bought so far, held or sold since)
    # Σ held units × property.unit_price (from ownership_ledger); a running installment plan
    # counts as its position: all its units at that price less the principal still to pay
    current_value: str
    total_returns: str  # wallet.total_returns
    properties: int  # distinct properties currently held
    units: int  # total units currently held
    # what selling units and positions brought in: current_value + sold - invested = the gain
    sold: str = "0"


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


class PronovaSettingsOut(BaseModel):
    # Live, admin-configurable Pronova pay discount (% off the total payable). The UI shows
    # this real rate; the server applies it to the charged amount at purchase.
    discount_pct: str


class PaymentOptionsOut(BaseModel):
    """The ways to pay for a property (the same on every property) and which are live now."""

    wallet: bool
    card: bool
    apple_pay: bool
    google_pay: bool
    crypto: bool
    pronova: bool
    sukuk: bool
    pronova_discount_pct: str


class SukukCertificateOut(BaseModel):
    """A Nova Sukuk certificate the investor submitted, and where its review stands."""

    certificate_id: uuid.UUID
    kind: str  # purchase | installment (a plan's down payment)
    status: str  # pending | approved (pledged to Nova Finance) | rejected | released
    investment_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    property_id: uuid.UUID
    property_title: str
    property_slug: str | None = None
    units: int
    amount_due: str
    certificate_no: str | None = None
    issuer: str | None = None
    review_note: str | None = None
    created_at: dt.datetime | None = None
    reviewed_at: dt.datetime | None = None
    released_at: dt.datetime | None = None
