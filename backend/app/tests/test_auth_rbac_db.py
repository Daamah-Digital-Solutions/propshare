"""DB-backed RBAC gate tests (the security-critical behaviors the Phase-1 plan
named as must-pass). These complement the DB-free unit tests by exercising the
real Postgres path end-to-end via the app."""

from __future__ import annotations

import pytest

PW = "Passw0rd!23"
PROP = {
    "title": "Gate Tower",
    "property_type": "apartment",
    "location": "Dubai, UAE",
    "total_value": 1000000,
    "unit_price": 100,
}


async def _register(client, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "T"}
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_switch_role_to_unauthorized_is_403(client):
    """A fresh investor cannot switch to a role they don't hold — server-enforced."""
    tok = await _register(client, "switch@ex.com")
    r = await client.post(
        "/api/v1/auth/switch-role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "ROLE_NOT_AUTHORIZED"


@pytest.mark.asyncio
async def test_register_provisions_profile_wallet_kyc_atomically(client, db):
    """register() creates the user + profile + wallet + kyc + investor role in one tx."""
    await _register(client, "prov@ex.com")
    uid = db("SELECT id FROM users WHERE email=:e", e="prov@ex.com")[0][0]
    assert db("SELECT count(*) FROM profiles WHERE id=:i", i=uid)[0][0] == 1
    assert db("SELECT count(*) FROM wallets WHERE user_id=:i", i=uid)[0][0] == 1
    assert db("SELECT count(*) FROM kyc_verifications WHERE user_id=:i", i=uid)[0][0] == 1
    assert (
        db("SELECT count(*) FROM user_roles WHERE user_id=:i AND role='investor'", i=uid)[0][0] == 1
    )


@pytest.mark.asyncio
async def test_register_rolls_back_fully_on_provision_failure(client, db, monkeypatch):
    """If provisioning fails mid-transaction, NOTHING persists (no orphan user)."""
    from app.services import auth_service

    async def boom(session, user):  # noqa: ANN001
        raise RuntimeError("provision failed")

    monkeypatch.setattr(auth_service, "_provision_new_user", boom)
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "rollback@ex.com", "password": PW, "full_name": "T"},
    )
    assert r.status_code >= 500
    assert db("SELECT count(*) FROM users WHERE email=:e", e="rollback@ex.com")[0][0] == 0
    # the user is flushed before provisioning; a full rollback leaves zero rows everywhere
    assert db("SELECT count(*) FROM profiles")[0][0] == 0
    assert db("SELECT count(*) FROM wallets")[0][0] == 0


@pytest.mark.asyncio
async def test_revoked_role_within_valid_ttl_is_refused(client, db):
    """require_active_role_db beats a still-valid token: revoke the role in the DB
    and the SAME unexpired token can no longer perform the owner action."""
    await _register(client, "owner@ex.com")
    uid = db("SELECT id FROM users WHERE email=:e", e="owner@ex.com")[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i, 'owner')", i=uid)
    db("UPDATE users SET active_role='owner' WHERE id=:i", i=uid)
    # login AFTER the grant so the token carries active_role=owner
    login = await client.post("/api/v1/auth/login", json={"email": "owner@ex.com", "password": PW})
    owner_tok = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {owner_tok}"}

    ok = await client.post("/api/v1/properties", json=PROP, headers=headers)
    assert ok.status_code == 201, ok.text  # owner action works while role is held

    db("DELETE FROM user_roles WHERE user_id=:i AND role='owner'", i=uid)  # revoke, keep token
    refused = await client.post("/api/v1/properties", json=PROP, headers=headers)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "ROLE_REVOKED"
