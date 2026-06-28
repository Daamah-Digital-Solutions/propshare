"""Security primitives: password hashing, access-token (JWT) issue/verify, and
opaque refresh/email token generation + hashing.

Design (Phase 1, owner-mandated):
- Passwords hashed with Argon2id (argon2-cffi).
- Access token = short-TTL JWT carrying ``sub`` (user id), ``roles`` (the
  authorized-role SET) and ``active_role`` (∈ roles). Kept in memory client-side.
- Refresh / email tokens are opaque random strings; only their SHA-256 hash is
  stored server-side, so a DB leak does not reveal usable tokens. The raw refresh
  token travels only in an httpOnly cookie.

This module is pure (no DB / no FastAPI), so it is unit-testable without Postgres.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings
from app.core.errors import AppError

_hasher = PasswordHasher()


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, Exception):  # noqa: BLE001 — any failure == not verified
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hashed)
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# Access token (JWT)
# --------------------------------------------------------------------------- #
def create_access_token(
    *,
    user_id: str,
    roles: list[str],
    active_role: str | None,
    now: dt.datetime | None = None,
) -> str:
    settings = get_settings()
    issued = now or dt.datetime.now(dt.UTC)
    payload: dict[str, Any] = {
        "sub": user_id,
        "roles": roles,
        "active_role": active_role,
        "iat": int(issued.timestamp()),
        "exp": int((issued + dt.timedelta(seconds=settings.access_token_ttl_seconds)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode + validate an access token. Raises AppError(401) on any problem.

    NOTE: this validates the token's *integrity and expiry* only. The active role
    is additionally re-checked against the DB on money/privileged endpoints
    (see api/deps.require_active_role_db) so a revoked role cannot act within a
    still-valid token's TTL.
    """
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError("TOKEN_EXPIRED", "Access token expired", status_code=401) from exc
    except jwt.PyJWTError as exc:
        raise AppError("TOKEN_INVALID", "Invalid access token", status_code=401) from exc

    if payload.get("typ") != "access":
        raise AppError("TOKEN_INVALID", "Wrong token type", status_code=401)
    # active_role must be within the authorized set (defense against a crafted token).
    active = payload.get("active_role")
    roles = payload.get("roles") or []
    if active is not None and active not in roles:
        raise AppError("TOKEN_INVALID", "active_role not in authorized roles", status_code=401)
    return payload


# --------------------------------------------------------------------------- #
# Opaque tokens (refresh + email verify/reset)
# --------------------------------------------------------------------------- #
def new_opaque_token(nbytes: int = 32) -> str:
    """Return a URL-safe random token (the RAW value — store only its hash)."""
    return secrets.token_urlsafe(nbytes)


def hash_token(raw: str) -> str:
    """SHA-256 hex digest used to store/look up opaque tokens."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
