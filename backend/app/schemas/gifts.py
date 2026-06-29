"""Inter-vivos gifting DTOs (Group 5).

Asset scope: only ``property_shares`` + ``wallet`` are accepted (REAL backings). The UI's
other options (passive_income / rental_returns / tokenized / allocation) are honest-disabled
client-side and rejected here — they have no real source to move.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

GiftAsset = Literal["property_shares", "wallet"]


class GiftScheduleIn(BaseModel):
    recipient_name: str = Field(min_length=1, max_length=200)
    recipient_email: str | None = None
    asset_type: GiftAsset
    property_id: uuid.UUID | None = None
    units: int | None = Field(default=None, ge=1)
    amount: Decimal | None = Field(default=None, gt=0)
    occasion: str | None = None
    message: str | None = None
    scheduled_for: dt.date
    recurring: bool = False
    recurrence_end: dt.date | None = None

    @model_validator(mode="after")
    def _check_asset(self) -> GiftScheduleIn:
        if self.asset_type == "property_shares":
            if self.property_id is None or self.units is None:
                raise ValueError("property_shares gifts require property_id and units.")
        elif self.asset_type == "wallet":
            if self.amount is None:
                raise ValueError("wallet gifts require amount.")
        return self


class GiftOut(BaseModel):
    id: uuid.UUID
    recipient_name: str
    recipient_email: str | None
    is_user: bool
    asset_type: str
    property_id: uuid.UUID | None
    units: int | None
    amount: str | None
    occasion: str | None
    message: str | None
    scheduled_for: dt.date
    recurring: bool
    recurrence_end: dt.date | None
    status: str
    failure_reason: str | None
    created_at: dt.datetime


class GiftRunOut(BaseModel):
    reminders_sent: int
    executed: int
    pending: int
    failed: int
