"""Messages from the platform team to users (client, 2026-10-28) — DDL owned by alembic/0039.

The team writes a message in the admin panel to one user or to everyone holding a role; each
recipient gets a ``PlatformMessage`` in their inbox (/messages), a notification and an email.
See ``message_service``.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOW = func.now()


class MessageTemplate(Base):
    __tablename__ = "message_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW, onupdate=_NOW
    )

    def __str__(self) -> str:
        return self.name


class MessageBroadcast(Base):
    __tablename__ = "message_broadcasts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    audience: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    send_email: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("message_templates.id", ondelete="SET NULL")
    )
    client_token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    recipients: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    emails_queued: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )

    def __str__(self) -> str:
        return self.subject


class PlatformMessage(Base):
    __tablename__ = "platform_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    broadcast_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("message_broadcasts.id", ondelete="SET NULL")
    )
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    read_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    # queued (see the outbox row for sent / failed), opted_out, no_email
    email_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="no_email")
    email_outbox_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_outbox.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
