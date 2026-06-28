"""Phase 11 — DB-backed broker referrals & commissions tests (the money gates).

Acceptance bar:
  1.  commission = pct × ACTUAL platform revenue (platform fee + mgmt fee), never the
      investment amount.
  2.  no accrual at signup (link only).
  3.  accrual on each revenue event (purchase + each rental period).
  4.  stops on full exit (no units → no mgmt fee → no commission).
  5.  no clawback (prior commissions + broker balance untouched on exit).
  6.  idempotent — one revenue event → one accrual.
  7.  admin rate change reflected; per-row rate snapshot keeps history immutable.
  8.  self-referral / generic referred_by path carries no commission.
  9.  structural cap CHECK (commission_amount <= revenue_amount).
  10. atomicity (accrual inside the distribution tx) + balance == SUM(ledger).
  11. no deadlock under concurrent shared-broker distributions (sorted union lock).
  12. broker-role gating / auth on every /broker endpoint.
  13. referral code deterministic + unique + one-per-broker; client link immutable.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import decimal
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services import broker_service, distribution_service

PW = "Passw0rd!23"
_P_START = dt.date(2025, 1, 1)
_P_END = dt.date(2026, 1, 1)  # 365 days -> period_fraction == 1.0


# --- arrange helpers -------------------------------------------------------- #
async def _register(client, email: str, *, ref: str | None = None) -> str:
    body = {"email": email, "password": PW, "full_name": "U"}
    if ref is not None:
        body["referral_code"] = ref
    r = await client.post("/api/v1/auth/register", json=body)
    return r.json()["access_token"]


def _uid(db, email: str) -> str:
    return db("SELECT id FROM users WHERE email=:e", e=email)[0][0]


def _verify_kyc(db, uid: str) -> None:
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)


async def _make_broker(client, db, email: str) -> tuple[str, str]:
    """Register + grant the admin-approved broker role + activate it. Returns
    (broker_token, broker_uid)."""
    await _register(client, email)
    uid = _uid(db, email)
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'broker')", i=uid)
    db("UPDATE users SET active_role='broker' WHERE id=:i", i=uid)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return login.json()["access_token"], uid


async def _broker_code(client, token: str) -> str:
    r = await client.get("/api/v1/broker/referral-code", headers=_hdr(token))
    return r.json()["code"]


def _seed_property(db, *, unit_price=100, total_units=1000) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Broker Demo','Dubai','residential','ready-income','active',:tv,:up,:tu,:tu,100)",
        id=pid,
        tv=unit_price * total_units,
        up=unit_price,
        tu=total_units,
    )
    return pid


def _grant_units(
    db, uid: str, pid: str, units: int, *, price=100, fee_rate="1.0", reason="purchase"
):
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason, fee_rate) "
        "VALUES (:u,:p,:n,:pr,:rs,:fr)",
        u=uid,
        p=pid,
        n=units,
        pr=price,
        rs=reason,
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


async def _run_rental(asession, pid: str, *, period_key: str, gross="1000") -> dict:
    res = await distribution_service.run_distribution(
        asession,
        property_id=uuid.UUID(pid),
        kind="rental",
        period_key=period_key,
        period_start=_P_START,
        period_end=_P_END,
        gross_pool=decimal.Decimal(gross),
        created_by=None,
    )
    await asession.commit()
    return res


# =========================================================================== #
# 1. commission = pct × ACTUAL platform revenue, never the investment amount
# =========================================================================== #
@pytest.mark.asyncio
async def test_commission_is_pct_of_platform_revenue_not_investment(client, db, asession):
    btoken, buid = await _make_broker(client, db, "broker1@capimax.com")
    code = await _broker_code(client, btoken)
    ctoken = await _register(client, "client1@capimax.com", ref=code)
    cuid = _uid(db, "client1@capimax.com")
    _verify_kyc(db, cuid)
    pid = _seed_property(db)
    _fund_wallet(db, cuid, 5000)

    # Buy $1000 of units: subtotal 1000, platform fee 2.5% = 25.00.
    r = await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": 1000, "method": "wallet"},
        headers=_hdr(ctoken, "auto"),
    )
    assert r.status_code == 200, r.text

    rows = db(
        "SELECT revenue_event_type, revenue_amount, commission_rate, commission_amount "
        "FROM broker_commissions WHERE broker_id=:b",
        b=buid,
    )
    assert len(rows) == 1
    ev_type, revenue, rate, commission = rows[0]
    assert ev_type == "investment_platform_fee"
    assert decimal.Decimal(revenue) == decimal.Decimal("25.00")  # the platform fee
    assert decimal.Decimal(rate) == decimal.Decimal("10.0")
    assert decimal.Decimal(commission) == decimal.Decimal("2.50")  # 10% × 25 platform fee
    # NEVER a percent of the investment amount (10% × 1000 would be 100).
    assert decimal.Decimal(commission) != decimal.Decimal("100.00")

    # And the recurring mgmt-fee event is also pct × the withheld fee, not units value.
    res = await _run_rental(asession, pid, period_key="2025")
    mgmt_fee = db(
        "SELECT management_fee FROM distribution_items WHERE user_id=:u AND distribution_id=:d",
        u=cuid,
        d=res["distribution_id"],
    )[0][0]
    mrow = db(
        "SELECT commission_amount FROM broker_commissions "
        "WHERE broker_id=:b AND revenue_event_type='distribution_mgmt_fee'",
        b=buid,
    )
    assert len(mrow) == 1
    expected = (
        decimal.Decimal(mgmt_fee) * decimal.Decimal("10") / decimal.Decimal("100")
    ).quantize(decimal.Decimal("0.01"))
    assert decimal.Decimal(mrow[0][0]) == expected


# =========================================================================== #
# 2. no accrual at signup — only the link is created
# =========================================================================== #
@pytest.mark.asyncio
async def test_no_accrual_at_signup(client, db):
    btoken, buid = await _make_broker(client, db, "broker2@capimax.com")
    code = await _broker_code(client, btoken)
    await _register(client, "client2@capimax.com", ref=code)
    cuid = _uid(db, "client2@capimax.com")

    # Link created, attribution set, but ZERO commission and a zero broker balance.
    assert db("SELECT COUNT(*) FROM broker_referrals WHERE client_id=:c", c=cuid)[0][0] == 1
    assert db("SELECT referred_by FROM users WHERE id=:c", c=cuid)[0][0] == buid
    assert db("SELECT COUNT(*) FROM broker_commissions WHERE broker_id=:b", b=buid)[0][0] == 0
    assert decimal.Decimal(db("SELECT balance FROM wallets WHERE user_id=:b", b=buid)[0][0]) == 0


# =========================================================================== #
# 3. accrual on each revenue event (purchase + each rental period)
# =========================================================================== #
@pytest.mark.asyncio
async def test_accrual_on_each_revenue_event(client, db, asession):
    btoken, buid = await _make_broker(client, db, "broker3@capimax.com")
    code = await _broker_code(client, btoken)
    ctoken = await _register(client, "client3@capimax.com", ref=code)
    cuid = _uid(db, "client3@capimax.com")
    _verify_kyc(db, cuid)
    pid = _seed_property(db)
    _fund_wallet(db, cuid, 5000)

    await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": 1000, "method": "wallet"},
        headers=_hdr(ctoken, "auto"),
    )
    await _run_rental(asession, pid, period_key="2025-Q1")
    await _run_rental(asession, pid, period_key="2025-Q2")

    rows = db(
        "SELECT revenue_event_type, revenue_event_id FROM broker_commissions WHERE broker_id=:b",
        b=buid,
    )
    # 1 purchase platform-fee + 2 rental mgmt-fee = 3 distinct revenue events.
    assert len(rows) == 3
    assert {t for t, _ in rows} == {"investment_platform_fee", "distribution_mgmt_fee"}
    assert len({eid for _, eid in rows}) == 3


# =========================================================================== #
# 4 & 5. stops on full exit; no clawback
# =========================================================================== #
@pytest.mark.asyncio
async def test_stops_on_exit_and_no_clawback(client, db, asession):
    btoken, buid = await _make_broker(client, db, "broker4@capimax.com")
    code = await _broker_code(client, btoken)
    await _register(client, "client4@capimax.com", ref=code)
    cuid = _uid(db, "client4@capimax.com")
    # A non-referred bystander co-owner keeps the property distributable after the client
    # exits (so the second run is a clean "no commission", not a NO_OWNERS error).
    await _register(client, "bystander4@capimax.com")
    byid = _uid(db, "bystander4@capimax.com")
    pid = _seed_property(db)
    _grant_units(db, cuid, pid, 100)
    _grant_units(db, byid, pid, 100)

    await _run_rental(asession, pid, period_key="2025")  # accrues on the mgmt fee
    before = db("SELECT COUNT(*) FROM broker_commissions WHERE broker_id=:b", b=buid)[0][0]
    bal_before = decimal.Decimal(db("SELECT balance FROM wallets WHERE user_id=:b", b=buid)[0][0])
    assert before == 1
    assert bal_before > 0

    # Full exit: net ownership goes to zero (a -100 secondary_sale row conserves nothing held).
    _grant_units(db, cuid, pid, -100, reason="secondary_sale")
    assert (
        db("SELECT COALESCE(SUM(units),0) FROM ownership_ledger WHERE user_id=:u", u=cuid)[0][0]
        == 0
    )

    await _run_rental(asession, pid, period_key="2026")  # no units -> no fee -> no commission
    after = db("SELECT COUNT(*) FROM broker_commissions WHERE broker_id=:b", b=buid)[0][0]
    bal_after = decimal.Decimal(db("SELECT balance FROM wallets WHERE user_id=:b", b=buid)[0][0])
    assert after == 1  # stopped — no new accrual
    assert bal_after == bal_before  # no clawback — prior commission stays


# =========================================================================== #
# 6. idempotent — one revenue event → one accrual
# =========================================================================== #
@pytest.mark.asyncio
async def test_idempotent_distribution_rerun(client, db, asession):
    btoken, buid = await _make_broker(client, db, "broker6@capimax.com")
    code = await _broker_code(client, btoken)
    await _register(client, "client6@capimax.com", ref=code)
    cuid = _uid(db, "client6@capimax.com")
    pid = _seed_property(db)
    _grant_units(db, cuid, pid, 100)

    await _run_rental(asession, pid, period_key="2025")
    from app.core.errors import AppError

    with pytest.raises(AppError):  # re-running the SAME period is refused (409)
        await _run_rental(asession, pid, period_key="2025")
    assert db("SELECT COUNT(*) FROM broker_commissions WHERE broker_id=:b", b=buid)[0][0] == 1


@pytest.mark.asyncio
async def test_accrue_is_idempotent_on_same_event(client, db, asession):
    btoken, buid = await _make_broker(client, db, "broker6b@capimax.com")
    code = await _broker_code(client, btoken)
    await _register(client, "client6b@capimax.com", ref=code)
    cuid = _uid(db, "client6b@capimax.com")
    event = uuid.uuid4()

    await broker_service.accrue_commission(
        asession,
        client_id=cuid,
        revenue_event_type="distribution_mgmt_fee",
        revenue_event_id=event,
        revenue_amount=decimal.Decimal("100"),
    )
    await asession.commit()
    second = await broker_service.accrue_commission(
        asession,
        client_id=cuid,
        revenue_event_type="distribution_mgmt_fee",
        revenue_event_id=event,  # SAME event
        revenue_amount=decimal.Decimal("100"),
    )
    await asession.commit()
    assert second is None  # no-op
    assert db("SELECT COUNT(*) FROM broker_commissions WHERE broker_id=:b", b=buid)[0][0] == 1
    # broker credited exactly once
    assert decimal.Decimal(
        db("SELECT balance FROM wallets WHERE user_id=:b", b=buid)[0][0]
    ) == decimal.Decimal("10.00")


# =========================================================================== #
# 7. admin rate change reflected; history immutable (per-row snapshot)
# =========================================================================== #
@pytest.mark.asyncio
async def test_admin_rate_change_snapshot(client, db, asession):
    btoken, buid = await _make_broker(client, db, "broker7@capimax.com")
    code = await _broker_code(client, btoken)
    await _register(client, "client7@capimax.com", ref=code)
    cuid = _uid(db, "client7@capimax.com")
    pid = _seed_property(db)
    _grant_units(db, cuid, pid, 100)

    _set_setting(db, "broker_commission_pct", "10.0")
    await _run_rental(asession, pid, period_key="2025-P1")
    _set_setting(db, "broker_commission_pct", "20.0")
    await _run_rental(asession, pid, period_key="2025-P2")

    rates = {
        eid: decimal.Decimal(rate)
        for eid, rate in db(
            "SELECT revenue_event_id, commission_rate FROM broker_commissions WHERE broker_id=:b",
            b=buid,
        )
    }
    assert sorted(rates.values()) == [decimal.Decimal("10.0"), decimal.Decimal("20.0")]
    # The first row keeps its 10.0 snapshot — the rate change is NOT retroactive.


# =========================================================================== #
# 8. self-referral / generic path carries no commission
# =========================================================================== #
@pytest.mark.asyncio
async def test_self_referral_creates_no_link(client, db, asession):
    btoken, buid = await _make_broker(client, db, "broker8@capimax.com")
    code = await _broker_code(client, btoken)
    # The self-referral guard: resolving a broker's OWN code for themselves must create
    # no link and return None (broker_id == client_id is rejected).
    res = await broker_service.resolve_signup_referral(
        asession, new_user_id=buid, referral_code=code
    )
    await asession.commit()
    assert res is None
    assert db("SELECT COUNT(*) FROM broker_referrals WHERE client_id=:b", b=buid)[0][0] == 0


@pytest.mark.asyncio
async def test_generic_referral_path_no_commission(client, db, asession):
    # A client who signs up with a NON-broker code (a random UUID) gets raw attribution
    # only — no broker_referrals link, and no commission on their revenue.
    some_uuid = str(uuid.uuid4())
    ctoken = await _register(client, "client8b@capimax.com", ref=some_uuid)
    cuid = _uid(db, "client8b@capimax.com")
    _verify_kyc(db, cuid)
    pid = _seed_property(db)
    _fund_wallet(db, cuid, 5000)

    await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": 1000, "method": "wallet"},
        headers=_hdr(ctoken, "auto"),
    )
    await _run_rental(asession, pid, period_key="2025")
    assert db("SELECT COUNT(*) FROM broker_referrals WHERE client_id=:c", c=cuid)[0][0] == 0
    assert db("SELECT COUNT(*) FROM broker_commissions WHERE client_id=:c", c=cuid)[0][0] == 0


# =========================================================================== #
# 9. structural cap CHECK (commission_amount <= revenue_amount)
# =========================================================================== #
@pytest.mark.asyncio
async def test_structural_cap_check(client, db):
    btoken, buid = await _make_broker(client, db, "broker9@capimax.com")
    code = await _broker_code(client, btoken)
    await _register(client, "client9@capimax.com", ref=code)
    cuid = _uid(db, "client9@capimax.com")
    rid = db("SELECT id FROM broker_referrals WHERE client_id=:c", c=cuid)[0][0]

    with pytest.raises(IntegrityError):  # CHECK (commission_amount <= revenue_amount) rejects it
        db(
            "INSERT INTO broker_commissions (broker_id, client_id, referral_id, "
            "revenue_event_type, revenue_event_id, revenue_amount, commission_rate, "
            "commission_amount) VALUES (:b,:c,:r,'x',:e,10.00,10.0,999.00)",
            b=buid,
            c=cuid,
            r=rid,
            e=str(uuid.uuid4()),
        )


# =========================================================================== #
# 10. atomicity (accrual inside the distribution tx) + balance == SUM(ledger)
# =========================================================================== #
@pytest.mark.asyncio
async def test_distribution_rolls_back_if_accrual_fails(client, db, asession, monkeypatch):
    btoken, buid = await _make_broker(client, db, "broker10@capimax.com")
    code = await _broker_code(client, btoken)
    await _register(client, "client10@capimax.com", ref=code)
    cuid = _uid(db, "client10@capimax.com")
    pid = _seed_property(db)
    _grant_units(db, cuid, pid, 100)

    async def _boom(*a, **k):
        raise RuntimeError("injected accrual failure")

    monkeypatch.setattr(broker_service, "accrue_commission", _boom)
    with pytest.raises(RuntimeError):
        await _run_rental(asession, pid, period_key="2025")
    await asession.rollback()
    # Whole run rolled back: no distribution, no items, no credits.
    assert db("SELECT COUNT(*) FROM distributions WHERE property_id=:p", p=pid)[0][0] == 0
    assert db("SELECT COUNT(*) FROM broker_commissions WHERE broker_id=:b", b=buid)[0][0] == 0


@pytest.mark.asyncio
async def test_broker_balance_equals_ledger(client, db, asession):
    btoken, buid = await _make_broker(client, db, "broker10b@capimax.com")
    code = await _broker_code(client, btoken)
    ctoken = await _register(client, "client10b@capimax.com", ref=code)
    cuid = _uid(db, "client10b@capimax.com")
    _verify_kyc(db, cuid)
    pid = _seed_property(db)
    _fund_wallet(db, cuid, 5000)
    await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": 1000, "method": "wallet"},
        headers=_hdr(ctoken, "auto"),
    )
    await _run_rental(asession, pid, period_key="2025")
    bal = decimal.Decimal(db("SELECT balance FROM wallets WHERE user_id=:b", b=buid)[0][0])
    ledger = decimal.Decimal(
        db("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=:b", b=buid)[0][0]
    )
    assert bal == ledger
    # all of the broker's ledger rows are referral_commission credits
    assert (
        db(
            "SELECT COUNT(*) FROM transactions WHERE user_id=:b AND type<>'referral_commission'",
            b=buid,
        )[0][0]
        == 0
    )


# =========================================================================== #
# 11. no deadlock under concurrent shared-broker distributions
# =========================================================================== #
@pytest.mark.asyncio
async def test_no_deadlock_concurrent_shared_broker(client, db, _test_db):
    async_url, _sync = _test_db
    btoken, buid = await _make_broker(client, db, "broker11@capimax.com")
    code = await _broker_code(client, btoken)
    await _register(client, "client11@capimax.com", ref=code)
    cuid = _uid(db, "client11@capimax.com")

    p1, p2 = _seed_property(db), _seed_property(db)
    # Both properties co-owned by the referred client AND the broker (2 shared wallets),
    # so a naive (unsorted) lock order could deadlock; the sorted union lock must not.
    for pid in (p1, p2):
        _grant_units(db, cuid, pid, 100)
        _grant_units(db, buid, pid, 100)

    engine = create_async_engine(async_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def run(pid: str, pk: str):
        async with maker() as s:
            await distribution_service.run_distribution(
                s,
                property_id=uuid.UUID(pid),
                kind="rental",
                period_key=pk,
                period_start=_P_START,
                period_end=_P_END,
                gross_pool=decimal.Decimal("1000"),
                created_by=None,
            )
            await s.commit()

    try:
        await asyncio.gather(run(p1, "C1"), run(p2, "C2"))
    finally:
        await engine.dispose()

    # Both runs completed; the broker earned a mgmt-fee commission on the client in each.
    assert db("SELECT COUNT(*) FROM broker_commissions WHERE broker_id=:b", b=buid)[0][0] == 2


# =========================================================================== #
# 12. broker-role gating / auth
# =========================================================================== #
@pytest.mark.asyncio
async def test_broker_endpoints_require_broker_role(client, db):
    # plain investor (default active_role) is forbidden
    itoken = await _register(client, "plain12@capimax.com")
    for path in (
        "/api/v1/broker/dashboard",
        "/api/v1/broker/referrals",
        "/api/v1/broker/commissions",
    ):
        r = await client.get(path, headers=_hdr(itoken))
        assert r.status_code == 403, path
    # unauthenticated is 401
    r = await client.get("/api/v1/broker/referral-code")
    assert r.status_code == 401


# =========================================================================== #
# 13. referral code deterministic + unique + one-per-broker; link immutable
# =========================================================================== #
@pytest.mark.asyncio
async def test_referral_code_stable_and_unique(client, db):
    t1, _u1 = await _make_broker(client, db, "broker13a@capimax.com")
    t2, _u2 = await _make_broker(client, db, "broker13b@capimax.com")
    a1 = await _broker_code(client, t1)
    a2 = await _broker_code(client, t1)  # same broker, called twice
    b1 = await _broker_code(client, t2)
    assert a1 == a2  # deterministic / one-per-broker
    assert a1 != b1  # distinct per broker


@pytest.mark.asyncio
async def test_client_link_is_immutable(client, db):
    t1, u1 = await _make_broker(client, db, "broker13c@capimax.com")
    t2, u2 = await _make_broker(client, db, "broker13d@capimax.com")
    code1 = await _broker_code(client, t1)
    await _register(client, "client13@capimax.com", ref=code1)
    cuid = _uid(db, "client13@capimax.com")
    rid = db("SELECT id FROM broker_referrals WHERE client_id=:c", c=cuid)[0][0]
    assert db("SELECT broker_id FROM broker_referrals WHERE id=:r", r=rid)[0][0] == u1

    # A second link for the same client violates UNIQUE(client_id) — no re-attribution.
    with pytest.raises(IntegrityError):
        db(
            "INSERT INTO broker_referrals (broker_id, client_id) VALUES (:b,:c)",
            b=u2,
            c=cuid,
        )
