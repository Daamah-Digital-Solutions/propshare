"""Investment certificates (client, 2026-10-28) — DDL owned by alembic/0038.

Each row is one certificate issued to a holder for their units in one property, with the secret
code its QR leads to (``/verify/{verification_code}``). See ``certificate_service``.
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


class InvestmentCertificate(Base):
    __tablename__ = "investment_certificates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    verification_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    # valid | superseded (the units changed, or are gone) | revoked (by the platform)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="valid")
    holder_name: Mapped[str] = mapped_column(Text, nullable=False)
    holder_ref: Mapped[str] = mapped_column(Text, nullable=False)  # "Investor ID ****1a2b"
    property_title: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    spv_name: Mapped[str | None] = mapped_column(Text)
    jurisdiction: Mapped[str | None] = mapped_column(Text)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    total_units: Mapped[int | None] = mapped_column(Integer)
    ownership: Mapped[str] = mapped_column(Text, nullable=False)
    unit_price: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    value: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    issued_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_NOW
    )
    superseded_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investment_certificates.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    revocation_reason: Mapped[str | None] = mapped_column(Text)
    verification_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_verified_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
