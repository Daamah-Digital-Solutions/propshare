"""Inter-vivos gifting model (Group 5) — DDL owned by alembic/0019.

A ``scheduled_gift`` is a future, optionally-recurring transfer that backs the gifting UI's
real promises: it RESERVES the gifted units (property-share gifts, via the shared
``reserved_units`` rule) or ESCROWS the cash (wallet gifts, via a real wallet debit) at
schedule time, and a cron executes it on ``scheduled_for`` (REAL recipient → atomic move;
non-user recipient → PENDING, materializes on KYC like Phase-10 family / Group-4 estate).
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOW = func.now()


class ScheduledGift(Base):
    __tablename__ = "scheduled_gifts"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('property_shares','wallet')",
            name="scheduled_gifts_asset_check",
        ),
        CheckConstraint(
            "(units IS NOT NULL AND units > 0) OR (amount IS NOT NULL AND amount > 0)",
            name="scheduled_gifts_amount_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    giver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    recipient_email: Mapped[str | None] = mapped_column(Text)
    recipient_name: Mapped[str] = mapped_column(Text, nullable=False)
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)  # property_shares | wallet
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="SET NULL")
    )
    units: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[decimal.Decimal | None] = mapped_column(Numeric(18, 2))
    occasion: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    scheduled_for: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    recurrence_end: Mapped[datetime.date | None] = mapped_column(Date)
    series_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # scheduled | pending (executed-on-date, awaiting recipient KYC) | executed | cancelled | failed
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="scheduled")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    reminder_sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    materialized_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
