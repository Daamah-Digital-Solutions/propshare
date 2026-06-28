"""Saved payment methods (Group 3) — DDL owned by alembic/0017.

PCI-safe: only TOKENS (Stripe customer id + payment_method id) and safe display metadata
(brand/last4/exp) are stored — never raw card data. Raw card entry happens client-side via
a Stripe SetupIntent.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOW = func.now()


class PaymentCustomer(Base):
    __tablename__ = "payment_customers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="stripe")
    customer_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class SavedPaymentMethod(Base):
    __tablename__ = "saved_payment_methods"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_payment_method_id",
            name="saved_payment_methods_provider_pm_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="stripe")
    provider_customer_id: Mapped[str | None] = mapped_column(Text)
    provider_payment_method_id: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False, server_default="card")
    brand: Mapped[str | None] = mapped_column(Text)
    last4: Mapped[str | None] = mapped_column(Text)
    exp_month: Mapped[int | None] = mapped_column(Integer)
    exp_year: Mapped[int | None] = mapped_column(Integer)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
