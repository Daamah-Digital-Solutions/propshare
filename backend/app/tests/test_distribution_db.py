"""Phase 6 — DB-backed distribution-engine tests (the returns money gates).

Acceptance bar: Hamilton pro-rata exact-to-the-cent (uneven/prime pools) +
determinism; management-fee math (Σ net + Σ fee == pool) from the snapshot rate ×
period; re-run idempotency (409, no double-pay); atomicity rollback (no partial
credits); family record-only allocation summing exactly to net; and the
reconciliation invariants (balance == SUM(ledger); total_returns == Σ return items).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.services import wallet_service
from app.services.distribution_service import hamilton

PW = "Passw0rd!23"


# --- pure Hamilton unit tests (no DB): exact + deterministic ---------------- #
def test_hamilton_sums_exactly_and_is_deterministic():
    # prime pool, equal weights -> remainders break the same way every call
    a = hamilton(10000, [("u1", 1), ("u2", 1), ("u3", 1)])
    b = hamilton(10000, [("u1", 1), ("u2", 1), ("u3", 1)])
    assert a == b  # deterministic
    assert sum(a.values()) == 10000  # exact
    assert sorted(a.values()) == [3333, 3333, 3334]


def test_hamilton_uneven_and_prime_pools_sum_exactly():
    cases = [
        (10000, [("a", 7), ("b", 11), ("c", 13)]),  # prime weights
        (99991, [("a", 1), ("b", 2), ("c", 3), ("d", 4)]),  # prime pool
        (1, [("a", 1), ("b", 1)]),  # 1 cent, 2 owners
        (100, [("a", 1)]),  # single owner gets all
    ]
    for pool, weights in cases:
        out = hamilton(pool, weights)
        assert sum(out.values()) == pool
        assert all(v >= 0 for v in out.values())


# --- DB helpers ------------------------------------------------------------- #
async def _verified(client, db, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Inv"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    return r.json()["access_token"]


async def _admin(client, db, email: str) -> str:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Admin"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return login.json()["access_token"]


def _uid(db, email: str) -> str:
    return db("SELECT id FROM users WHERE email=:e", e=email)[0][0]


def _seed_property(db, *, unit_price=100, total_units=100, minimum=100, status="active") -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Marina Bay','Dubai','residential','ready-income',:st,:tv,:up,:tu,:tu,:mi)",
        id=pid,
        st=status,
        tv=unit_price * total_units,
        up=unit_price,
        tu=total_units,
        mi=minimum,
    )
    return pid


def _fund(db, uid: str, amount) -> None:
    db(
        "INSERT INTO transactions (user_id, type, amount, status) "
        "VALUES (:u,'deposit',:a,'completed')",
        u=uid,
        a=amount,
    )
    db("UPDATE wallets SET balance=:a WHERE user_id=:u", a=amount, u=uid)


async def _invest(client, token, pid, amount):
    return await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": amount, "method": "wallet"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
    )


async def _run(client, admin_tok, pid, *, kind, period_key, start, end, pool):
    return await client.post(
        f"/api/v1/admin/properties/{pid}/distributions",
        json={
            "kind": kind,
            "period_key": period_key,
            "period_start": start,
            "period_end": end,
            "gross_pool": pool,
        },
        headers={"Authorization": f"Bearer {admin_tok}"},
    )


def _bal(db, uid):
    return db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0]


def _assert_balance_invariant(db, uid):
    bal = _bal(db, uid)
    led = db("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=:i", i=uid)[0][0]
    assert bal == led, f"balance {bal} != ledger {led}"


# --- pro-rata exact-to-the-cent (3-way uneven split, no fee) ---------------- #
@pytest.mark.asyncio
async def test_pro_rata_sums_to_pool_exactly(client, db):
    admin = await _admin(client, db, "a1@d.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    users = ["pa@d.com", "pb@d.com", "pc@d.com"]
    for e in users:
        t = await _verified(client, db, e)
        _fund(db, _uid(db, e), 1000)
        assert (await _invest(client, t, pid, 100)).status_code == 200  # 1 unit each

    # appreciation kind -> no management fee, isolates pro-rata rounding
    r = await _run(
        client,
        admin,
        pid,
        kind="appreciation",
        period_key="2026-Q1",
        start="2026-01-01",
        end="2026-04-01",
        pool=100,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_net"] == "100.00"
    assert body["total_management_fee"] == "0.00"
    # sum of credited returns is EXACTLY the pool, each within a cent of 33.33
    nets = [
        db("SELECT net_amount FROM distribution_items WHERE user_id=:i", i=_uid(db, e))[0][0]
        for e in users
    ]
    assert sum(nets) == Decimal("100.00")
    assert sorted(str(n) for n in nets) == ["33.33", "33.33", "33.34"]
    for e in users:
        _assert_balance_invariant(db, _uid(db, e))


# --- management fee math (Σ net + Σ fee == pool) ---------------------------- #
@pytest.mark.asyncio
async def test_management_fee_withheld_from_rental(client, db):
    admin = await _admin(client, db, "a2@d.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    for e in ["ma@d.com", "mb@d.com"]:
        t = await _verified(client, db, e)
        _fund(db, _uid(db, e), 2000)
        assert (await _invest(client, t, pid, 1000)).status_code == 200  # 10 units, principal 1000

    # full-year period -> fraction 1.0; mgmt rate snapshot 1.0% -> fee = 1000*1% = 10
    r = await _run(
        client,
        admin,
        pid,
        kind="rental",
        period_key="2026-FY",
        start="2025-01-01",
        end="2026-01-01",
        pool=200,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_management_fee"] == "20.00"  # 10 + 10
    assert body["total_net"] == "180.00"  # 90 + 90
    # Σ net + Σ fee == pool, exactly
    assert Decimal(body["total_net"]) + Decimal(body["total_management_fee"]) == Decimal("200.00")
    for e in ["ma@d.com", "mb@d.com"]:
        uid = _uid(db, e)
        item = db(
            "SELECT gross_amount, management_fee, net_amount FROM distribution_items "
            "WHERE user_id=:i",
            i=uid,
        )[0]
        assert item == (Decimal("100.00"), Decimal("10.00"), Decimal("90.00"))
        # wallet credited net (balance was 2000-1025=975 -> +90 = 1065); total_returns == 90
        assert _bal(db, uid) == Decimal("1065.00")
        assert db("SELECT total_returns FROM wallets WHERE user_id=:i", i=uid)[0][0] == Decimal(
            "90.00"
        )
        _assert_balance_invariant(db, uid)


@pytest.mark.asyncio
async def test_appreciation_kind_has_no_management_fee(client, db):
    admin = await _admin(client, db, "a3@d.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    t = await _verified(client, db, "ap@d.com")
    _fund(db, _uid(db, "ap@d.com"), 2000)
    await _invest(client, t, pid, 1000)
    r = await _run(
        client,
        admin,
        pid,
        kind="appreciation",
        period_key="2026-APP",
        start="2025-01-01",
        end="2026-01-01",
        pool=500,
    )
    assert r.json()["total_management_fee"] == "0.00"
    assert r.json()["total_net"] == "500.00"


# --- re-run idempotency (no double-pay) ------------------------------------- #
@pytest.mark.asyncio
async def test_rerun_same_period_is_refused_no_double_pay(client, db):
    admin = await _admin(client, db, "a4@d.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    t = await _verified(client, db, "idem@d.com")
    uid = _uid(db, "idem@d.com")
    _fund(db, uid, 2000)
    await _invest(client, t, pid, 1000)

    first = await _run(
        client,
        admin,
        pid,
        kind="rental",
        period_key="2026-Q2",
        start="2026-04-01",
        end="2026-07-01",
        pool=300,
    )
    assert first.status_code == 200
    bal_after = _bal(db, uid)
    second = await _run(
        client,
        admin,
        pid,
        kind="rental",
        period_key="2026-Q2",
        start="2026-04-01",
        end="2026-07-01",
        pool=300,
    )
    assert second.status_code == 409 and second.json()["error"]["code"] == "DISTRIBUTION_EXISTS"
    # no second credit, exactly one distribution + one item for the user
    assert _bal(db, uid) == bal_after
    assert db("SELECT count(*) FROM distributions WHERE property_id=:p", p=pid)[0][0] == 1
    assert db("SELECT count(*) FROM distribution_items WHERE user_id=:i", i=uid)[0][0] == 1


# --- atomicity rollback (no partial credits) -------------------------------- #
@pytest.mark.asyncio
async def test_atomic_rollback_on_partial_failure(client, db, monkeypatch):
    admin = await _admin(client, db, "a5@d.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    uids = []
    for e in ["fa@d.com", "fb@d.com"]:
        t = await _verified(client, db, e)
        uid = _uid(db, e)
        uids.append(uid)
        _fund(db, uid, 2000)
        await _invest(client, t, pid, 1000)
    pre = {u: _bal(db, u) for u in uids}

    # blow up on the 2nd wallet credit mid-run -> the whole run must roll back
    real = wallet_service.credit
    calls = {"n": 0}

    async def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("boom")
        return await real(*a, **k)

    monkeypatch.setattr(wallet_service, "credit", flaky)
    r = await _run(
        client,
        admin,
        pid,
        kind="appreciation",
        period_key="2026-FAIL",
        start="2026-01-01",
        end="2026-04-01",
        pool=200,
    )
    assert r.status_code >= 500
    # nothing persisted: no distribution, no items, balances unchanged
    assert db("SELECT count(*) FROM distributions WHERE property_id=:p", p=pid)[0][0] == 0
    assert db("SELECT count(*) FROM distribution_items")[0][0] == 0
    for u in uids:
        assert _bal(db, u) == pre[u]
        assert db("SELECT total_returns FROM wallets WHERE user_id=:i", i=u)[0][0] == Decimal("0")


# --- family record-only allocation (sums exactly to net) -------------------- #
@pytest.mark.asyncio
async def test_family_allocation_records_split_exactly(client, db):
    admin = await _admin(client, db, "a6@d.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    t = await _verified(client, db, "fam@d.com")
    uid = _uid(db, "fam@d.com")
    _fund(db, uid, 2000)
    await _invest(client, t, pid, 1000)  # sole owner, 10 units

    # Phase-10 model: pending family allocations are PENDING family_transfers FROM the
    # owner's Self member to not-yet-registered child members (record-only split).
    gid = str(uuid.uuid4())
    db(
        "INSERT INTO family_groups (id, owner_id, name) VALUES (:g,:o,'Fam')",
        g=gid,
        o=uid,
    )
    self_mid = db(
        "INSERT INTO family_members (family_group_id, user_id, name, relationship, is_verified) "
        "VALUES (:g,:u,'Self','Self (Owner)',true) RETURNING id",
        g=gid,
        u=uid,
    )[0][0]
    for name, units in [("Kid A", 6), ("Kid B", 4)]:
        cid = db(
            "INSERT INTO family_members (family_group_id, name, relationship) "
            "VALUES (:g,:n,'child') RETURNING id",
            g=gid,
            n=name,
        )[0][0]
        db(
            "INSERT INTO family_transfers (family_group_id, from_member_id, to_member_id, "
            "property_id, units, status) VALUES (:g,:f,:t,:p,:u,'pending')",
            g=gid,
            f=self_mid,
            t=cid,
            p=pid,
            u=units,
        )

    r = await _run(
        client,
        admin,
        pid,
        kind="appreciation",
        period_key="2026-FAM",
        start="2026-01-01",
        end="2026-04-01",
        pool=100,
    )
    assert r.status_code == 200
    # money lands in the OWNER's wallet (record-only family split)
    assert db("SELECT total_returns FROM wallets WHERE user_id=:i", i=uid)[0][0] == Decimal(
        "100.00"
    )
    allocs = db(
        "SELECT amount FROM family_return_allocations WHERE family_group_id=:g ORDER BY amount",
        g=gid,
    )
    amounts = sorted(str(a[0]) for a in allocs)
    assert amounts == ["40.00", "60.00"]  # 100 split 6:4, exact
    assert sum(a[0] for a in allocs) == Decimal("100.00")
    assert db("SELECT total_returns FROM family_groups WHERE id=:g", g=gid)[0][0] == Decimal(
        "100.00"
    )


# --- gating + edges --------------------------------------------------------- #
@pytest.mark.asyncio
async def test_distribution_requires_admin(client, db):
    pid = _seed_property(db)
    # unauthenticated
    r0 = await client.post(
        f"/api/v1/admin/properties/{pid}/distributions",
        json={
            "period_key": "x",
            "period_start": "2026-01-01",
            "period_end": "2026-02-01",
            "gross_pool": 10,
        },
    )
    assert r0.status_code == 401
    # authenticated but not admin
    inv = await _verified(client, db, "noadmin@d.com")
    r1 = await _run(
        client,
        inv,
        pid,
        kind="rental",
        period_key="x",
        start="2026-01-01",
        end="2026-02-01",
        pool=10,
    )
    assert r1.status_code == 403


@pytest.mark.asyncio
async def test_distribution_no_owners_rejected(client, db):
    admin = await _admin(client, db, "a7@d.com")
    pid = _seed_property(db)  # no investments
    r = await _run(
        client,
        admin,
        pid,
        kind="rental",
        period_key="2026-EMPTY",
        start="2026-01-01",
        end="2026-04-01",
        pool=100,
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "NO_OWNERS"


@pytest.mark.asyncio
async def test_my_returns_endpoint(client, db):
    admin = await _admin(client, db, "a8@d.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    t = await _verified(client, db, "ret@d.com")
    _fund(db, _uid(db, "ret@d.com"), 2000)
    await _invest(client, t, pid, 1000)
    await _run(
        client,
        admin,
        pid,
        kind="rental",
        period_key="2026-RET",
        start="2025-01-01",
        end="2026-01-01",
        pool=200,
    )
    me = await client.get("/api/v1/investments/returns", headers={"Authorization": f"Bearer {t}"})
    assert me.status_code == 200
    body = me.json()
    assert body["count"] == 1
    # sole owner: gross 200 (full pool), fee 1000*1%*1.0 = 10 -> net 190
    assert body["total_net"] == "190.00"
    assert body["items"][0]["net_amount"] == "190.00"
    assert body["items"][0]["management_fee"] == "10.00"
