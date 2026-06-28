"""Phase 10 — DB-backed family-groups & gifting tests (the money gates).

Acceptance bar: one-group-per-owner; add real vs pending member; ≤-ownership invariant
(over-allocation → 422; a pending allocation reserves units so a secondary listing / LP
exit of the same units is refused, both directions); atomic REAL transfer (ledger
conserved, fee_rate stamped, no wallet movement) vs PENDING (reserve only); materialize
on KYC-verify; no-double-counted returns (real owner paid directly + excluded from split,
pending recorded-only, Σ items == pool); discount yields floor(amount/(unit_price×(1−d)))
units and is family-scoped; idempotency; auth/KYC gates.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import pytest

from app.services import distribution_service

PW = "Passw0rd!23"


# --- arrange helpers -------------------------------------------------------- #
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
        "(:id,'Fam Demo','Dubai','residential','ready-income','active',:tv,:up,:tu,:tu,100)",
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


def _hdr(token, key=None):
    h = {"Authorization": f"Bearer {token}"}
    if key is not None:
        h["Idempotency-Key"] = str(uuid.uuid4()) if key == "auto" else key
    return h


async def _create_group(client, token, name="Fam"):
    return await client.post("/api/v1/family/groups", json={"name": name}, headers=_hdr(token))


async def _add_member(client, token, name, email, relationship="Son"):
    return await client.post(
        "/api/v1/family/members",
        json={"name": name, "email": email, "relationship": relationship},
        headers=_hdr(token),
    )


async def _group(client, token):
    return (await client.get("/api/v1/family/groups/me", headers=_hdr(token))).json()


def _member_id(group, *, relationship=None, email=None):
    for m in group["members"]:
        if relationship and m["relationship"] == relationship:
            return m["member_id"]
        if email and m["email"] == email:
            return m["member_id"]
    return None


async def _transfer(client, token, frm, to, pid, units, key="auto"):
    return await client.post(
        "/api/v1/family/transfers",
        json={"from_member_id": frm, "to_member_id": to, "property_id": pid, "units": units},
        headers=_hdr(token, key),
    )


def _holding(db, uid, pid):
    return int(
        db(
            "SELECT COALESCE(SUM(units),0) FROM ownership_ledger "
            "WHERE user_id=:u AND property_id=:p",
            u=uid,
            p=pid,
        )[0][0]
    )


def _ownership_sum(db, pid):
    return int(
        db("SELECT COALESCE(SUM(units),0) FROM ownership_ledger WHERE property_id=:i", i=pid)[0][0]
    )


def _balance_invariant(db, uid):
    bal = db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0]
    led = db("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=:i", i=uid)[0][0]
    assert bal == led, f"balance {bal} != ledger {led}"


# --- group lifecycle -------------------------------------------------------- #
@pytest.mark.asyncio
async def test_one_group_per_owner(client, db):
    t = await _verified_user(client, db, "g1@f.com")
    r1 = await _create_group(client, t)
    r2 = await _create_group(client, t)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["group_id"] == r2.json()["group_id"]
    assert (
        db("SELECT count(*) FROM family_groups WHERE owner_id=:o", o=_uid(db, "g1@f.com"))[0][0]
        == 1
    )
    # owner is auto-added as the Self member
    assert _member_id(r1.json(), relationship="Self (Owner)") is not None


@pytest.mark.asyncio
async def test_add_member_real_vs_pending(client, db):
    t = await _verified_user(client, db, "g2@f.com")
    await _verified_user(client, db, "realmember@f.com")  # an existing KYC'd user
    await _create_group(client, t)
    real = await _add_member(client, t, "Real Kid", "realmember@f.com")
    pending = await _add_member(client, t, "Pending Kid", "noone@f.com")
    assert real.json()["is_verified"] is True and real.json()["is_user"] is True
    assert pending.json()["is_verified"] is False and pending.json()["is_user"] is False


# --- ≤-ownership invariant -------------------------------------------------- #
@pytest.mark.asyncio
async def test_over_allocation_rejected(client, db):
    t = await _verified_user(client, db, "ov@f.com")
    uid = _uid(db, "ov@f.com")
    pid = _seed_property(db)
    _grant_units(db, uid, pid, 10)
    g = (await _create_group(client, t)).json()
    self_id = _member_id(g, relationship="Self (Owner)")
    await _add_member(client, t, "P", "ovp@f.com")
    pid_member = _member_id(await _group(client, t), email="ovp@f.com")
    res = await _transfer(client, t, self_id, pid_member, pid, 11)
    assert res.status_code == 422 and res.json()["error"]["code"] == "INSUFFICIENT_UNITS"


@pytest.mark.asyncio
async def test_pending_reserves_blocks_secondary_and_lp(client, db):
    t = await _verified_user(client, db, "rs@f.com")
    uid = _uid(db, "rs@f.com")
    pid = _seed_property(db)
    _grant_units(db, uid, pid, 10)
    g = (await _create_group(client, t)).json()
    self_id = _member_id(g, relationship="Self (Owner)")
    await _add_member(client, t, "P", "rsp@f.com")
    pid_member = _member_id(await _group(client, t), email="rsp@f.com")
    # pending-allocate 8 of the owner's 10 units
    assert (await _transfer(client, t, self_id, pid_member, pid, 8)).status_code == 200
    # only 2 free -> a 5-unit secondary listing is refused
    listing = await client.post(
        "/api/v1/secondary/listings",
        json={"property_id": pid, "units": 5, "price_per_unit": 100},
        headers=_hdr(t),
    )
    assert listing.status_code == 422 and listing.json()["error"]["code"] == "INSUFFICIENT_UNITS"
    # ...and a 5-unit LP exit request is refused too
    lp = await client.post(
        "/api/v1/liquidity/exit-requests",
        json={"property_id": pid, "units": 5},
        headers=_hdr(t),
    )
    assert lp.status_code == 422 and lp.json()["error"]["code"] == "INSUFFICIENT_UNITS"


@pytest.mark.asyncio
async def test_secondary_listing_blocks_family_transfer(client, db):
    """The reverse direction: a secondary listing reserves units against a family transfer."""
    t = await _verified_user(client, db, "rev@f.com")
    uid = _uid(db, "rev@f.com")
    pid = _seed_property(db)
    _grant_units(db, uid, pid, 10)
    g = (await _create_group(client, t)).json()
    self_id = _member_id(g, relationship="Self (Owner)")
    await _add_member(client, t, "P", "revp@f.com")
    pid_member = _member_id(await _group(client, t), email="revp@f.com")
    listing = await client.post(
        "/api/v1/secondary/listings",
        json={"property_id": pid, "units": 8, "price_per_unit": 100},
        headers=_hdr(t),
    )
    assert listing.status_code == 200
    res = await _transfer(client, t, self_id, pid_member, pid, 5)
    assert res.status_code == 422 and res.json()["error"]["code"] == "INSUFFICIENT_UNITS"


# --- atomic real transfer vs pending ---------------------------------------- #
@pytest.mark.asyncio
async def test_real_transfer_moves_ledger_no_wallet(client, db):
    t = await _verified_user(client, db, "rt_o@f.com")
    await _verified_user(client, db, "rt_b@f.com")
    uid = _uid(db, "rt_o@f.com")
    bid = _uid(db, "rt_b@f.com")
    pid = _seed_property(db)
    _grant_units(db, uid, pid, 50)
    g = (await _create_group(client, t)).json()
    self_id = _member_id(g, relationship="Self (Owner)")
    await _add_member(client, t, "Brother", "rt_b@f.com")
    b_member = _member_id(await _group(client, t), email="rt_b@f.com")

    obal = db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0]
    bbal = db("SELECT balance FROM wallets WHERE user_id=:i", i=bid)[0][0]
    res = await _transfer(client, t, self_id, b_member, pid, 10)
    assert res.status_code == 200 and res.json()["status"] == "completed"
    # ledger moved, Σ conserved, no wallet movement
    assert _holding(db, uid, pid) == 40
    assert _holding(db, bid, pid) == 10
    assert _ownership_sum(db, pid) == 50
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == obal
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=bid)[0][0] == bbal
    # recipient's acquired row carries fee_rate (Decision-2 carries)
    assert db(
        "SELECT fee_rate FROM ownership_ledger WHERE user_id=:u AND reason='family_transfer_in'",
        u=bid,
    )[0][0] == decimal.Decimal("1.000")
    _balance_invariant(db, uid)
    _balance_invariant(db, bid)


@pytest.mark.asyncio
async def test_pending_transfer_reserve_only(client, db):
    t = await _verified_user(client, db, "pt@f.com")
    uid = _uid(db, "pt@f.com")
    pid = _seed_property(db)
    _grant_units(db, uid, pid, 20)
    g = (await _create_group(client, t)).json()
    self_id = _member_id(g, relationship="Self (Owner)")
    await _add_member(client, t, "Pending", "pt_p@f.com")
    p_member = _member_id(await _group(client, t), email="pt_p@f.com")
    res = await _transfer(client, t, self_id, p_member, pid, 8)
    assert res.status_code == 200 and res.json()["status"] == "pending"
    # no ledger move; owner still holds all 20; pending cached on the member
    assert _holding(db, uid, pid) == 20
    assert _ownership_sum(db, pid) == 20
    assert db("SELECT allocated_units FROM family_members WHERE id=:i", i=p_member)[0][0] == 8


# --- materialization on KYC verify ------------------------------------------ #
@pytest.mark.asyncio
async def test_materialize_on_member_kyc(client, db):
    t = await _verified_user(client, db, "mt_o@f.com")
    uid = _uid(db, "mt_o@f.com")
    pid = _seed_property(db)
    _grant_units(db, uid, pid, 20)
    g = (await _create_group(client, t)).json()
    self_id = _member_id(g, relationship="Self (Owner)")
    # invite a member by an email that isn't a user yet
    await _add_member(client, t, "Future Kid", "future@f.com")
    p_member = _member_id(await _group(client, t), email="future@f.com")
    assert (await _transfer(client, t, self_id, p_member, pid, 8)).status_code == 200
    assert _holding(db, uid, pid) == 20  # still pending, nothing moved

    # the invited person registers + KYC-verifies, then pulls their allocation
    tp = await _verified_user(client, db, "future@f.com")
    puid = _uid(db, "future@f.com")
    mat = await client.post("/api/v1/family/materialize", headers=_hdr(tp))
    assert mat.status_code == 200 and mat.json()["materialized"] == 1
    # pending -> real: owner 12, member 8, Σ conserved, transfer completed, cache zeroed
    assert _holding(db, uid, pid) == 12
    assert _holding(db, puid, pid) == 8
    assert _ownership_sum(db, pid) == 20
    assert (
        db("SELECT status FROM family_transfers WHERE to_member_id=:m", m=p_member)[0][0]
        == "completed"
    )
    assert db("SELECT allocated_units FROM family_members WHERE id=:i", i=p_member)[0][0] == 0
    # idempotent: re-running materializes nothing more
    assert (await client.post("/api/v1/family/materialize", headers=_hdr(tp))).json()[
        "materialized"
    ] == 0


# --- no double-counted returns (the §3 reconciliation) ---------------------- #
@pytest.mark.asyncio
async def test_no_double_counted_returns(client, db, asession):
    t = await _verified_user(client, db, "dc_o@f.com")
    await _verified_user(client, db, "dc_b@f.com")
    uid = _uid(db, "dc_o@f.com")
    bid = _uid(db, "dc_b@f.com")
    pid = _seed_property(db, unit_price=100)
    _grant_units(db, uid, pid, 20)
    g = (await _create_group(client, t)).json()
    self_id = _member_id(g, relationship="Self (Owner)")
    # B is a real user -> real move (B becomes a direct owner of 8)
    await _add_member(client, t, "Bro", "dc_b@f.com")
    b_member = _member_id(await _group(client, t), email="dc_b@f.com")
    assert (await _transfer(client, t, self_id, b_member, pid, 8)).status_code == 200
    # P is pending -> reserves 4 of the owner's remaining 12
    await _add_member(client, t, "Pend", "dc_p@f.com")
    p_member = _member_id(await _group(client, t), email="dc_p@f.com")
    assert (await _transfer(client, t, self_id, p_member, pid, 4)).status_code == 200
    assert _holding(db, uid, pid) == 12 and _holding(db, bid, pid) == 8

    # appreciation distribution (no mgmt fee) of 2000 -> 100/unit
    await distribution_service.run_distribution(
        asession,
        property_id=uuid.UUID(pid),
        kind="appreciation",
        period_key="2026-DC",
        period_start=dt.date(2026, 1, 1),
        period_end=dt.date(2026, 4, 1),
        gross_pool=decimal.Decimal("2000"),
        created_by=None,
    )
    await asession.commit()

    # REAL owners paid directly; Σ direct items == pool; pending member NOT an item
    owner_item = db("SELECT net_amount FROM distribution_items WHERE user_id=:u", u=uid)[0][0]
    b_item = db("SELECT net_amount FROM distribution_items WHERE user_id=:u", u=bid)[0][0]
    assert owner_item == 1200 and b_item == 800
    assert owner_item + b_item == 2000  # no unit counted twice
    p_uid = db("SELECT user_id FROM family_members WHERE id=:i", i=p_member)[0][0]
    assert p_uid is None  # pending member is not a user -> never a direct item
    # pending member recorded-only: 4/12 of the owner's 1200 = 400 (money stays with owner)
    rec = db("SELECT amount FROM family_return_allocations WHERE member_id=:m", m=p_member)[0][0]
    assert rec == decimal.Decimal("400.00")


# --- reinvest at the family discount ---------------------------------------- #
@pytest.mark.asyncio
async def test_family_reinvest_discount(client, db):
    t = await _verified_user(client, db, "ri@f.com")
    uid = _uid(db, "ri@f.com")
    pid = _seed_property(db, unit_price=100)
    _fund_wallet(db, uid, 100000)
    await _create_group(client, t)
    # default discount 7.5% -> effective 92.50 -> floor(1000/92.50) = 10 units
    res = await client.post(
        "/api/v1/family/reinvest",
        json={"property_id": pid, "amount": 1000},
        headers=_hdr(t, "auto"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["effective_price"] == "92.50"
    assert res.json()["units"] == 10
    assert _holding(db, uid, pid) == 10
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 100000 - 1000
    _balance_invariant(db, uid)


@pytest.mark.asyncio
async def test_family_reinvest_discount_is_configurable(client, db):
    t = await _verified_user(client, db, "ri2@f.com")
    uid = _uid(db, "ri2@f.com")
    pid = _seed_property(db, unit_price=100)
    _fund_wallet(db, uid, 100000)
    _set_setting(db, "family_reinvest_discount_pct", "20")  # effective 80 -> floor(1000/80)=12
    await _create_group(client, t)
    res = await client.post(
        "/api/v1/family/reinvest",
        json={"property_id": pid, "amount": 1000},
        headers=_hdr(t, "auto"),
    )
    assert res.json()["effective_price"] == "80.00"
    assert res.json()["units"] == 12


# --- idempotency ------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_transfer_idempotency(client, db):
    t = await _verified_user(client, db, "id_o@f.com")
    await _verified_user(client, db, "id_b@f.com")
    uid = _uid(db, "id_o@f.com")
    bid = _uid(db, "id_b@f.com")
    pid = _seed_property(db)
    _grant_units(db, uid, pid, 50)
    g = (await _create_group(client, t)).json()
    self_id = _member_id(g, relationship="Self (Owner)")
    await _add_member(client, t, "B", "id_b@f.com")
    b_member = _member_id(await _group(client, t), email="id_b@f.com")
    r1 = await _transfer(client, t, self_id, b_member, pid, 10, key="dup-1")
    r2 = await _transfer(client, t, self_id, b_member, pid, 10, key="dup-1")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["transfer_id"] == r2.json()["transfer_id"]
    assert _holding(db, bid, pid) == 10  # moved exactly once
    assert _ownership_sum(db, pid) == 50


@pytest.mark.asyncio
async def test_reinvest_idempotency(client, db):
    t = await _verified_user(client, db, "rid@f.com")
    uid = _uid(db, "rid@f.com")
    pid = _seed_property(db, unit_price=100)
    _fund_wallet(db, uid, 100000)
    await _create_group(client, t)
    body = {"property_id": pid, "amount": 1000}
    r1 = await client.post("/api/v1/family/reinvest", json=body, headers=_hdr(t, "dup-r"))
    r2 = await client.post("/api/v1/family/reinvest", json=body, headers=_hdr(t, "dup-r"))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json().get("replayed") is True
    assert _holding(db, uid, pid) == 10  # charged/issued exactly once
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 100000 - 1000


# --- gates ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_family_requires_kyc(client, db):
    r = await client.post(
        "/api/v1/auth/register", json={"email": "nokyc@f.com", "password": PW, "full_name": "N"}
    )
    token = r.json()["access_token"]
    res = await _create_group(client, token)
    assert res.status_code == 403 and res.json()["error"]["code"] == "KYC_REQUIRED"


@pytest.mark.asyncio
async def test_family_requires_auth(client):
    assert (await client.get("/api/v1/family/groups/me")).status_code == 401
    assert (await client.post("/api/v1/family/groups", json={"name": "x"})).status_code == 401
