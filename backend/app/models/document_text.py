"""Extracted text of a property document (assistant document search, Batch D).

DDL is owned by ``alembic/versions/0027_document_texts.py``. One row per indexed document;
``status`` says whether text was found (``indexed``), the file had none (``empty``, e.g. a
scanned image), the type is not extractable (``unsupported``) or extraction failed.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DocumentText(Base):
    __tablename__ = "document_texts"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="indexed")
    pages: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    chars: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    error: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["DocumentText"]
