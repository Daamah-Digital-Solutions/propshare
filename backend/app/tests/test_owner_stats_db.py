"""Phase 15 — DB-backed tests for the Owner/Developer real-stats read endpoints.

Acceptance bar: every wired card computes the real value from seeded data, owner-scoped
(another owner's data excluded); net-holders excludes a fully-exited user; the monthly
series includes real zeros and excludes pending distributions; occupancy is null
(honest empty, no 94%); funding excludes pending/expired and other devs; repeat-investors
1/2 -> "50.0", zero-state -> "0.0"; auth 401/403.
"""

from __future__ import annotations

import datetime as dt
import uuid

PW = "Passw0rd!23"
NOW = dt.datetime.now(dt.UTC)


def _month_key(d: dt.datetime) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _months_ago(n: int) -> dt.datetime:
    y, m = NOW.year, NOW.month
    for _ in range(n):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return dt.datetime(y, m, 15, tzinfo=dt.UTC)


# --- auth / seeding helpers ------------------------------------------------- #
async def _owner(client, db, email: str) -> tuple[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Owner"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'owner')", i=uid)
    db("UPDATE users SET active_role='owner' WHERE id=:i", i=uid)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return login.json()["access_token"], str(uid)


async def _investor_token(client, db, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Inv"}
    )
    return r.json()["access_token"]


async def _mk_user(client, db, email: str) -> str:
    """Create a real user (investments.user_id / ownership_ledger.user_id have FKs to users)."""
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "U"}
    )
    return str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])


def _seed_property(
    db, owner_id: str, *, total_value=1_000_000, unit_price=100, total_units=100
) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,owner_id,title,location,property_type,model,status,"
        "total_value,unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,:o,'Prop','Dubai','residential','ready-income','active',:tv,:up,:tu,:tu,100)",
        id=pid,
        o=owner_id,
        tv=total_value,
        up=unit_price,
        tu=total_units,
    )
    return pid


def _ledger(db, user_id: str, property_id: str, units: int) -> None:
    db(
        "INSERT INTO ownership_ledger (user_id,property_id,units,unit_price,reason) "
        "VALUES (:u,:p,:n,100,'purchase')",
        u=user_id,
        p=property_id,
        n=units,
    )


def _distribution(
    db, property_id: str, *, period_key, gross, created_at, status="completed"
) -> None:
    db(
        "INSERT INTO distributions (id,property_id,kind,period_key,period_start,period_end,"
        "gross_pool,total_net,total_management_fee,status,created_at) VALUES "
        "(:id,:p,'rental',:pk,:ps,:pe,:g,:g,0,:st,:ca)",
        id=str(uuid.uuid4()),
        p=property_id,
        pk=period_key,
        ps=created_at.date(),
        pe=created_at.date(),
        g=gross,
        st=status,
        ca=created_at,
    )


def _investment(
    db, user_id: str, property_id: str, *, amount, units=1, status="confirmed", confirmed_at=None
) -> None:
    db(
        "INSERT INTO investments (id,user_id,property_id,units,amount,status,confirmed_at) "
        "VALUES (:id,:u,:p,:n,:a,:st,:ca)",
        id=str(uuid.uuid4()),
        u=user_id,
        p=property_id,
        n=units,
        a=amount,
        st=status,
        ca=confirmed_at,
    )


async def _portfolio(client, token):
    return await client.get(
        "/api/v1/owner/portfolio-stats", headers={"Authorization": f"Bearer {token}"}
    )


async def _funding(client, token):
    return await client.get(
        "/api/v1/owner/funding-stats", headers={"Authorization": f"Bearer {token}"}
    )


# --- portfolio-stats -------------------------------------------------------- #
async def test_portfolio_value_and_net_holder_investors(client, db):
    tok, oid = await _owner(client, db, "owner1@x.com")
    pid = _seed_property(db, oid, total_value=1_000_000)
    a = await _mk_user(client, db, "h-a@x.com")
    b = await _mk_user(client, db, "h-b@x.com")
    c = await _mk_user(client, db, "h-c@x.com")
    _ledger(db, a, pid, 10)  # net 10
    _ledger(db, b, pid, 10)  # net 10
    _ledger(db, c, pid, 10)  # fully-exited below -> net 0
    _ledger(db, c, pid, -10)

    r = await _portfolio(client, tok)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_portfolio_value"] == "1000000.00"
    assert body["total_investors"] == 2  # net-holders only; exited user excluded
    assert body["occupancy"] is None  # honest empty, no 94%


async def test_monthly_revenue_series_zeros_and_excludes_pending(client, db):
    tok, oid = await _owner(client, db, "owner2@x.com")
    pid = _seed_property(db, oid)
    _distribution(db, pid, period_key="cur", gross=1000, created_at=NOW)  # current month
    _distribution(db, pid, period_key="old", gross=500, created_at=_months_ago(2))
    _distribution(
        db, pid, period_key="pend", gross=999, created_at=NOW, status="pending"
    )  # excluded

    body = (await _portfolio(client, tok)).json()
    series = {p["month"]: p["amount"] for p in body["monthly_revenue_series"]}
    assert len(series) == 6  # 6-month window
    assert series[_month_key(NOW)] == "1000.00"
    assert series[_month_key(_months_ago(2))] == "500.00"
    # every other month is a real zero
    zero_months = [m for m in series if m not in (_month_key(NOW), _month_key(_months_ago(2)))]
    assert all(series[m] == "0.00" for m in zero_months)
    # current-month card excludes the pending distribution
    assert body["monthly_revenue_current"] == "1000.00"


async def test_per_property_revenue_all_time_and_occupancy_null(client, db):
    tok, oid = await _owner(client, db, "owner3@x.com")
    pid = _seed_property(db, oid)
    _distribution(db, pid, period_key="a", gross=1000, created_at=NOW)
    _distribution(db, pid, period_key="b", gross=500, created_at=_months_ago(2))
    _distribution(db, pid, period_key="p", gross=777, created_at=NOW, status="pending")

    body = (await _portfolio(client, tok)).json()
    pp = {x["property_id"]: x for x in body["per_property"]}
    assert pp[pid]["revenue_generated"] == "1500.00"  # all-time completed, pending excluded
    assert pp[pid]["occupancy"] is None


async def test_portfolio_owner_scoped(client, db):
    tok1, oid1 = await _owner(client, db, "owner-a@x.com")
    _tok2, oid2 = await _owner(client, db, "owner-b@x.com")
    p1 = _seed_property(db, oid1, total_value=1_000_000)
    p2 = _seed_property(db, oid2, total_value=9_000_000)
    b_inv = await _mk_user(client, db, "b-inv@x.com")
    _ledger(db, b_inv, p2, 10)  # owner B's investor
    _distribution(db, p2, period_key="x", gross=8000, created_at=NOW)

    body = (await _portfolio(client, tok1)).json()
    assert body["total_portfolio_value"] == "1000000.00"  # only owner A's property
    assert body["total_investors"] == 0  # owner B's holder excluded
    assert [x["property_id"] for x in body["per_property"]] == [p1]
    assert body["monthly_revenue_current"] == "0.00"  # owner B's distribution excluded


# --- funding-stats ---------------------------------------------------------- #
async def test_funding_series_this_month_and_excludes_pending(client, db):
    tok, oid = await _owner(client, db, "dev1@x.com")
    pid = _seed_property(db, oid)
    x = await _mk_user(client, db, "f-x@x.com")
    y = await _mk_user(client, db, "f-y@x.com")
    pend = await _mk_user(client, db, "f-pend@x.com")
    exp = await _mk_user(client, db, "f-exp@x.com")
    _investment(db, x, pid, amount=60000, confirmed_at=NOW)
    _investment(db, y, pid, amount=30000, confirmed_at=NOW)
    _investment(db, x, pid, amount=40000, confirmed_at=_months_ago(2))
    _investment(db, pend, pid, amount=99999, status="pending", confirmed_at=None)
    _investment(db, exp, pid, amount=88888, status="expired", confirmed_at=NOW)

    body = (await _funding(client, tok)).json()
    series = {p["month"]: p["amount"] for p in body["monthly_funding_series"]}
    assert len(series) == 6
    assert series[_month_key(NOW)] == "90000.00"  # 60000 + 30000 (pending/expired excluded)
    assert series[_month_key(_months_ago(2))] == "40000.00"
    assert body["funding_this_month"] == "90000.00"


async def test_repeat_investors_half_and_distinct(client, db):
    tok, oid = await _owner(client, db, "dev2@x.com")
    pid = _seed_property(db, oid)
    x = await _mk_user(client, db, "r-x@x.com")
    y = await _mk_user(client, db, "r-y@x.com")
    _investment(db, x, pid, amount=100, confirmed_at=NOW)  # X: 2 confirmed -> repeat
    _investment(db, x, pid, amount=100, confirmed_at=_months_ago(1))
    _investment(db, y, pid, amount=100, confirmed_at=NOW)  # Y: 1 confirmed

    body = (await _funding(client, tok)).json()
    assert body["repeat_investors"] == {"repeat": 1, "total": 2, "pct": "50.0"}
    assert body["distinct_investors"] == 2


async def test_funding_zero_state(client, db):
    tok, oid = await _owner(client, db, "dev3@x.com")
    _seed_property(db, oid)  # property but no investments
    body = (await _funding(client, tok)).json()
    assert body["repeat_investors"] == {"repeat": 0, "total": 0, "pct": "0.0"}
    assert body["distinct_investors"] == 0
    assert body["funding_this_month"] == "0.00"
    assert all(p["amount"] == "0.00" for p in body["monthly_funding_series"])


async def test_funding_owner_scoped(client, db):
    tok1, oid1 = await _owner(client, db, "dev-a@x.com")
    _tok2, oid2 = await _owner(client, db, "dev-b@x.com")
    _seed_property(db, oid1)
    p2 = _seed_property(db, oid2)
    other = await _mk_user(client, db, "od-inv@x.com")
    _investment(db, other, p2, amount=50000, confirmed_at=NOW)  # other dev

    body = (await _funding(client, tok1)).json()
    assert body["funding_this_month"] == "0.00"
    assert body["distinct_investors"] == 0


# --- auth ------------------------------------------------------------------- #
async def test_stats_require_auth(client, db):
    assert (await client.get("/api/v1/owner/portfolio-stats")).status_code == 401
    assert (await client.get("/api/v1/owner/funding-stats")).status_code == 401


async def test_stats_require_owner_role(client, db):
    tok = await _investor_token(client, db, "plain-investor@x.com")
    assert (await _portfolio(client, tok)).status_code == 403
    assert (await _funding(client, tok)).status_code == 403
