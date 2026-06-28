"""Investment-engine models (Phase 5) — DDL owned by alembic/0006.

``platform_settings`` is the admin-configurable key/value store the fee logic
READS (never hardcoded constants): ``platform_fee_pct`` (charged at purchase) and
``management_fee_pct`` (annual, charged in Phase 6).

``ownership_ledger`` is the append-only record of unit movements — one row per
purchase (and, later, per transfer/sale). It is the source of truth for unit
ownership; ``properties.available_units`` is the fast running counter guarded by
``SELECT ... FOR UPDATE`` + a DB CHECK.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOW = func.now()


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class OwnershipLedger(Base):
    __tablename__ = "ownership_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    investment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investments.id", ondelete="SET NULL")
    )
    units: Mapped[int] = mapped_column(Integer, nullable=False)  # +acquired / -released
    unit_price: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)  # purchase | ...
    # Phase 9 (Decision 2) — the management-fee rate the owner CONSENTED TO, stamped at
    # acquisition. Original investors carry their snapshot rate; LP/secondary-acquired
    # units carry the platform rate at acquisition. Phase-6 derives the rental fee base
    # from this per-row rate (never a global re-derive). NULL on release/legacy rows.
    fee_rate: Mapped[decimal.Decimal | None] = mapped_column(Numeric(6, 3))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
