"""Saved developer profiles (client letter, 2026-11-18) — DDL owned by alembic/0044 and 0046.

One row per developer; ``profile`` is the object a listing keeps in ``content.developer``, and
``versions`` its Arabic and French text ({"ar": {"name", "about", "previousProjects",
"verifications"}, "fr": {...}}), the developer part of a listing's language versions. A new
listing fills its developer card, in every language, from a saved profile; see
``developer_service``.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SavedDeveloper(Base):
    __tablename__ = "saved_developers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    profile: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    versions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
