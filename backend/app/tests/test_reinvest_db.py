"""Phase 14 — DB-backed investor reinvest (the real, server-applied discount).

Acceptance bar: the reinvest discount is server-applied + admin-configurable; the client
sends only an amount (never a price); units = floor(amount / effective_price); the wallet
is charged units × effective_price (whole units; the remainder stays); idempotent on the
Idempotency-Key; KYC + key required.
"""

from __future__ import annotations

import uuid

import pytest

PW = "Passw0rd!23"


async def _verified_user(client, db, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "U"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    return r.json()["access_token"]


def _uid(db, email: str) -> str:
    return db("SELECT id FROM users WHERE email=:e", e=email)[0][0]


def _seed_property(db, *, unit_price=100, total_units=1000) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Reinvest Demo','Dubai','residential','ready-income','active',:tv,:up,:tu,:tu,100)",
        id=pid,
        tv=unit_price * total_units,
        up=unit_price,
        tu=total_units,
    )
    return pid


def _fund_wallet(db, uid: str, amount) -> None:
    db(
        "INSERT INTO transactions (user_id, type, amount, status) "
        "VALUES (:u,'deposit',:a,'completed')",
        u=uid,
        a=amount,
    )
    db("UPDATE wallets SET balance=:a WHERE user_id=:u", a=amount, u=uid)


def _set_setting(db, key: str, value: str) -> None:
    db(
        "INSERT INTO platform_settings (key, value) VALUES (:k,:v) "
        "ON CONFLICT (key) DO UPDATE SET value=:v",
        k=key,
        v=value,
    )


def _hdr(token, key=None):
    h = {"Authorization": f"Bearer {token}"}
    if key is not None:
        h["Idempotency-Key"] = str(uuid.uuid4()) if key == "auto" else key
    return h


@pytest.mark.asyncio
async def test_reinvest_applies_server_discount(client, db):
    t = await _verified_user(client, db, "re1@capimax.com")
    uid = _uid(db, "re1@capimax.com")
    pid = _seed_property(db)
    _fund_wallet(db, uid, 5000)
    _set_setting(db, "reinvest_discount_pct", "5.0")

    # Client sends ONLY an amount — the server computes the discounted units/price.
    r = await client.post(
        "/api/v1/investments/reinvest",
        json={"property_id": pid, "amount": 1000},
        headers=_hdr(t, "auto"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # effective_price = 100 × (1 − 5/100) = 95 → units = floor(1000/95) = 10
    assert body["effective_price"] == "95.00"
    assert body["units"] == 10
    assert body["discount_pct"] == "5.0"

    # Ownership recorded at the NOMINAL unit price (asset value), discount is the subsidy.
    led = db("SELECT units, unit_price, reason FROM ownership_ledger WHERE user_id=:u", u=uid)[0]
    assert led[0] == 10 and str(led[1]) == "100.00" and led[2] == "reinvest"
    # Wallet debited units × effective_price (10 × 95 = 950); available units dropped by 10.
    assert str(db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0]) == "4050.00"
    assert db("SELECT available_units FROM properties WHERE id=:p", p=pid)[0][0] == 990


@pytest.mark.asyncio
async def test_reinvest_charges_whole_units_not_raw_amount(client, db):
    """Regression: reinvest debits units × effective_price (whole units), NOT the raw amount,
    so a non-aligned amount never over-charges — the unspent remainder stays in the wallet."""
    t = await _verified_user(client, db, "re6@capimax.com")
    uid = _uid(db, "re6@capimax.com")
    pid = _seed_property(db)
    _fund_wallet(db, uid, 5000)
    _set_setting(db, "reinvest_discount_pct", "5.0")
    # $555 @ effective 95 -> units = floor(555/95) = 5; cost = 5×95 = 475; remainder 80 stays.
    r = await client.post(
        "/api/v1/investments/reinvest",
        json={"property_id": pid, "amount": 555},
        headers=_hdr(t, "auto"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["units"] == 5
    assert r.json()["amount"] == "475.00"  # charged the whole-unit cost, not the raw 555
    assert str(db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0]) == "4525.00"
    assert str(db("SELECT total_invested FROM wallets WHERE user_id=:u", u=uid)[0][0]) == "475.00"


@pytest.mark.asyncio
async def test_reinvest_discount_is_admin_configurable(client, db):
    t = await _verified_user(client, db, "re2@capimax.com")
    uid = _uid(db, "re2@capimax.com")
    pid = _seed_property(db)
    _fund_wallet(db, uid, 5000)
    _set_setting(db, "reinvest_discount_pct", "50")  # effective price 50 → 1000/50 = 20 units

    r = await client.post(
        "/api/v1/investments/reinvest",
        json={"property_id": pid, "amount": 1000},
        headers=_hdr(t, "auto"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["effective_price"] == "50.00"
    assert r.json()["units"] == 20

    # The live rate is exposed (so the UI shows the real server discount, not a literal).
    s = await client.get("/api/v1/investments/reinvest-settings", headers=_hdr(t))
    assert s.json()["discount_pct"] == "50"


@pytest.mark.asyncio
async def test_reinvest_idempotent(client, db):
    t = await _verified_user(client, db, "re3@capimax.com")
    uid = _uid(db, "re3@capimax.com")
    pid = _seed_property(db)
    _fund_wallet(db, uid, 5000)
    key = str(uuid.uuid4())
    first = await client.post(
        "/api/v1/investments/reinvest",
        json={"property_id": pid, "amount": 1000},
        headers=_hdr(t, key),
    )
    second = await client.post(
        "/api/v1/investments/reinvest",
        json={"property_id": pid, "amount": 1000},
        headers=_hdr(t, key),
    )
    assert first.status_code == 200 and second.status_code == 200
    assert second.json().get("replayed") is True
    # exactly one debit (units × effective_price = 950) / one ledger row
    assert str(db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0]) == "4050.00"
    assert db("SELECT COUNT(*) FROM ownership_ledger WHERE user_id=:u", u=uid)[0][0] == 1


@pytest.mark.asyncio
async def test_reinvest_insufficient_funds(client, db):
    t = await _verified_user(client, db, "re4@capimax.com")
    uid = _uid(db, "re4@capimax.com")
    pid = _seed_property(db)
    _fund_wallet(db, uid, 100)  # not enough for a 1000 reinvest
    r = await client.post(
        "/api/v1/investments/reinvest",
        json={"property_id": pid, "amount": 1000},
        headers=_hdr(t, "auto"),
    )
    assert r.status_code == 422
    assert db("SELECT COUNT(*) FROM ownership_ledger WHERE user_id=:u", u=uid)[0][0] == 0


@pytest.mark.asyncio
async def test_reinvest_requires_key_kyc_and_auth(client, db):
    # unauthenticated
    pid = _seed_property(db)
    assert (
        await client.post("/api/v1/investments/reinvest", json={"property_id": pid, "amount": 100})
    ).status_code == 401
    # authed but not KYC-verified
    r = await client.post(
        "/api/v1/auth/register", json={"email": "re5@capimax.com", "password": PW, "full_name": "U"}
    )
    t = r.json()["access_token"]
    res = await client.post(
        "/api/v1/investments/reinvest",
        json={"property_id": pid, "amount": 100},
        headers=_hdr(t, "auto"),
    )
    assert res.status_code == 403  # KYC required
    # KYC ok but missing Idempotency-Key
    db(
        "UPDATE kyc_verifications SET status='verified' WHERE user_id=:i",
        i=_uid(db, "re5@capimax.com"),
    )
    res2 = await client.post(
        "/api/v1/investments/reinvest",
        json={"property_id": pid, "amount": 100},
        headers=_hdr(t),
    )
    assert res2.status_code == 400  # IDEMPOTENCY_KEY_REQUIRED
