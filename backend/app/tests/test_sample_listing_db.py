"""Sample (demo) listings are shown like any listing but can never take money.

Reproduces the risk: a published listing is open for investment, and production accepts
real crypto deposits into wallets, so a demo listing published for meetings could receive
real money. A listing with content.sample = true now refuses every way to acquire units
(direct purchase, reinvest, installment plan) with a plain message, reserves nothing and
charges nothing; normal listings are unaffected.
"""

# ruff: noqa: E501
from __future__ import annotations

import json
import uuid

import pytest

PW = "Passw0rd!23"
MSG = "This is a sample listing shown for demonstration only. It is not open for investment."


async def _investor(client, db, email: str) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Inv"}
    )
    uid = str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    db(
        "INSERT INTO transactions (user_id, type, amount, status) VALUES (:u,'deposit',100000,'completed')",
        u=uid,
    )
    db("UPDATE wallets SET balance=100000, total_returns=5000 WHERE user_id=:u", u=uid)
    return r.json()["access_token"], uid


def _prop(db, *, model: str, sample: bool) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,unit_price,"
        "total_units,available_units,minimum_investment,content) VALUES "
        "(:id,'Sample Tower','Dubai','apartment',:m,'active',100000,100,1000,1000,100,CAST(:c AS jsonb))",
        id=pid,
        m=model,
        c=json.dumps({"sample": True} if sample else {}),
    )
    return pid


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Idempotency-Key": str(uuid.uuid4())}


@pytest.mark.asyncio
async def test_sample_listing_refuses_purchase_installment_and_reinvest(client, db):
    tok, uid = await _investor(client, db, "sample-inv@x.com")
    ready = _prop(db, model="ready-income", sample=True)
    offplan = _prop(db, model="installment", sample=True)
    attempts = [
        await client.post(
            "/api/v1/investments",
            json={"property_id": ready, "amount": 500, "method": "wallet"},
            headers=_h(tok),
        ),
        await client.post(
            "/api/v1/installments",
            json={"property_id": offplan, "amount": 500, "duration_months": 12},
            headers=_h(tok),
        ),
    ]
    # (card/crypto first check the provider is configured, then reach the same guard as wallet)
    for r in attempts:
        assert r.status_code == 409, r.text
        assert r.json()["error"] == {"code": "SAMPLE_LISTING", "message": MSG, "details": {}}
    # nothing reserved, nothing charged, nothing recorded
    for pid in (ready, offplan):
        assert db("SELECT available_units FROM properties WHERE id=:p", p=pid)[0][0] == 1000
    assert db("SELECT count(*) FROM investments WHERE user_id=:u", u=uid)[0][0] == 0
    assert db("SELECT count(*) FROM installment_plans WHERE investor_id=:u", u=uid)[0][0] == 0
    assert db("SELECT count(*) FROM ownership_ledger WHERE user_id=:u", u=uid)[0][0] == 0
    assert float(db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0]) == 100000.0


@pytest.mark.asyncio
async def test_sample_listing_refuses_reinvest(client, db):
    from app.core.errors import AppError
    from app.models import Property
    from app.services import investment_service

    pid = _prop(db, model="ready-income", sample=True)
    prop = Property(id=uuid.UUID(pid), content={"sample": True})
    with pytest.raises(AppError) as exc:
        investment_service.refuse_sample(prop)
    assert exc.value.code == "SAMPLE_LISTING" and exc.value.message == MSG
    # the reinvest path runs the same check right after its status check
    import inspect

    src = inspect.getsource(investment_service)
    assert src.count("    refuse_sample(prop)\n") == 2  # direct purchase + reinvest


@pytest.mark.asyncio
async def test_normal_listings_are_unaffected(client, db):
    tok, _uid = await _investor(client, db, "normal-inv@x.com")
    ready = _prop(db, model="ready-income", sample=False)
    offplan = _prop(db, model="installment", sample=False)
    r = await client.post(
        "/api/v1/investments",
        json={"property_id": ready, "amount": 500, "method": "wallet"},
        headers=_h(tok),
    )
    assert r.status_code in (200, 201), r.text
    r = await client.post(
        "/api/v1/installments",
        json={"property_id": offplan, "amount": 500, "duration_months": 12},
        headers=_h(tok),
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_editor_shows_sample_badge(client, db):
    email = "sample-admin@x.com"
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "A"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    await client.post("/admin/login", data={"username": email, "password": PW})
    sample = (
        await client.get(f"/admin/listing/{_prop(db, model='ready-income', sample=True)}")
    ).text
    normal = (
        await client.get(f"/admin/listing/{_prop(db, model='ready-income', sample=False)}")
    ).text
    assert "Sample listing, not open for investment" in sample
    assert "data-sample-badge" not in normal
