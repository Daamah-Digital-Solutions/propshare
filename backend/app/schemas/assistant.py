"""Request/response shapes for the assistant and support-ticket routes (plan Phase 1)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StatusOut(BaseModel):
    enabled: bool
    reason: str | None  # why it is not usable for THIS caller, when enabled is False
    provider: str
    model_configured: bool
    encryption: Literal["ok", "missing"]
    policy_version: str
    consent_required: bool
    consent_given: bool
    visitor_allowed: bool
    rollout: str
    reply_language: str = "auto"  # "en": the widget stays in English


class ConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_version: str = Field(min_length=1, max_length=32)


class ConsentOut(BaseModel):
    policy_version: str
    accepted_at: dt.datetime


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    lang: str
    message_count: int
    created_at: dt.datetime
    last_message_at: dt.datetime | None


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4000)
    lang: Literal["en", "ar"] = "en"


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    text: str | None
    cards: list[dict[str, Any]]
    confidence: str | None
    feedback: str | None
    created_at: dt.datetime


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=16, max_length=128)


class ProposalOut(BaseModel):
    id: uuid.UUID
    action: str
    status: str
    summary: str | None
    result: dict[str, Any] | None
    decided_at: dt.datetime | None


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback: Literal["up", "down"]


class MaintenanceOut(BaseModel):
    purged: int | None = None
    reencrypted: int | None = None
    remaining: int | None = None
    active_key: str | None = None


# --- support tickets --------------------------------------------------------------------- #
class TicketCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(min_length=1, max_length=32)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    priority: Literal["normal", "high"] = "normal"
    contact_email: EmailStr | None = None  # visitors only


class TicketMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)


class CsatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int = Field(ge=1, le=5)


class TicketMessageOut(BaseModel):
    id: uuid.UUID
    author_type: str
    body: str
    created_at: dt.datetime


class TicketOut(BaseModel):
    id: uuid.UUID
    ticket_no: str
    category: str | None
    priority: str
    status: str
    subject: str | None
    source: str
    created_at: dt.datetime
    updated_at: dt.datetime
    resolved_at: dt.datetime | None
    csat: int | None = None
    messages: list[TicketMessageOut] = Field(default_factory=list)
