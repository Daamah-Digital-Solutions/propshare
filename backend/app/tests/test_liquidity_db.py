"""Phase 9 — DB-backed liquidity-provider tests (ACTIVE rail + money gates).

Covers: server-authoritative + seller-price-locked pricing; cross-market reservation
(both directions); atomic buyback (LP debited lp_price, seller credited seller_net via
secondary_sale + explicit fee row, units moved seller→LP, Σ conserved); concurrency
(one wins / one 409); can't-fund-own; insufficient balance rollback; idempotency; KYC +
liquidity_provider role gate; partial fill; expiry + price-band; the never-commingle
CHECK at the schema level; and Decision 2 (mgmt-fee leak closed — LP-acquired units are
charged the platform rate, original investors keep their own rate, no retroactive change).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import decimal
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.services import distribution_service

PW = "Passw0rd!23"


# --- arrange helpers -------------------------------------------------------- #
async def _verified_user(client, db, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Inv"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    return r.json()["access_token"]


async def _lp_user(client, db, email: str) -> str:
    """A KYC-verified user with the liquidity_provider role active."""
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "LP"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'liquidity_provider')", i=uid)
    db("UPDATE users SET active_role='liquidity_provider' WHERE id=:i", i=uid)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return login.json()["access_token"]


def _uid(db, email: str) -> str:
    return db("SELECT id FROM users WHERE email=:e", e=email)[0][0]


def _seed_property(db, *, unit_price=100, total_units=1000) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Marina Bay','Dubai','residential','ready-income','active',:tv,:up,:tu,:tu,100)",
        id=pid,
        tv=unit_price * total_units,
        up=unit_price,
        tu=total_units,
    )
    return pid


def _grant_units(db, uid: str, pid: str, units: int, *, price=100, fee_rate="1.0"):
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason, fee_rate) "
        "VALUES (:u,:p,:n,:pr,'purchase',:fr)",
        u=uid,
        p=pid,
        n=units,
        pr=price,
        fr=fee_rate,
    )


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


async def _create_request(client, token, pid, units):
    return await client.post(
        "/api/v1/liquidity/exit-requests",
        json={"property_id": pid, "units": units},
        headers={"Authorization": f"Bearer {token}"},
    )


async def _fund(client, token, request_id, units, key="auto"):
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = str(uuid.uuid4()) if key == "auto" else key
    return await client.post(
        f"/api/v1/liquidity/exit-requests/{request_id}/fund",
        json={"units": units},
        headers=headers,
    )


# --- invariants ------------------------------------------------------------- #
def _assert_balance_invariant(db, uid: str):
    bal = db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0]
    led = db("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=:i", i=uid)[0][0]
    assert bal == led, f"balance {bal} != ledger {led}"


def _ownership_sum(db, pid: str) -> int:
    return int(
        db("SELECT COALESCE(SUM(units),0) FROM ownership_ledger WHERE property_id=:i", i=pid)[0][0]
    )


def _holding(db, uid: str, pid: str) -> int:
    return int(
        db(
            "SELECT COALESCE(SUM(units),0) FROM ownership_ledger "
            "WHERE user_id=:u AND property_id=:p",
            u=uid,
            p=pid,
        )[0][0]
    )


# --- request creation + pricing -------------------------------------------- #
@pytest.mark.asyncio
async def test_create_request_pricing_snapshot(client, db):
    ts = await _verified_user(client, db, "s1@l.com")
    sid = _uid(db, "s1@l.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 50)
    res = await _create_request(client, ts, pid, 10)
    assert res.status_code == 200, res.text
    b = res.json()
    # defaults: 3% discount, 2% fee. gross 1000; lp_price 970; fee 19.40; seller_net 950.60
    assert b["gross"] == "1000.00"
    assert b["lp_price"] == "970.00"
    assert b["liquidity_fee"] == "19.40"
    assert b["seller_net"] == "950.60"
    assert b["status"] == "open"


@pytest.mark.asyncio
async def test_create_request_not_owner_rejected(client, db):
    ts = await _verified_user(client, db, "s2@l.com")
    pid = _seed_property(db)
    res = await _create_request(client, ts, pid, 5)
    assert res.status_code == 422 and res.json()["error"]["code"] == "NOT_AN_OWNER"


# --- cross-market reservation (both directions) ----------------------------- #
@pytest.mark.asyncio
async def test_cross_market_reservation_lp_then_secondary(client, db):
    ts = await _verified_user(client, db, "x1@l.com")
    sid = _uid(db, "x1@l.com")
    pid = _seed_property(db)
    _grant_units(db, sid, pid, 10)
    assert (await _create_request(client, ts, pid, 8)).status_code == 200
    # only 2 unreserved units left -> a 5-unit secondary listing must be refused
    listing = await client.post(
        "/api/v1/secondary/listings",
        json={"property_id": pid, "units": 5, "price_per_unit": 100},
        headers={"Authorization": f"Bearer {ts}"},
    )
    assert listing.status_code == 422 and listing.json()["error"]["code"] == "INSUFFICIENT_UNITS"


@pytest.mark.asyncio
async def test_cross_market_reservation_secondary_then_lp(client, db):
    ts = await _verified_user(client, db, "x2@l.com")
    sid = _uid(db, "x2@l.com")
    pid = _seed_property(db)
    _grant_units(db, sid, pid, 10)
    listing = await client.post(
        "/api/v1/secondary/listings",
        json={"property_id": pid, "units": 8, "price_per_unit": 100},
        headers={"Authorization": f"Bearer {ts}"},
    )
    assert listing.status_code == 200
    # only 2 unreserved -> a 5-unit LP exit request must be refused
    res = await _create_request(client, ts, pid, 5)
    assert res.status_code == 422 and res.json()["error"]["code"] == "INSUFFICIENT_UNITS"


# --- atomic buyback happy path ---------------------------------------------- #
@pytest.mark.asyncio
async def test_fund_happy_path(client, db):
    ts = await _verified_user(client, db, "hs@l.com")
    tl = await _lp_user(client, db, "hl@l.com")
    sid = _uid(db, "hs@l.com")
    lid = _uid(db, "hl@l.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 50)
    _fund_wallet(db, lid, 100000)

    req = (await _create_request(client, ts, pid, 10)).json()["request_id"]
    res = await _fund(client, tl, req, 10)
    assert res.status_code == 200, res.text

    # LP debited lp_price 970; seller netted 950.60 (secondary_sale +970, fee -19.40)
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=lid)[0][0] == 100000 - 970
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=sid)[0][0] == decimal.Decimal(
        "950.60"
    )
    assert (
        db("SELECT count(*) FROM transactions WHERE type='secondary_sale' AND amount=970")[0][0]
        == 1
    )
    assert db("SELECT count(*) FROM transactions WHERE type='fee' AND amount=-19.40")[0][0] == 1
    assert (
        db("SELECT count(*) FROM transactions WHERE type='investment' AND amount=-970")[0][0] == 1
    )
    # units moved seller->LP; Σ conserved; LP row carries platform fee_rate (1.0 default)
    assert _holding(db, sid, pid) == 40
    assert _holding(db, lid, pid) == 10
    assert _ownership_sum(db, pid) == 50
    assert db(
        "SELECT fee_rate FROM ownership_ledger WHERE user_id=:u AND reason='lp_acquire'", u=lid
    )[0][0] == decimal.Decimal("1.000")
    # request filled; one active position recorded
    assert db("SELECT status FROM lp_exit_requests WHERE id=:i", i=req)[0][0] == "filled"
    assert db(
        "SELECT classification, principal_amount FROM lp_positions WHERE lp_user_id=:i", i=lid
    )[0] == ("active", decimal.Decimal("970.00"))
    _assert_balance_invariant(db, sid)
    _assert_balance_invariant(db, lid)


# --- seller price-lock: in-band rate change does NOT change payout ----------- #
@pytest.mark.asyncio
async def test_seller_price_locked_within_band(client, db):
    ts = await _verified_user(client, db, "pl_s@l.com")
    tl = await _lp_user(client, db, "pl_l@l.com")
    sid = _uid(db, "pl_s@l.com")
    lid = _uid(db, "pl_l@l.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 50)
    _fund_wallet(db, lid, 100000)
    req = (await _create_request(client, ts, pid, 10)).json()["request_id"]  # seller_net 950.60

    # admin nudges the discount 3% -> 5% (in band); the seller must STILL get 950.60
    _set_setting(db, "liquidity_discount_pct", "5.0")
    assert (await _fund(client, tl, req, 10)).status_code == 200
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=sid)[0][0] == decimal.Decimal(
        "950.60"
    )
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=lid)[0][0] == 100000 - 970


@pytest.mark.asyncio
async def test_price_band_exceeded_rejects_fill(client, db):
    ts = await _verified_user(client, db, "bd_s@l.com")
    tl = await _lp_user(client, db, "bd_l@l.com")
    sid = _uid(db, "bd_s@l.com")
    _fund_wallet(db, _uid(db, "bd_l@l.com"), 100000)
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 50)
    req = (await _create_request(client, ts, pid, 10)).json()["request_id"]
    # blow the discount way out (3% -> 60%): snapshot 970 vs fresh 400 -> >10% band
    _set_setting(db, "liquidity_discount_pct", "60.0")
    res = await _fund(client, tl, req, 10)
    assert res.status_code == 409 and res.json()["error"]["code"] == "PRICE_BAND_EXCEEDED"
    assert _ownership_sum(db, pid) == 50  # nothing moved (atomic rollback)
    # request is left open (the rejected fill rolled back); it lapses by TTL or re-create
    assert db("SELECT status FROM lp_exit_requests WHERE id=:i", i=req)[0][0] == "open"


# --- guards ----------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_cannot_fund_own_request(client, db):
    tl = await _lp_user(client, db, "own@l.com")
    lid = _uid(db, "own@l.com")
    pid = _seed_property(db)
    _grant_units(db, lid, pid, 20)
    _fund_wallet(db, lid, 100000)
    req = (await _create_request(client, tl, pid, 10)).json()["request_id"]
    res = await _fund(client, tl, req, 5)
    assert res.status_code == 409 and res.json()["error"]["code"] == "CANNOT_FUND_OWN_REQUEST"


@pytest.mark.asyncio
async def test_insufficient_lp_balance_rolls_back(client, db):
    ts = await _verified_user(client, db, "ib_s@l.com")
    tl = await _lp_user(client, db, "ib_l@l.com")
    sid = _uid(db, "ib_s@l.com")
    lid = _uid(db, "ib_l@l.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 50)
    _fund_wallet(db, lid, 100)  # nowhere near 970
    req = (await _create_request(client, ts, pid, 10)).json()["request_id"]
    res = await _fund(client, tl, req, 10)
    assert res.status_code == 422 and res.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
    # all-or-nothing: nothing moved, no position, request still open
    assert _ownership_sum(db, pid) == 50
    assert _holding(db, lid, pid) == 0
    assert db("SELECT count(*) FROM lp_positions")[0][0] == 0
    assert db("SELECT status FROM lp_exit_requests WHERE id=:i", i=req)[0][0] == "open"
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=sid)[0][0] == 0
    _assert_balance_invariant(db, lid)


@pytest.mark.asyncio
async def test_fund_idempotency_replay(client, db):
    ts = await _verified_user(client, db, "id_s@l.com")
    tl = await _lp_user(client, db, "id_l@l.com")
    sid = _uid(db, "id_s@l.com")
    lid = _uid(db, "id_l@l.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 50)
    _fund_wallet(db, lid, 100000)
    req = (await _create_request(client, ts, pid, 10)).json()["request_id"]
    r1 = await _fund(client, tl, req, 10, key="dup-1")
    r2 = await _fund(client, tl, req, 10, key="dup-1")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["position_id"] == r2.json()["position_id"]
    assert db("SELECT count(*) FROM lp_positions WHERE idempotency_key='dup-1'")[0][0] == 1
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=lid)[0][0] == 100000 - 970
    _assert_balance_invariant(db, lid)


@pytest.mark.asyncio
async def test_fund_requires_lp_role(client, db):
    ts = await _verified_user(client, db, "rl_s@l.com")
    sid = _uid(db, "rl_s@l.com")
    # a plain verified investor (active_role investor), not an LP
    tinv = await _verified_user(client, db, "rl_i@l.com")
    _fund_wallet(db, _uid(db, "rl_i@l.com"), 100000)
    pid = _seed_property(db)
    _grant_units(db, sid, pid, 20)
    req = (await _create_request(client, ts, pid, 10)).json()["request_id"]
    res = await _fund(client, tinv, req, 5)
    assert res.status_code == 403  # FORBIDDEN — needs liquidity_provider active role


@pytest.mark.asyncio
async def test_fund_requires_idempotency_key(client, db):
    ts = await _verified_user(client, db, "ik_s@l.com")
    tl = await _lp_user(client, db, "ik_l@l.com")
    sid = _uid(db, "ik_s@l.com")
    _fund_wallet(db, _uid(db, "ik_l@l.com"), 100000)
    _grant_units(db, sid, pid := _seed_property(db), 20)
    req = (await _create_request(client, ts, pid, 10)).json()["request_id"]
    res = await _fund(client, tl, req, 5, key=None)
    assert res.status_code == 400 and res.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


# --- concurrency ------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_concurrent_fund_one_wins(client, db):
    ts = await _verified_user(client, db, "cc_s@l.com")
    ta = await _lp_user(client, db, "cc_a@l.com")
    tb = await _lp_user(client, db, "cc_b@l.com")
    sid = _uid(db, "cc_s@l.com")
    _grant_units(db, sid, pid := _seed_property(db, unit_price=100), 10)
    _fund_wallet(db, _uid(db, "cc_a@l.com"), 100000)
    _fund_wallet(db, _uid(db, "cc_b@l.com"), 100000)
    req = (await _create_request(client, ts, pid, 10)).json()["request_id"]

    ra, rb = await asyncio.gather(_fund(client, ta, req, 10), _fund(client, tb, req, 10))
    codes = sorted([ra.status_code, rb.status_code])
    assert codes == [200, 409], f"{ra.status_code}/{ra.text} | {rb.status_code}/{rb.text}"
    loser = ra if ra.status_code == 409 else rb
    assert loser.json()["error"]["code"] in {"INSUFFICIENT_UNITS", "REQUEST_NOT_OPEN"}
    assert db("SELECT units_remaining FROM lp_exit_requests WHERE id=:i", i=req)[0][0] == 0
    assert _ownership_sum(db, pid) == 10
    assert db("SELECT count(*) FROM lp_positions")[0][0] == 1


# --- partial fill ----------------------------------------------------------- #
@pytest.mark.asyncio
async def test_partial_fill(client, db):
    ts = await _verified_user(client, db, "pf_s@l.com")
    tl = await _lp_user(client, db, "pf_l@l.com")
    sid = _uid(db, "pf_s@l.com")
    lid = _uid(db, "pf_l@l.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 50)
    _fund_wallet(db, lid, 100000)
    req = (await _create_request(client, ts, pid, 20)).json()["request_id"]
    assert (await _fund(client, tl, req, 8)).status_code == 200
    assert db("SELECT units_remaining FROM lp_exit_requests WHERE id=:i", i=req)[0][0] == 12
    assert db("SELECT status FROM lp_exit_requests WHERE id=:i", i=req)[0][0] == "open"
    assert _holding(db, lid, pid) == 8
    assert _ownership_sum(db, pid) == 50


# --- expiry ----------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_expired_request_cannot_be_funded(client, db):
    ts = await _verified_user(client, db, "ex_s@l.com")
    tl = await _lp_user(client, db, "ex_l@l.com")
    sid = _uid(db, "ex_s@l.com")
    _fund_wallet(db, _uid(db, "ex_l@l.com"), 100000)
    _grant_units(db, sid, pid := _seed_property(db), 20)
    req = (await _create_request(client, ts, pid, 10)).json()["request_id"]
    db("UPDATE lp_exit_requests SET expires_at = now() - interval '1 hour' WHERE id=:i", i=req)
    res = await _fund(client, tl, req, 10)
    assert res.status_code == 409 and res.json()["error"]["code"] == "REQUEST_EXPIRED"
    assert _ownership_sum(db, pid) == 20


# --- Decision 2: mgmt-fee leak closed, no retroactive change ----------------- #
@pytest.mark.asyncio
async def test_mgmt_fee_charged_on_lp_acquired_units(client, db, asession):
    admin_email = "lpadmin@l.com"
    await client.post(
        "/api/v1/auth/register", json={"email": admin_email, "password": PW, "full_name": "A"}
    )
    aid = _uid(db, admin_email)
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=aid)

    ts = await _verified_user(client, db, "d2_s@l.com")
    tl = await _lp_user(client, db, "d2_l@l.com")
    sid = _uid(db, "d2_s@l.com")
    lid = _uid(db, "d2_l@l.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 20, fee_rate="1.0")  # seller's consented rate 1%
    _fund_wallet(db, lid, 100000)

    req = (await _create_request(client, ts, pid, 8)).json()["request_id"]
    assert (await _fund(client, tl, req, 8)).status_code == 200
    # seller now holds 12, LP holds 8 (LP row stamped platform 1%)

    # rental distribution over a full year: each owner charged 1% on their HELD units.
    await distribution_service.run_distribution(
        asession,
        property_id=uuid.UUID(pid),
        kind="rental",
        period_key="2026-FY",
        period_start=dt.date(2025, 1, 1),
        period_end=dt.date(2026, 1, 1),
        gross_pool=decimal.Decimal("2000"),
        created_by=uuid.UUID(str(aid)),
    )
    await asession.commit()

    # LP (8 units @100 @1%) is charged a mgmt fee — the leak is closed, not zero.
    lp_fee = db("SELECT management_fee FROM distribution_items WHERE user_id=:i", i=lid)[0][0]
    seller_fee = db("SELECT management_fee FROM distribution_items WHERE user_id=:i", i=sid)[0][0]
    assert lp_fee == decimal.Decimal("8.00"), lp_fee  # 8 × 100 × 1%
    assert seller_fee == decimal.Decimal("12.00"), seller_fee  # 12 × 100 × 1%, own consented rate


# --- never-commingle CHECK (schema-level) ----------------------------------- #
@pytest.mark.asyncio
async def test_never_commingle_check_constraint(client, db):
    await client.post(
        "/api/v1/auth/register", json={"email": "nc@l.com", "password": PW, "full_name": "N"}
    )
    uid = _uid(db, "nc@l.com")
    # an ACTIVE row missing its required active columns must be refused by the CHECK
    with pytest.raises(IntegrityError):
        db(
            "INSERT INTO lp_positions (lp_user_id, classification, principal_amount) "
            "VALUES (:u,'active',100)",
            u=uid,
        )
    # a PASSIVE row carrying active-only columns must be refused too
    with pytest.raises(IntegrityError):
        db(
            "INSERT INTO lp_positions (lp_user_id, classification, principal_amount, units) "
            "VALUES (:u,'passive',100,5)",
            u=uid,
        )


# --- auth ------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_liquidity_requires_auth(client):
    assert (await client.get("/api/v1/liquidity/exit-requests")).status_code == 401
    assert (await client.get("/api/v1/liquidity/positions")).status_code == 401
    assert (await client.post("/api/v1/liquidity/exit-requests", json={})).status_code == 401
