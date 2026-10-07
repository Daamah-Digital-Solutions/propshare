"""Wallet & deposit DTOs (Phase 4).

Money is returned as STRINGS (decimal-exact) — never float. Deposit amounts the
client sends are the *requested* amount; the credited amount is whatever the
provider webhook reports as captured (server-authoritative).
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class WalletOut(BaseModel):
    balance: str
    pending_balance: str
    total_invested: str
    total_returns: str
    currency: str


class TransactionOut(BaseModel):
    id: uuid.UUID
    type: str
    amount: str
    status: str
    description: str | None
    payment_method: str | None
    reference_id: uuid.UUID | None
    created_at: dt.datetime


class TransactionListOut(BaseModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int


class DepositIn(BaseModel):
    amount: float = Field(gt=0, le=1_000_000_000)
    method: str = Field(pattern="^(card|crypto)$")
    # crypto: the coin the member chose to pay in, a code of GET /payments/crypto/coins
    # ("usdtbsc"); the invoice is made for that coin
    pay_currency: str | None = Field(default=None, pattern="^[A-Za-z0-9]{2,24}$")


class CryptoCoinOut(BaseModel):
    code: str  # what a payment is made for, e.g. "usdtbsc"
    ticker: str
    name: str  # NOWPayments' name, the network in it for a token: "Tether USD (Tron)"
    network: str | None
    stable: bool
    popular: bool
    memo: bool  # paying it needs a memo / tag as well as the address


class CryptoCoinsOut(BaseModel):
    items: list[CryptoCoinOut]
    total: int


class CryptoMinimumOut(BaseModel):
    """The smallest payment one coin takes right now (it moves with the network's fees)."""

    coin: str
    minimum: str | None  # in ``currency``; None when the provider does not say
    currency: str


class OpenCryptoPaymentOut(BaseModel):
    """A crypto payment the member started and that has not settled yet."""

    id: uuid.UUID
    purpose: str  # deposit | investment | installment
    amount: str
    currency: str
    coin: str | None  # the coin chosen, when known
    stage: str  # awaiting_transfer | confirming
    checkout_url: str | None  # the page to finish it on
    created_at: dt.datetime
    title: str | None  # the property, for a purchase or a down payment


class DepositOut(BaseModel):
    payment_id: uuid.UUID
    provider: str
    status: str
    checkout_url: str | None  # hosted checkout to redirect to


class DepositMethodsOut(BaseModel):
    """Which deposit rails are LIVE right now, so the SPA can reflect availability
    upfront instead of surprising the user with a 503 after they try. Card->Stripe,
    crypto->NOWPayments flip on the moment their keys are set on the server; bank is
    live whenever the platform has at least one active receiving account."""

    card: bool
    crypto: bool
    bank: bool


class PaymentStatusOut(BaseModel):
    id: uuid.UUID
    provider: str
    status: str
    amount: str
    amount_captured: str | None
    created_at: dt.datetime
