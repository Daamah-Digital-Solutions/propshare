"""Notification preferences + email outbox (Phase 12) — DDL owned by alembic/0013.

* ``NotificationPreference`` — per-user EMAIL category toggles. In-app delivery is
  always on (it's the feed); SMS/push are not offered (no delivery mechanism), so they
  are not modelled here. Missing row ⇒ all categories default ON.
* ``EmailOutbox`` — the transactional outbox. A row is written ATOMICALLY with the
  in-app notification inside the originating (often money) transaction; a separate cron
  drainer sends it OUT of that transaction, so a slow/failing email provider can never
  stall or roll back a financial transaction. ``user_id`` is NULL for non-user
  recipients (e.g. a family invitee who hasn't registered yet).
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOW = func.now()


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    email_investment_updates: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    email_returns: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    email_security_alerts: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    email_new_properties: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )


class EmailOutbox(Base):
    __tablename__ = "email_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    to_email: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
