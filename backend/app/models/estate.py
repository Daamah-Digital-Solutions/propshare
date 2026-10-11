"""Estate / inheritance models (Group 4) — DDL owned by alembic/0018, 0035 and 0036.

Free allocation (owner-set %, not Sharia-enforced; disclaimer shown in the UI) +
manual-admin death verification. REAL/PENDING beneficiary model mirrors Phase-10 family.
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOW = func.now()


class EstateBeneficiary(Base):
    __tablename__ = "estate_beneficiaries"
    __table_args__ = (
        CheckConstraint(
            "allocation_pct >= 0 AND allocation_pct <= 100",
            name="estate_beneficiaries_alloc_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    relationship: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    allocation_pct: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)
    # UI extras (role/scope/trigger/id_type/id_number) so the existing form round-trips
    # with no markup change. PII-at-rest hardening flagged in plan/phase-estate-design.md.
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    beneficiary_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    # 0035 — the number on the person's certificate (and typed into a claim); ``version``
    # counts the changes to what the certificate prints.
    certificate_no: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # copies of the person's identity document the holder uploaded:
    # [{id, key, filename, content_type, size, uploaded_at}] in object storage (never public)
    id_documents: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class EstateEvent(Base):
    __tablename__ = "estate_events"
    __table_args__ = (UniqueConstraint("subject_user_id", name="estate_events_subject_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    subject_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="verified")
    death_certificate_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    verified_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    # 0035 — the claim the execution came from, and what it recorded
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estate_claims.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="death")
    date_of_death: Mapped[datetime.date | None] = mapped_column(Date)
    # 0036 — the wallet balance the percentages were applied to on the day of the event
    wallet_base: Mapped[decimal.Decimal | None] = mapped_column(Numeric(15, 2))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class EstateTransfer(Base):
    __tablename__ = "estate_transfers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    estate_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estate_events.id", ondelete="CASCADE"), nullable=False
    )
    beneficiary_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estate_beneficiaries.id", ondelete="SET NULL")
    )
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="SET NULL")
    )
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    # 0036 — a share of the holder's wallet balance (then: no property, units 0)
    amount: Mapped[decimal.Decimal | None] = mapped_column(Numeric(15, 2))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="completed")
    materialized_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class EstateClaim(Base):
    """A claim on a holder's assets by the person the holder designated (0035): sent from the
    public page with the beneficiary certificate and the claimant's identity document, reviewed
    by staff, and, once approved, executed as a transfer to the claimant's OWN account.

    Statuses: submitted -> in_review -> approved | rejected, with needs_info while staff wait
    for the claimant."""

    __tablename__ = "estate_claims"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    reference: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="submitted")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    claimant_name: Mapped[str] = mapped_column(Text, nullable=False)
    claimant_email: Mapped[str] = mapped_column(Text, nullable=False)
    claimant_phone: Mapped[str | None] = mapped_column(Text)
    claimant_country: Mapped[str] = mapped_column(Text, nullable=False)
    claimant_id_type: Mapped[str | None] = mapped_column(Text)
    claimant_id_number: Mapped[str | None] = mapped_column(Text)
    relationship: Mapped[str | None] = mapped_column(Text)
    claimant_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    holder_name: Mapped[str] = mapped_column(Text, nullable=False)
    holder_email: Mapped[str | None] = mapped_column(Text)
    certificate_no: Mapped[str | None] = mapped_column(Text)
    date_of_death: Mapped[datetime.date | None] = mapped_column(Date)
    details: Mapped[str | None] = mapped_column(Text)
    documents: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    beneficiary_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estate_beneficiaries.id", ondelete="SET NULL")
    )
    estate_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estate_events.id", ondelete="SET NULL")
    )
    admin_note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
