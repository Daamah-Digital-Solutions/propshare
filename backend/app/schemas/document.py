"""Document DTOs (Phase: storage/documents)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID | None
    title: str
    type: str
    download_url: str
    created_at: dt.datetime
