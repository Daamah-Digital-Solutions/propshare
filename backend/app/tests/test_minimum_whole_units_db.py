"""Listing minimum on BOTH money paths (owner decision): whole units, same rule, same message.

Reproduces the gap: the installment plan only checked "at least one unit" and ignored the
listing's minimum investment, while a direct purchase enforced it with a terse message.
"""

# ruff: noqa: E501
from __future__ import annotations

import uuid

import pytest

PW = "Passw0rd!23"


async def _investor(client, db, email: str, balance: int = 100_000) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Inv"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    db(
        "INSERT INTO transactions (user_id, type, amount, status) VALUES (:u,'deposit',:a,'completed')",
        u=uid,
        a=balance,
    )
    db("UPDATE wallets SET balance=:a WHERE user_id=:u", a=balance, u=uid)
    return r.json()["access_token"]


def _prop(db, *, model: str, unit_price: int = 100, minimum: int = 500, units: int = 1000) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,unit_price,"
        "total_units,available_units,minimum_investment) VALUES "
        "(:id,'Min Tower','Dubai','apartment',:m,'active',:tv,:up,:u,:u,:mn)",
        id=pid,
        m=model,
        tv=unit_price * units,
        up=unit_price,
        u=units,
        mn=minimum,
    )
    return pid


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Idempotency-Key": str(uuid.uuid4())}


MSG_500 = "The minimum investment for this property is $500 (5 whole units at $100 each). Amounts are rounded down to whole units."


async def _plan(client, tok, pid, amount):
    return await client.post(
        "/api/v1/installments",
        json={"property_id": pid, "amount": amount, "duration_months": 12},
        headers=_h(tok),
    )


@pytest.mark.asyncio
async def test_installment_plan_enforces_listing_minimum(client, db):
    tok = await _investor(client, db, "plan-min@x.com")
    pid = _prop(db, model="installment", minimum=500)
    for amount in (300, 499, 599.99 - 100):  # 3, 4 and 4 whole units: all below $500
        r = await _plan(client, tok, pid, amount)
        assert r.status_code == 422, (amount, r.text)
        err = r.json()["error"]
        assert err["code"] == "AMOUNT_TOO_LOW" and err["message"] == MSG_500
        assert err["details"]["minimum_amount"] == "500"
    # nothing reserved, nothing charged
    assert db("SELECT count(*) FROM installment_plans WHERE property_id=:p", p=pid)[0][0] == 0
    assert db("SELECT available_units FROM properties WHERE id=:p", p=pid)[0][0] == 1000
    assert (
        float(
            db(
                "SELECT balance FROM wallets w JOIN users u ON u.id=w.user_id WHERE u.email='plan-min@x.com'"
            )[0][0]
        )
        == 100000.0
    )
    # exactly the minimum works; an amount between whole units is rounded down to whole units
    ok = await _plan(client, tok, pid, 500)
    assert ok.status_code == 201, ok.text
    ok2 = await _plan(client, tok, pid, 650)
    assert ok2.status_code == 201, ok2.text
    assert [
        r[0]
        for r in db(
            "SELECT units_total FROM installment_plans WHERE property_id=:p ORDER BY created_at",
            p=pid,
        )
    ] == [5, 6]


@pytest.mark.asyncio
async def test_direct_purchase_uses_the_same_rule_and_message(client, db):
    tok = await _investor(client, db, "buy-min@x.com")
    pid = _prop(db, model="ready-income", minimum=500)
    r = await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": 450, "method": "wallet"},
        headers=_h(tok),
    )
    assert r.status_code == 422 and r.json()["error"]["message"] == MSG_500
    r = await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": 500, "method": "wallet"},
        headers=_h(tok),
    )
    assert r.status_code in (200, 201), r.text


@pytest.mark.asyncio
async def test_legacy_minimum_below_one_unit_or_not_whole_units_is_rounded_up_in_the_message(
    client, db
):
    tok = await _investor(client, db, "legacy-min@x.com")
    below = _prop(db, model="installment", unit_price=100, minimum=10)
    r = await _plan(client, tok, below, 50)
    assert (
        r.json()["error"]["message"]
        == "The minimum investment for this property is $100 (1 whole unit at $100 each). Amounts are rounded down to whole units."
    )
    odd = _prop(db, model="installment", unit_price=100, minimum=250)
    r = await _plan(client, tok, odd, 200)
    assert (
        r.json()["error"]["message"]
        == "The minimum investment for this property is $300 (3 whole units at $100 each). Amounts are rounded down to whole units."
    )
    assert (await _plan(client, tok, odd, 300)).status_code == 201
