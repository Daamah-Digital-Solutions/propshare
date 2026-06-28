"""Phase 8 — DB-backed secondary-market tests (the money gates).

Covers the acceptance bar: list units you don't own -> rejected; lock-up -> 409;
price-bound -> 422; concurrent double-buy -> one wins / one 409 with units_remaining
never negative; atomic transfer all-or-nothing with rollback; buyer idempotency;
can't buy your own listing; insufficient balance -> 422; ownership invariants after a
burst of randomized trades; resale fee correct; partial fills; sell-then-distribution
pays the NEW owner. Invariants asserted throughout: Σ ownership per property is
conserved by every trade, and balance == SUM(ledger) for every participant.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import decimal
import random
import uuid

import pytest

from app.services import distribution_service

PW = "Passw0rd!23"


# --- arrange helpers -------------------------------------------------------- #
async def _verified_user(client, db, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Inv"}
    )
    token = r.json()["access_token"]
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    return token


def _uid(db, email: str) -> str:
    return db("SELECT id FROM users WHERE email=:e", e=email)[0][0]


def _seed_property(db, *, unit_price=100, total_units=1000, status="active") -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Marina Bay','Dubai','residential','ready-income',:st,:tv,:up,:tu,:av,100)",
        id=pid,
        st=status,
        tv=unit_price * total_units,
        up=unit_price,
        tu=total_units,
        av=total_units,
    )
    return pid


def _grant_units(db, uid: str, pid: str, units: int, *, price=100, ago_days: int | None = None):
    """Give a user units of a property by appending an ownership_ledger row (as a prior
    primary purchase would). ago_days backdates created_at for lock-up tests."""
    created = "now()" if ago_days is None else f"now() - interval '{ago_days} days'"
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason, "
        f"created_at) VALUES (:u,:p,:n,:pr,'purchase',{created})",
        u=uid,
        p=pid,
        n=units,
        pr=price,
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


async def _list(client, token, pid, units, price):
    return await client.post(
        "/api/v1/secondary/listings",
        json={"property_id": pid, "units": units, "price_per_unit": price},
        headers={"Authorization": f"Bearer {token}"},
    )


async def _buy(client, token, listing_id, units, key="auto"):
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = str(uuid.uuid4()) if key == "auto" else key
    return await client.post(
        f"/api/v1/secondary/listings/{listing_id}/buy",
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


# --- listing validation ----------------------------------------------------- #
@pytest.mark.asyncio
async def test_list_units_you_do_not_own_rejected(client, db):
    token = await _verified_user(client, db, "noown@s.com")
    pid = _seed_property(db)
    res = await _list(client, token, pid, 5, 100)
    assert res.status_code == 422 and res.json()["error"]["code"] == "NOT_AN_OWNER"


@pytest.mark.asyncio
async def test_listing_reservation_prevents_double_listing(client, db):
    token = await _verified_user(client, db, "double@s.com")
    uid = _uid(db, "double@s.com")
    pid = _seed_property(db)
    _grant_units(db, uid, pid, 10)
    ok = await _list(client, token, pid, 8, 100)
    assert ok.status_code == 200, ok.text
    # only 2 unreserved units remain -> a 5-unit second listing is refused
    over = await _list(client, token, pid, 5, 100)
    assert over.status_code == 422 and over.json()["error"]["code"] == "INSUFFICIENT_UNITS"


@pytest.mark.asyncio
async def test_lockup_blocks_listing(client, db):
    token = await _verified_user(client, db, "lock@s.com")
    uid = _uid(db, "lock@s.com")
    pid = _seed_property(db)
    _set_setting(db, "secondary_lockup_days", "30")
    _grant_units(db, uid, pid, 10, ago_days=5)  # acquired 5 days ago, 30-day lock-up
    res = await _list(client, token, pid, 5, 100)
    assert res.status_code == 409 and res.json()["error"]["code"] == "LOCKUP_ACTIVE"
    # past the lock-up window -> allowed
    db("DELETE FROM ownership_ledger WHERE user_id=:u", u=uid)
    _grant_units(db, uid, pid, 10, ago_days=40)
    ok = await _list(client, token, pid, 5, 100)
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_price_bounds_enforced(client, db):
    token = await _verified_user(client, db, "price@s.com")
    uid = _uid(db, "price@s.com")
    pid = _seed_property(db, unit_price=100)
    _set_setting(db, "secondary_price_min_pct", "90")
    _set_setting(db, "secondary_price_max_pct", "110")
    _grant_units(db, uid, pid, 50)
    low = await _list(client, token, pid, 5, 80)  # 80 < 90% of 100
    assert low.status_code == 422 and low.json()["error"]["code"] == "PRICE_OUT_OF_BOUNDS"
    high = await _list(client, token, pid, 5, 120)  # 120 > 110% of 100
    assert high.status_code == 422 and high.json()["error"]["code"] == "PRICE_OUT_OF_BOUNDS"
    ok = await _list(client, token, pid, 5, 105)
    assert ok.status_code == 200, ok.text


# --- happy path + fee ------------------------------------------------------- #
@pytest.mark.asyncio
async def test_buy_happy_path_transfers_units_and_money(client, db):
    ts = await _verified_user(client, db, "seller@s.com")
    tb = await _verified_user(client, db, "buyer@s.com")
    sid = _uid(db, "seller@s.com")
    bid = _uid(db, "buyer@s.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 50)
    _fund_wallet(db, bid, 100000)

    listing_id = (await _list(client, ts, pid, 50, 105)).json()["listing_id"]
    res = await _buy(client, tb, listing_id, 10)
    assert res.status_code == 200, res.text
    body = res.json()
    # server-authoritative: 10 * 105 = 1050 gross; 1.0% resale fee = 10.50; total 1060.50
    assert body["gross"] == "1050.00"
    assert body["resale_fee"] == "10.50"
    assert body["total_charged"] == "1060.50"

    # seller credited the FULL gross; buyer debited gross + fee
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=sid)[0][0] == 1050
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=bid)[0][0] == 100000 - 1060.50
    # seller proceeds booked as a secondary_sale; buyer as investment + fee
    assert (
        db("SELECT count(*) FROM transactions WHERE type='secondary_sale' AND amount=1050")[0][0]
        == 1
    )
    assert (
        db("SELECT count(*) FROM transactions WHERE type='investment' AND amount=-1050")[0][0] == 1
    )
    assert db("SELECT count(*) FROM transactions WHERE type='fee' AND amount=-10.50")[0][0] == 1
    # units moved: seller 40, buyer 10, Σ conserved at 50
    assert _holding(db, sid, pid) == 40
    assert _holding(db, bid, pid) == 10
    assert _ownership_sum(db, pid) == 50
    # listing partially filled
    assert (
        db("SELECT units_remaining FROM secondary_listings WHERE id=:i", i=listing_id)[0][0] == 40
    )
    assert db("SELECT status FROM secondary_listings WHERE id=:i", i=listing_id)[0][0] == "active"
    _assert_balance_invariant(db, sid)
    _assert_balance_invariant(db, bid)


@pytest.mark.asyncio
async def test_full_fill_marks_listing_sold(client, db):
    ts = await _verified_user(client, db, "fseller@s.com")
    tb = await _verified_user(client, db, "fbuyer@s.com")
    sid = _uid(db, "fseller@s.com")
    bid = _uid(db, "fbuyer@s.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 10)
    _fund_wallet(db, bid, 100000)
    listing_id = (await _list(client, ts, pid, 10, 100)).json()["listing_id"]
    res = await _buy(client, tb, listing_id, 10)
    assert res.status_code == 200
    assert db("SELECT units_remaining FROM secondary_listings WHERE id=:i", i=listing_id)[0][0] == 0
    assert db("SELECT status FROM secondary_listings WHERE id=:i", i=listing_id)[0][0] == "sold"
    assert _ownership_sum(db, pid) == 10


# --- guards ----------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_cannot_buy_own_listing(client, db):
    ts = await _verified_user(client, db, "self@s.com")
    sid = _uid(db, "self@s.com")
    pid = _seed_property(db)
    _grant_units(db, sid, pid, 20)
    _fund_wallet(db, sid, 100000)
    listing_id = (await _list(client, ts, pid, 10, 100)).json()["listing_id"]
    res = await _buy(client, ts, listing_id, 5)
    assert res.status_code == 409 and res.json()["error"]["code"] == "CANNOT_BUY_OWN_LISTING"
    assert _ownership_sum(db, pid) == 20  # nothing moved


@pytest.mark.asyncio
async def test_insufficient_balance_rolls_back(client, db):
    ts = await _verified_user(client, db, "pseller@s.com")
    tb = await _verified_user(client, db, "poor@s.com")
    sid = _uid(db, "pseller@s.com")
    bid = _uid(db, "poor@s.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 50)
    _fund_wallet(db, bid, 50)  # nowhere near 10 * 100 + fee
    listing_id = (await _list(client, ts, pid, 50, 100)).json()["listing_id"]

    res = await _buy(client, tb, listing_id, 10)
    assert res.status_code == 422 and res.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
    # all-or-nothing: no unit moved, no trade row, listing untouched, balances intact
    assert _holding(db, sid, pid) == 50
    assert _holding(db, bid, pid) == 0
    assert (
        db("SELECT units_remaining FROM secondary_listings WHERE id=:i", i=listing_id)[0][0] == 50
    )
    assert db("SELECT count(*) FROM secondary_trades")[0][0] == 0
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=bid)[0][0] == 50
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=sid)[0][0] == 0
    _assert_balance_invariant(db, bid)
    _assert_balance_invariant(db, sid)


@pytest.mark.asyncio
async def test_buy_idempotency_replay_returns_same_trade(client, db):
    ts = await _verified_user(client, db, "iseller@s.com")
    tb = await _verified_user(client, db, "ibuyer@s.com")
    sid = _uid(db, "iseller@s.com")
    bid = _uid(db, "ibuyer@s.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 50)
    _fund_wallet(db, bid, 100000)
    listing_id = (await _list(client, ts, pid, 50, 100)).json()["listing_id"]

    r1 = await _buy(client, tb, listing_id, 10, key="dup-1")
    r2 = await _buy(client, tb, listing_id, 10, key="dup-1")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["trade_id"] == r2.json()["trade_id"]
    assert db("SELECT count(*) FROM secondary_trades WHERE idempotency_key='dup-1'")[0][0] == 1
    # charged + transferred exactly once
    assert _holding(db, bid, pid) == 10
    assert (
        db("SELECT units_remaining FROM secondary_listings WHERE id=:i", i=listing_id)[0][0] == 40
    )
    _assert_balance_invariant(db, bid)


@pytest.mark.asyncio
async def test_buy_requires_idempotency_key(client, db):
    ts = await _verified_user(client, db, "kseller@s.com")
    tb = await _verified_user(client, db, "kbuyer@s.com")
    sid = _uid(db, "kseller@s.com")
    _grant_units(db, sid, pid := _seed_property(db), 20)
    _fund_wallet(db, _uid(db, "kbuyer@s.com"), 100000)
    listing_id = (await _list(client, ts, pid, 20, 100)).json()["listing_id"]
    res = await _buy(client, tb, listing_id, 5, key=None)
    assert res.status_code == 400 and res.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


@pytest.mark.asyncio
async def test_buy_requires_kyc(client, db):
    ts = await _verified_user(client, db, "kyseller@s.com")
    sid = _uid(db, "kyseller@s.com")
    pid = _seed_property(db)
    _grant_units(db, sid, pid, 20)
    listing_id = (await _list(client, ts, pid, 20, 100)).json()["listing_id"]
    # buyer registers but is NOT verified
    r = await client.post(
        "/api/v1/auth/register", json={"email": "raw@s.com", "password": PW, "full_name": "R"}
    )
    tb = r.json()["access_token"]
    _fund_wallet(db, _uid(db, "raw@s.com"), 100000)
    res = await _buy(client, tb, listing_id, 5)
    assert res.status_code == 403 and res.json()["error"]["code"] == "KYC_REQUIRED"


# --- concurrency ------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_concurrent_double_buy_one_wins(client, db):
    """Two buyers race for the same last 10 units — exactly one wins (listing FOR UPDATE)."""
    ts = await _verified_user(client, db, "cseller@s.com")
    ta = await _verified_user(client, db, "ca@s.com")
    tb = await _verified_user(client, db, "cb@s.com")
    sid = _uid(db, "cseller@s.com")
    _grant_units(db, sid, pid := _seed_property(db, unit_price=100), 10)
    _fund_wallet(db, _uid(db, "ca@s.com"), 100000)
    _fund_wallet(db, _uid(db, "cb@s.com"), 100000)
    listing_id = (await _list(client, ts, pid, 10, 100)).json()["listing_id"]

    ra, rb = await asyncio.gather(
        _buy(client, ta, listing_id, 10),
        _buy(client, tb, listing_id, 10),
    )
    codes = sorted([ra.status_code, rb.status_code])
    assert codes == [200, 409], f"{ra.status_code}/{ra.text} | {rb.status_code}/{rb.text}"
    loser = ra if ra.status_code == 409 else rb
    assert loser.json()["error"]["code"] in {"INSUFFICIENT_UNITS", "LISTING_NOT_ACTIVE"}
    # exactly 10 units sold, never negative, Σ conserved, sold-out
    rem = db("SELECT units_remaining FROM secondary_listings WHERE id=:i", i=listing_id)[0][0]
    assert rem == 0
    assert db("SELECT status FROM secondary_listings WHERE id=:i", i=listing_id)[0][0] == "sold"
    assert _ownership_sum(db, pid) == 10
    assert db("SELECT count(*) FROM secondary_trades")[0][0] == 1


# --- ownership invariants after a burst ------------------------------------- #
@pytest.mark.asyncio
async def test_ownership_invariants_after_randomized_trades(client, db):
    rng = random.Random(8)  # deterministic
    ts = await _verified_user(client, db, "bseller@s.com")
    sid = _uid(db, "bseller@s.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 100)

    buyers = []
    for n in range(4):
        tok = await _verified_user(client, db, f"bb{n}@s.com")
        _fund_wallet(db, _uid(db, f"bb{n}@s.com"), 1_000_000)
        buyers.append((tok, _uid(db, f"bb{n}@s.com")))

    listing_id = (await _list(client, ts, pid, 100, 100)).json()["listing_id"]
    bought_total = 0
    for _ in range(12):
        tok, _bid = rng.choice(buyers)
        rem = db("SELECT units_remaining FROM secondary_listings WHERE id=:i", i=listing_id)[0][0]
        if rem <= 0:
            break
        qty = rng.randint(1, min(9, rem))
        res = await _buy(client, tok, listing_id, qty)
        assert res.status_code == 200, res.text
        bought_total += qty

    # Σ ownership conserved; seller's remaining == 100 - bought; never negative
    assert _ownership_sum(db, pid) == 100
    assert _holding(db, sid, pid) == 100 - bought_total
    rem = db("SELECT units_remaining FROM secondary_listings WHERE id=:i", i=listing_id)[0][0]
    assert rem == 100 - bought_total >= 0
    # every participant's wallet reconciles
    _assert_balance_invariant(db, sid)
    for _tok, bid in buyers:
        _assert_balance_invariant(db, bid)


# --- sell then distribution pays the new owner ------------------------------ #
@pytest.mark.asyncio
async def test_distribution_after_sale_pays_new_owner(client, db, asession):
    ts = await _verified_user(client, db, "dseller@s.com")
    tb = await _verified_user(client, db, "dbuyer@s.com")
    sid = _uid(db, "dseller@s.com")
    bid = _uid(db, "dbuyer@s.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, sid, pid, 20)
    _fund_wallet(db, bid, 100000)

    listing_id = (await _list(client, ts, pid, 20, 100)).json()["listing_id"]
    assert (await _buy(client, tb, listing_id, 8)).status_code == 200
    # seller now holds 12, buyer holds 8
    assert _holding(db, sid, pid) == 12 and _holding(db, bid, pid) == 8

    # appreciation distribution (no management fee) of 2000 -> 100/unit
    await distribution_service.run_distribution(
        asession,
        property_id=uuid.UUID(pid),
        kind="appreciation",
        period_key="2026-Q2",
        period_start=dt.date(2026, 4, 1),
        period_end=dt.date(2026, 6, 30),
        gross_pool=decimal.Decimal("2000"),
        created_by=None,
    )
    await asession.commit()

    # the NEW owner is paid pro-rata by current ownership: seller 1200, buyer 800
    seller_item = db("SELECT net_amount FROM distribution_items WHERE user_id=:u", u=sid)[0][0]
    buyer_item = db("SELECT net_amount FROM distribution_items WHERE user_id=:u", u=bid)[0][0]
    assert seller_item == 1200 and buyer_item == 800
    assert seller_item + buyer_item == 2000


# --- auth ------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_secondary_requires_auth(client):
    assert (await client.get("/api/v1/secondary/listings")).status_code == 401
    assert (await client.get("/api/v1/secondary/holdings")).status_code == 401
    assert (await client.post("/api/v1/secondary/listings", json={})).status_code == 401
