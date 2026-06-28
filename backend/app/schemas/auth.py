"""Auth DTOs."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    referral_code: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    """Access token only. The refresh token is delivered via an httpOnly cookie."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class WalletSummary(BaseModel):
    balance: str
    pending_balance: str
    total_invested: str
    total_returns: str


class MeOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    phone: str | None
    email_verified: bool
    roles: list[str]
    active_role: str | None
    kyc_status: str
    wallet: WalletSummary


class SwitchRoleIn(BaseModel):
    role: str


class RequestRoleIn(BaseModel):
    role: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class VerifyEmailIn(BaseModel):
    token: str


class OAuthCallbackIn(BaseModel):
    """SPA posts the provider's authorization code + redirect_uri it used."""

    code: str
    redirect_uri: str
