"""Inbox of messages from the platform team (client, 2026-10-28)."""

from __future__ import annotations

import datetime

from pydantic import BaseModel


class InboxMessageOut(BaseModel):
    id: str
    subject: str
    preview: str
    read: bool
    created_at: datetime.datetime
    body: str | None = None


class InboxOut(BaseModel):
    items: list[InboxMessageOut]
    unread: int


class ReadAllOut(BaseModel):
    marked: int
