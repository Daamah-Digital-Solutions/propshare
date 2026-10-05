"""The history of a listing's unit price after launch (0034) — DDL owned by alembic/0034.

``properties.unit_price`` is the CURRENT price: what a new buyer pays, the guide price of the
secondary market, the price of a liquidity-provider exit and what a holding is valued at.
Staff record a new price for a property under construction each month and at each sales
phase; every change is one append-only row here (the price before it and the new one), so
the price an investor bought at, sold at, or is shown on a chart can always be traced.
A listing that never changed price has no rows: its history is its launch price.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOW = func.now()


class PropertyPrice(Base):
    __tablename__ = "property_prices"
    __table_args__ = (
        CheckConstraint("price > 0", name="property_prices_price_check"),
        CheckConstraint("previous_price > 0", name="property_prices_previous_price_check"),
        CheckConstraint("price <> previous_price", name="property_prices_check"),
        Index("property_prices_property_idx", "property_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    previous_price: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    price: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # a sales phase or stage this price opens ("Phase 2"), when it is one
    label: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_NOW
    )
