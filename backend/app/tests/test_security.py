"""Phase 1 — DB-free unit tests for the security primitives.

These run without Postgres (pure crypto/JWT logic). The DB-backed integration
tests (real register/login/refresh/role-switch + the revoked-role-within-TTL
check) run against Postgres in CI / the owner's docker compose.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_access_token_roundtrip_carries_roles_and_active_role() -> None:
    token = create_access_token(
        user_id="11111111-1111-1111-1111-111111111111",
        roles=["investor", "owner"],
        active_role="owner",
    )
    payload = decode_access_token(token)
    assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
    assert payload["roles"] == ["investor", "owner"]
    assert payload["active_role"] == "owner"
    assert payload["typ"] == "access"


def test_decode_rejects_tampered_token() -> None:
    token = create_access_token(user_id="u", roles=["investor"], active_role="investor")
    with pytest.raises(AppError) as exc:
        decode_access_token(token + "tampered")
    assert exc.value.code in {"TOKEN_INVALID", "TOKEN_EXPIRED"}
    assert exc.value.status_code == 401


def test_decode_rejects_active_role_not_in_roles() -> None:
    # A crafted token claiming an active role outside the authorized set must fail.
    token = create_access_token(user_id="u", roles=["investor"], active_role="admin")
    with pytest.raises(AppError) as exc:
        decode_access_token(token)
    assert exc.value.code == "TOKEN_INVALID"


def test_decode_rejects_expired_token() -> None:
    past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)
    token = create_access_token(user_id="u", roles=["investor"], active_role="investor", now=past)
    with pytest.raises(AppError) as exc:
        decode_access_token(token)
    assert exc.value.code == "TOKEN_EXPIRED"


def test_opaque_token_hash_is_deterministic_and_hides_raw() -> None:
    raw = new_opaque_token()
    assert hash_token(raw) == hash_token(raw)
    assert raw not in hash_token(raw)
    assert len(hash_token(raw)) == 64  # sha256 hex
