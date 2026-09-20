"""AI-assistant conversations, messages, proposed actions and consent (plan Phase 1).

DDL is owned by ``alembic/versions/0026_assistant.py``; nothing is created from here.

The message content columns are ciphertext in the database: the ``Encrypted*`` column types
encrypt on write and decrypt on read, so a dump or a nightly backup never contains readable
conversations. ``usage`` holds token counts only.

An action the model proposes is NOT an action taken: a proposal row is created with a
one-time token (only its hash is stored) that the user's own confirmation call must present.
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedJSON, EncryptedText
from app.models.base import Base

_NOW = func.now()


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # NULL user_id = visitor (not signed in); visitor_key groups their turns.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    visitor_key: Mapped[str | None] = mapped_column(Text)
    active_role: Mapped[str | None] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(Text, nullable=False, server_default="en")
    title: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_cached_input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    total_output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_reasoning_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    est_cost_usd: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, server_default="0"
    )
    model: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_NOW
    )
    last_message_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # user | assistant | system_note
    # --- encrypted at rest (AES-256-GCM, key id embedded in the blob) ---
    text: Mapped[str | None] = mapped_column("text_enc", EncryptedText)
    content: Mapped[object | None] = mapped_column("content_enc", EncryptedJSON)
    tool_calls: Mapped[object | None] = mapped_column("tool_calls_enc", EncryptedJSON)
    cards: Mapped[object | None] = mapped_column("cards_enc", EncryptedJSON)
    enc_key_id: Mapped[str | None] = mapped_column(Text)
    # counts only — never content
    usage: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    first_token_ms: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[str | None] = mapped_column(Text)
    guardrail_flags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    feedback: Mapped[str | None] = mapped_column(Text)
    lang: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_NOW
    )


class AssistantActionProposal(Base):
    __tablename__ = "assistant_action_proposals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assistant_messages.id", ondelete="SET NULL")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    summary: Mapped[str | None] = mapped_column(Text)
    # only the HASH of the one-time confirmation token is stored; the model never sees it
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="awaiting_user_confirmation"
    )
    result: Mapped[dict | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_NOW
    )
    decided_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))


class AssistantConsent(Base):
    __tablename__ = "assistant_consents"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    policy_version: Mapped[str] = mapped_column(Text, primary_key=True)
    accepted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_NOW
    )
    ip: Mapped[str | None] = mapped_column(Text)


__all__ = [
    "AssistantActionProposal",
    "AssistantConsent",
    "AssistantConversation",
    "AssistantMessage",
]
