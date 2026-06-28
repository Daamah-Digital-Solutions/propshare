"""Secondary-market trade model (Phase 8) — DDL owned by alembic/0009.

``secondary_trades`` is the append-only record of executed fills (one row per
purchase against a listing — a listing can be filled partially many times).
UNIQUE(idempotency_key) stops a buyer's request replay from double-buying. The
``secondary_listings`` row (with its units_remaining counter) lives in
app/models/__init__.py alongside the original 0001 table.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

_NOW = func.now()


class SecondaryTrade(Base):
    __tablename__ = "secondary_trades"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="secondary_trades_idempotency_key_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("secondary_listings.id", ondelete="CASCADE"), nullable=False
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    buyer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_unit: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    gross: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    resale_fee: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    total_charged: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    buyer = relationship(
        "User",
        primaryjoin="foreign(SecondaryTrade.buyer_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )
