"""Notification + preferences schemas (Phase 12)."""

from __future__ import annotations

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: str
    type: str
    title: str
    message: str
    read: bool
    created_at: str


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int


class UnreadCountOut(BaseModel):
    count: int


class OkOut(BaseModel):
    ok: bool


class MarkAllOut(BaseModel):
    marked: int


class PreferencesOut(BaseModel):
    email_investment_updates: bool
    email_returns: bool
    email_security_alerts: bool
    email_new_properties: bool


class PreferencesIn(BaseModel):
    # Only the email channels we actually deliver are accepted. SMS/push keys (if sent)
    # are ignored — those channels don't exist.
    email_investment_updates: bool | None = None
    email_returns: bool | None = None
    email_security_alerts: bool | None = None
    email_new_properties: bool | None = None


class DispatchOut(BaseModel):
    sent: int
    failed: int
    retried: int
