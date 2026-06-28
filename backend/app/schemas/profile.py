"""Profile / account-settings DTOs."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class ProfileOut(BaseModel):
    id: uuid.UUID
    email: EmailStr | None
    full_name: str | None
    phone: str | None
    avatar_url: str | None


class ProfileUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
