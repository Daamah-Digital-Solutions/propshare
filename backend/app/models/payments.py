"""Payment models (Phase 4) — DDL owned by alembic/0005.

``payments`` is the per-intent record (one row per deposit attempt), keyed for
idempotency on (provider, provider_payment_id) and on idempotency_key.
``payment_events`` is the inbound-webhook dedupe ledger (one row per processed
provider event) — a replayed webhook collides on (provider, event_id) and no-ops.
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOW = func.now()


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id", name="payments_provider_pid_key"),
        UniqueConstraint("idempotency_key", name="payments_idempotency_key_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)  # stripe | nowpayments
    provider_payment_id: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)  # requested
    amount_captured: Mapped[decimal.Decimal | None] = mapped_column(Numeric(15, 2))
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="USD")
    # requires_action | pending | succeeded | failed | cancelled
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    # deposit | investment | installment (an installment plan's down payment, 0032)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, server_default="deposit")
    payment_method: Mapped[str | None] = mapped_column(Text)  # card | crypto | pronova
    related_investment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    related_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("installment_plans.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[object | None] = mapped_column(JSONB)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="payment_events_provider_event_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL")
    )
    type: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class SukukCertificate(Base):
    """A Nova Sukuk certificate an investor submits to pay for a purchase (``investment_id``)
    or an installment plan's down payment (``plan_id``) — DDL owned by alembic/0032.

    No money moves through the platform: staff check the certificate covers ``amount_due``
    and approve (the units become the investor's) or reject it with a reason. An approved
    certificate keeps its ``units`` pledged to Nova Finance — not sellable, transferable or
    exitable — until staff release the pledge (status ``released``).
    """

    __tablename__ = "sukuk_certificates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    investment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investments.id", ondelete="CASCADE")
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("installment_plans.id", ondelete="CASCADE")
    )
    # the units this certificate pays for (and pledges once approved)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_due: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    certificate_no: Mapped[str | None] = mapped_column(Text)
    issuer: Mapped[str | None] = mapped_column(Text)
    certificate_value: Mapped[decimal.Decimal | None] = mapped_column(Numeric(15, 2))
    valid_until: Mapped[datetime.date | None] = mapped_column(Date)
    file_key: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    # pending | approved (pledged) | rejected | released (pledge lifted)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    released_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
