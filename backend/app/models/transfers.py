"""Transfers of property units or wallet balance to another person (client, 2026-10-28) —
DDL owned by alembic/0040. See ``transfer_service``."""

from __future__ import annotations

import datetime
import decimal
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOW = func.now()

OPEN = ("scheduled", "waiting")


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    reference: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    recipient_email: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_name: Mapped[str | None] = mapped_column(Text)
    asset: Mapped[str] = mapped_column(Text, nullable=False)  # units | balance
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id")
    )
    property_title: Mapped[str | None] = mapped_column(Text)
    units: Mapped[int | None] = mapped_column(Integer)
    unit_price: Mapped[decimal.Decimal | None] = mapped_column(Numeric(15, 2))
    # balance: the amount sent; units: their value at the unit price when sent (a record)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    fee: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default="0")
    fee_pct: Mapped[decimal.Decimal] = mapped_column(
        Numeric(6, 3), nullable=False, server_default="0"
    )
    message: Mapped[str | None] = mapped_column(Text)
    occasion: Mapped[str | None] = mapped_column(Text)  # optional: birthday, wedding, ...
    deliver_on: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    # the sender was reminded of a transfer scheduled in the next days
    reminder_sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    # scheduled | waiting | delivered | cancelled | expired | failed
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="scheduled")
    invited_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    closed_reason: Mapped[str | None] = mapped_column(Text)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW, onupdate=_NOW
    )
