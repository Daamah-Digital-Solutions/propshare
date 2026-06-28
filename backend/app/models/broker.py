"""Broker referral & commission models (Phase 11) — DDL owned by alembic/0012.

* ``BrokerCode``       — one server-generated shareable code per broker.
* ``BrokerReferral``   — the first-class broker↔client link. ``client_id`` is UNIQUE
  and the link is created ONLY on the signup path (never retroactively), so a client
  who signed up without a broker code stays broker-less permanently.
* ``BrokerCommission`` — append-only accrual/credit ledger. ``UNIQUE(revenue_event_type,
  revenue_event_id)`` makes one platform-revenue event yield at most one accrual; the
  ``commission_amount <= revenue_amount`` CHECK is the structural guarantee that a
  broker can never be paid more than the platform earned from that client; the
  ``commission_rate`` is snapshotted per row so an admin rate change never rewrites
  history.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

_NOW = func.now()


class BrokerCode(Base):
    __tablename__ = "broker_codes"
    __table_args__ = (
        UniqueConstraint("broker_id", name="broker_codes_broker_id_key"),
        UniqueConstraint("code", name="broker_codes_code_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    broker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    broker = relationship(
        "User",
        primaryjoin="foreign(BrokerCode.broker_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )


class BrokerReferral(Base):
    __tablename__ = "broker_referrals"
    __table_args__ = (
        UniqueConstraint("client_id", name="broker_referrals_client_id_key"),
        CheckConstraint("broker_id <> client_id", name="broker_referrals_no_self"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    broker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    code_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("broker_codes.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    broker = relationship(
        "User",
        primaryjoin="foreign(BrokerReferral.broker_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )
    client = relationship(
        "User",
        primaryjoin="foreign(BrokerReferral.client_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )


class BrokerCommission(Base):
    __tablename__ = "broker_commissions"
    __table_args__ = (
        UniqueConstraint(
            "revenue_event_type", "revenue_event_id", name="broker_commissions_event_key"
        ),
        CheckConstraint("commission_amount >= 0", name="broker_commissions_amount_non_negative"),
        CheckConstraint("commission_amount <= revenue_amount", name="broker_commissions_cap"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    broker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    referral_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("broker_referrals.id", ondelete="CASCADE"), nullable=False
    )
    # v1: 'investment_platform_fee' (Phase 5) | 'distribution_mgmt_fee' (Phase 6).
    revenue_event_type: Mapped[str] = mapped_column(Text, nullable=False)
    # investments.id OR distribution_items.id — the first-class revenue fact.
    revenue_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revenue_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    commission_rate: Mapped[decimal.Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    commission_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    broker = relationship(
        "User",
        primaryjoin="foreign(BrokerCommission.broker_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )
    client = relationship(
        "User",
        primaryjoin="foreign(BrokerCommission.client_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )
