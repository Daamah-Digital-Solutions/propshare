"""Liquidity-provider models (Phase 9) — DDL owned by alembic/0010.

* ``LpPoolTier`` — admin-editable PASSIVE config (term + fixed APY + minimum).
* ``LpExitRequest`` — the seller-side instant-buyout order book. The pricing
  columns are an AUTHORITATIVE snapshot locked at creation (what the seller
  receives); the fill only band-checks them, never changes them.
* ``LpPosition`` — THE never-commingle table: one classified row per committed LP
  principal. ``classification`` is single-valued (CHECK active|passive) and
  cross-field CHECKs force the opposite product's columns NULL, so a row is
  structurally one product only. For ACTIVE it is an append-only acquisition/audit
  record — current holdings always come from ``ownership_ledger``, never from here.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

_NOW = func.now()


class LpPoolTier(Base):
    __tablename__ = "lp_pool_tiers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    period_months: Mapped[int] = mapped_column(Integer, nullable=False)
    apy_pct: Mapped[decimal.Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    min_amount: Mapped[decimal.Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class LpExitRequest(Base):
    __tablename__ = "lp_exit_requests"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="lp_exit_requests_idempotency_key_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    units_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    # AUTHORITATIVE snapshot — locked at creation, used verbatim for the seller payout.
    unit_price_snapshot: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    discount_pct_snapshot: Mapped[decimal.Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    fee_pct_snapshot: Mapped[decimal.Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    gross: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    lp_price: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    liquidity_fee: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    seller_net: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    filled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    seller = relationship(
        "User",
        primaryjoin="foreign(LpExitRequest.seller_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )


class LpPosition(Base):
    __tablename__ = "lp_positions"
    __table_args__ = (UniqueConstraint("idempotency_key", name="lp_positions_idempotency_key_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    lp_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    classification: Mapped[str] = mapped_column(Text, nullable=False)  # active | passive
    principal_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    closed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    # ACTIVE-only (acquisition/audit; holdings live in ownership_ledger)
    exit_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lp_exit_requests.id", ondelete="SET NULL")
    )
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE")
    )
    units: Mapped[int | None] = mapped_column(Integer)
    unit_price_snapshot: Mapped[decimal.Decimal | None] = mapped_column(Numeric(15, 2))
    discount_pct: Mapped[decimal.Decimal | None] = mapped_column(Numeric(6, 3))
    spread_at_entry: Mapped[decimal.Decimal | None] = mapped_column(Numeric(15, 2))
    # PASSIVE-only
    pool_tier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lp_pool_tiers.id", ondelete="SET NULL")
    )
    apy_pct_snapshot: Mapped[decimal.Decimal | None] = mapped_column(Numeric(6, 3))
    term_months: Mapped[int | None] = mapped_column(Integer)
    maturity_date: Mapped[datetime.date | None] = mapped_column(Date)
    accrued_amount: Mapped[decimal.Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    lp_user = relationship(
        "User",
        primaryjoin="foreign(LpPosition.lp_user_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )
