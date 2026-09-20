"""Support tickets and their thread (plan Phase 1, §3/§4).

DDL is owned by ``alembic/versions/0026_assistant.py``.

Tickets are staff-facing and therefore plaintext. By design they never carry conversation
text: the assistant fills ``summary`` from a structured handoff object (category, reference
ids, attempted actions, account facts) and ``context`` with the same data as JSON. Staff who
need the actual conversation open the admin transcript view, which decrypts on demand and
writes an audit row.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, FetchedValue, ForeignKey, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOW = func.now()


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # human reference (CPX-001001...). The DEFAULT lives in the database (a sequence), so the
    # ORM must never send this column and must read it back after the insert.
    ticket_no: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, server_default=FetchedValue()
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="support")
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    contact_email: Mapped[str | None] = mapped_column(Text)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assistant_conversations.id", ondelete="SET NULL")
    )
    category: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text, nullable=False, server_default="normal")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    subject: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)  # structured handoff, never chat text
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="assistant")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_NOW
    )
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    csat: Mapped[int | None] = mapped_column(SmallInteger)


class SupportTicketMessage(Base):
    __tablename__ = "support_ticket_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False
    )
    author_type: Mapped[str] = mapped_column(Text, nullable=False)  # user | staff | system
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # internal notes are for staff only and are never returned to the ticket owner
    internal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_NOW
    )


__all__ = ["SupportTicket", "SupportTicketMessage"]
