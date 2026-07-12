"""Task 12 — Broker / Liquidity-Provider role application flow (DB-backed).

Acceptance: an applicant submits the join form (fields + documents) → a pending role request is
created carrying that data; /me reports the role as pending (drives preview access); the admin
sees the application (incl. downloadable documents) and, on approval, the role is GRANTED
(auto-activated). Self-serve roles (owner) are rejected by the application endpoint.
"""

from __future__ import annotations

import json

PW = "Passw0rd!23"


async def _user(client, db, email: str) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "U"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    return r.json()["access_token"], str(uid)


async def _admin(client, db, email: str) -> str:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "A"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return login.json()["access_token"]


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


async def test_broker_application_end_to_end(client, db):
    tok, uid = await _user(client, db, "brk-apply@x.com")
    fields = json.dumps(
        {"full_name": "Broker Bob", "license_number": "LIC-123", "phone": "+100", "country": "UAE"}
    )
    r = await client.post(
        "/api/v1/auth/roles/apply",
        data={"role": "broker", "fields": fields},
        files=[("files", ("license.pdf", b"%PDF-1.4 broker-license", "application/pdf"))],
        headers=_h(tok),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending_approval"

    # a pending request now carries the application data + a stored document
    rows = db(
        "SELECT id, application FROM role_grant_requests WHERE user_id=:u AND role='broker'", u=uid
    )
    assert len(rows) == 1
    req_id, application = rows[0]
    assert application["fields"]["license_number"] == "LIC-123"
    assert len(application["documents"]) == 1

    # /me reports the role as pending (not yet granted) — this drives preview access
    me = (await client.get("/api/v1/auth/me", headers=_h(tok))).json()
    assert "broker" in me["pending_roles"] and "broker" not in me["roles"]

    # the admin sees the application (with fields) and can download the document
    a_tok = await _admin(client, db, "brk-admin@x.com")
    reqs = (await client.get("/api/v1/admin/role-requests", headers=_h(a_tok))).json()
    match = next(x for x in reqs if x["id"] == str(req_id))
    assert match["application"]["fields"]["full_name"] == "Broker Bob"
    doc = await client.get(
        f"/api/v1/admin/role-requests/{req_id}/documents/0/download", headers=_h(a_tok)
    )
    assert doc.status_code == 200 and doc.content == b"%PDF-1.4 broker-license"

    # approval GRANTS the role (auto-activation) and clears the pending state
    dec = await client.post(
        f"/api/v1/admin/role-requests/{req_id}/decision",
        json={"approve": True},
        headers=_h(a_tok),
    )
    assert dec.status_code == 200 and dec.json()["status"] == "approved"
    me2 = (await client.get("/api/v1/auth/me", headers=_h(tok))).json()
    assert "broker" in me2["roles"] and "broker" not in me2["pending_roles"]


async def test_apply_rejects_self_serve_role(client, db):
    tok, _uid = await _user(client, db, "brk-bad@x.com")
    r = await client.post(
        "/api/v1/auth/roles/apply",
        data={"role": "owner", "fields": "{}"},
        headers=_h(tok),
    )
    assert r.status_code == 422  # owner is self-serve — not an application role


async def test_apply_resubmit_updates_same_request(client, db):
    tok, uid = await _user(client, db, "lp-apply@x.com")
    await client.post(
        "/api/v1/auth/roles/apply",
        data={"role": "liquidity_provider", "fields": json.dumps({"entity_type": "individual"})},
        headers=_h(tok),
    )
    await client.post(
        "/api/v1/auth/roles/apply",
        data={"role": "liquidity_provider", "fields": json.dumps({"entity_type": "institution"})},
        headers=_h(tok),
    )
    rows = db(
        "SELECT application FROM role_grant_requests "
        "WHERE user_id=:u AND role='liquidity_provider' AND status='pending'",
        u=uid,
    )
    assert len(rows) == 1  # resubmission updates the SAME pending request, not a duplicate
    assert rows[0][0]["fields"]["entity_type"] == "institution"
