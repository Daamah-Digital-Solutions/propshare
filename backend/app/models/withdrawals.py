"""Withdrawal / payout models (Phase 7) — DDL owned by alembic/0008.

``withdrawals`` is the money-out lifecycle record; UNIQUE(idempotency_key) stops a
request replay from creating a second hold. ``payout_events`` dedupes settlement
webhooks (UNIQUE(provider, event_id)). ``connect_accounts`` tracks each investor's
Stripe Connect onboarding state — bank payouts are gated on a payouts-enabled
account. Destinations are tokenized refs only (Connect account id / crypto address),
never raw bank PII.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

_NOW = func.now()


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    __table_args__ = (UniqueConstraint("idempotency_key", name="withdrawals_idempotency_key_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)  # bank | crypto
    provider: Mapped[str] = mapped_column(Text, nullable=False)  # stripe | nowpayments
    destination: Mapped[object] = mapped_column(JSONB, nullable=False, server_default="{}")
    # pending_review | approved | processing | completed | failed | returned | rejected
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending_review")
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    provider_payout_id: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    user = relationship(
        "User",
        primaryjoin="foreign(Withdrawal.user_id) == User.id",
        viewonly=True,
        lazy="selectin",
    )


class PayoutEvent(Base):
    __tablename__ = "payout_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="payout_events_provider_event_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    withdrawal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("withdrawals.id", ondelete="SET NULL")
    )
    type: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class ConnectAccount(Base):
    __tablename__ = "connect_accounts"
    __table_args__ = (UniqueConstraint("user_id", name="connect_accounts_user_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    stripe_account_id: Mapped[str | None] = mapped_column(Text)
    payouts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    details_submitted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="none")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
