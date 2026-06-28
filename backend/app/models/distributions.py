"""Returns & distributions models (Phase 6) — DDL owned by alembic/0007.

``distributions`` records one payout run per (property, period). UNIQUE(property_id,
period_key) makes a re-run of the same period impossible (idempotency). Each
``distribution_items`` row is the audit of one investor's share — gross (pro-rata by
units, Hamilton largest-remainder), the withheld management fee (snapshot rate), and
the net credited to their wallet. UNIQUE(distribution_id, user_id) prevents any
investor being paid twice within a run.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOW = func.now()


class Distribution(Base):
    __tablename__ = "distributions"
    __table_args__ = (
        UniqueConstraint("property_id", "period_key", name="distributions_property_period_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="rental")
    period_key: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    period_end: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    gross_pool: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    total_net: Mapped[decimal.Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    total_management_fee: Mapped[decimal.Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))


class DistributionItem(Base):
    __tablename__ = "distribution_items"
    __table_args__ = (
        UniqueConstraint("distribution_id", "user_id", name="distribution_items_dist_user_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    distribution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("distributions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    management_fee: Mapped[decimal.Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    net_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
