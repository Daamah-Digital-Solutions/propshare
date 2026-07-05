"""Installment plans model (Group 6) — DDL owned by alembic/0020.

Progressive-vesting purchase of an under-construction property: the investor commits to
``units_total`` units at a locked ``unit_price`` and pays a down payment + N monthly
installments. Ownership vests into ``ownership_ledger`` proportionally per PAID payment
(``vest_units`` on each ``InstallmentPayment``); full ownership + rental-yield eligibility
transfer at the final payment (handover). The fee is snapshotted at creation.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from sqlalchemy import (
    CheckConstraint,
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


class InstallmentPlan(Base):
    __tablename__ = "installment_plans"
    __table_args__ = (
        CheckConstraint("units_total > 0", name="installment_plans_units_check"),
        CheckConstraint(
            "vested_units >= 0 AND vested_units <= units_total",
            name="installment_plans_vested_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    investor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    units_total: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    down_payment_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_months: Mapped[int] = mapped_column(Integer, nullable=False)
    fee_rate: Mapped[decimal.Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    management_fee_rate: Mapped[decimal.Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    vested_units: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class InstallmentPayment(Base):
    __tablename__ = "installment_payments"
    __table_args__ = (
        UniqueConstraint("plan_id", "seq", name="installment_payments_plan_seq_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("installment_plans.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # 0 = down payment
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # downpayment | installment | final
    due_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    base_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    fee_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    vest_units: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="scheduled")
    paid_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
