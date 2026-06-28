"""DB-backed property lifecycle test: owner create -> submit -> admin approve ->
becomes publicly visible; plus the authz boundaries (non-owner can't submit
another's listing; non-admin can't approve)."""

from __future__ import annotations

import pytest

PW = "Passw0rd!23"
PROP = {
    "title": "Flow Tower",
    "property_type": "apartment",
    "location": "Dubai, UAE",
    "total_value": 1000000,
    "unit_price": 100,
}


async def _register(client, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "X"}
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


async def _login(client, email: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return r.json()["access_token"]


async def _owner(client, db, email: str) -> str:
    await _register(client, email)
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i, 'owner')", i=uid)
    db("UPDATE users SET active_role='owner' WHERE id=:i", i=uid)
    return await _login(client, email)


async def _admin(client, db, email: str) -> str:
    await _register(client, email)
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i, 'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    return await _login(client, email)


def _ids(resp) -> list[str]:
    return [i["id"] for i in resp.json()["items"]]


@pytest.mark.asyncio
async def test_create_submit_approve_makes_property_public(client, db):
    owner_tok = await _owner(client, db, "owner@flow.com")
    oh = {"Authorization": f"Bearer {owner_tok}"}

    created = await client.post("/api/v1/properties", json=PROP, headers=oh)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["status"] == "draft"

    submitted = await client.post(f"/api/v1/properties/{pid}/submit", headers=oh)
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "under_review"

    # Not yet public: absent from the list and detail 404 (public = active/funded only).
    assert pid not in _ids(await client.get("/api/v1/properties"))
    assert (await client.get(f"/api/v1/properties/{pid}")).status_code == 404

    admin_tok = await _admin(client, db, "admin@flow.com")
    approved = await client.post(
        f"/api/v1/admin/properties/{pid}/approve",
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "active"

    # Now visible in the marketplace list AND on its detail page.
    assert pid in _ids(await client.get("/api/v1/properties"))
    assert (await client.get(f"/api/v1/properties/{pid}")).status_code == 200

    # The approval is audit-logged.
    assert db("SELECT count(*) FROM audit_log WHERE action='property.approve'")[0][0] == 1


@pytest.mark.asyncio
async def test_authz_non_owner_cannot_submit_and_non_admin_cannot_approve(client, db):
    owner_tok = await _owner(client, db, "o1@flow.com")
    created = await client.post(
        "/api/v1/properties", json=PROP, headers={"Authorization": f"Bearer {owner_tok}"}
    )
    pid = created.json()["id"]

    # A different OWNER cannot submit someone else's property.
    other_owner = await _owner(client, db, "o2@flow.com")
    r = await client.post(
        f"/api/v1/properties/{pid}/submit", headers={"Authorization": f"Bearer {other_owner}"}
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"

    # A non-admin (investor) cannot approve.
    investor_tok = await _register(client, "inv@flow.com")
    r2 = await client.post(
        f"/api/v1/admin/properties/{pid}/approve",
        headers={"Authorization": f"Bearer {investor_tok}"},
    )
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_owner_cannot_edit_once_active(client, db):
    owner_tok = await _owner(client, db, "lock@flow.com")
    oh = {"Authorization": f"Bearer {owner_tok}"}
    pid = (await client.post("/api/v1/properties", json=PROP, headers=oh)).json()["id"]
    db("UPDATE properties SET status='active' WHERE id=:i", i=pid)  # simulate go-live
    r = await client.patch(f"/api/v1/properties/{pid}", json={"title": "Renamed"}, headers=oh)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PROPERTY_LOCKED"
