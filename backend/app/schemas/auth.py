"""Auth DTOs."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

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
    # Roles the user has a pending approval request for (Task 12 — drives preview access).
    pending_roles: list[str] = []
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


class EmailChangeIn(BaseModel):
    # validated with the sign-up rules in the service (so the assistant's path gets them too)
    new_email: str = Field(min_length=3, max_length=320)


class EmailChangeLinkIn(BaseModel):
    token: str = Field(min_length=10, max_length=256)


class EmailChangeOut(BaseModel):
    """Where a change stands: ``awaiting_approval`` (link sent to the current address, shown
    masked in ``sent_to``), ``awaiting_confirmation`` (link sent to the new one) or
    ``completed``. Addresses are masked."""

    status: str
    new_email: str
    sent_to: str | None = None
    expires_at: dt.datetime | None = None


class EmailChangeStatusOut(BaseModel):
    pending: EmailChangeOut | None


class EmailChangeLinkOut(BaseModel):
    """What a link from the emails is about, before anything happens: the page shows it and
    acts only when the person presses a button. ``new_email`` is in full (the link went to the
    account's owner, or to that address itself); ``account_email`` is masked."""

    step: Literal["approve", "confirm"]
    new_email: str
    account_email: str
    expires_at: dt.datetime


class EmailChangeRejectOut(BaseModel):
    """ "This wasn't me": the change stopped; ``signed_out`` when every device was signed out
    (the link from the current address)."""

    status: str
    signed_out: bool


class OAuthCallbackIn(BaseModel):
    """SPA posts the provider's authorization code + redirect_uri it used, and the broker code
    of the share link that brought the visitor (applied only if this creates a new account)."""

    code: str
    redirect_uri: str
    referral_code: str | None = Field(default=None, max_length=32)


# --------------------------------------------------------------------------- #
# Two-factor authentication
# --------------------------------------------------------------------------- #
class LoginOut(BaseModel):
    """Login / OAuth result. Without 2FA it is exactly ``TokenOut``. With 2FA on, no token is
    issued yet: ``mfa_required`` is true and ``mfa_token`` (5 minutes) must be exchanged at
    ``POST /auth/login/mfa`` together with a code."""

    access_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    mfa_required: bool = False
    mfa_token: str | None = None


class MfaLoginIn(BaseModel):
    mfa_token: str = Field(min_length=10, max_length=512)
    # a 6-digit authenticator code, or a recovery code such as ABCD-EFGH-JKLM-NPQR
    code: str = Field(min_length=6, max_length=32)


class MfaStatusOut(BaseModel):
    has_password: bool
    enabled: bool
    enabled_at: dt.datetime | None
    recovery_codes_remaining: int
    available: bool


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg_data_uri: str
    expires_in: int


class MfaCodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class MfaDisableIn(BaseModel):
    password: str | None = Field(default=None, max_length=128)
    code: str = Field(min_length=6, max_length=32)


class MfaRecoveryCodesOut(BaseModel):
    recovery_codes: list[str]
