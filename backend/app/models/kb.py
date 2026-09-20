"""Approved knowledge base for the assistant (plan Phase 1, §3/§7).

DDL is owned by ``alembic/versions/0026_assistant.py``.

The agent may only read rows whose ``status`` is ``approved``: a draft article is invisible
to it. Articles are versioned per (slug, lang), so an edit creates a new version and the
approval is an explicit, audited act. Articles carry wording, never live numbers: figures
come from tools that read the real data, so the knowledge base can never go stale about
money.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOW = func.now()


class KbArticle(Base):
    __tablename__ = "kb_articles"
    __table_args__ = (
        UniqueConstraint("slug", "lang", "version", name="kb_articles_slug_lang_version_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str] = mapped_column(Text, nullable=False, server_default="en")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(Text, nullable=False, server_default="all")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    source_ref: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_NOW
    )


__all__ = ["KbArticle"]
