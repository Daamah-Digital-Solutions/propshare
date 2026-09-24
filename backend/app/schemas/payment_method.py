"""Saved payment-method DTOs (Group 3).

Only safe display metadata is returned — never the Stripe tokens or any card data.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class SavedPaymentMethodOut(BaseModel):
    id: uuid.UUID
    type: str
    brand: str | None
    last4: str | None
    exp_month: int | None
    exp_year: int | None
    is_default: bool
    created_at: dt.datetime


class SetupIntentOut(BaseModel):
    client_secret: str
    publishable_key: str


class AddPaymentMethodIn(BaseModel):
    # The finished SetupIntent (seti_...) from Stripe's card form. The server reads the card it
    # saved from Stripe itself; the browser never names a payment method.
    setup_intent_id: str = Field(pattern=r"^seti_[A-Za-z0-9]{6,120}$")
