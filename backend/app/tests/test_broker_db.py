"""Phase 11 — DB-backed broker referrals & commissions tests (the money gates).

Acceptance bar:
  1.  commission = the property's rate (or the general one) × the amount invested, never the
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
_P_END = dt.date(2025, 12, 31)  # 365 days, both ends included -> period_fraction == 1.0


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
# 1. commission = the property's rate, or the general one, x the amount invested
# =========================================================================== #
@pytest.mark.asyncio
async def test_commission_is_a_percentage_of_the_investment(client, db, asession):
    btoken, buid = await _make_broker(client, db, "broker1@capimax.com")
    code = await _broker_code(client, btoken)
    ctoken = await _register(client, "client1@capimax.com", ref=code)
    cuid = _uid(db, "client1@capimax.com")
    _verify_kyc(db, cuid)
    general, own = _seed_property(db), _seed_property(db)
    db("UPDATE properties SET broker_commission_pct=4 WHERE id=:p", p=own)
    _fund_wallet(db, cuid, 5000)

    for pid in (general, own):
        r = await client.post(
            "/api/v1/investments",
            json={"property_id": pid, "amount": 1000, "method": "wallet"},
            headers=_hdr(ctoken, "auto"),
        )
        assert r.status_code == 200, r.text

    rows = db(
        "SELECT revenue_event_type, revenue_amount, commission_rate, commission_amount "
        "FROM broker_commissions WHERE broker_id=:b ORDER BY commission_amount",
        b=buid,
    )
    assert [(r[0], str(r[1]), str(r[3])) for r in rows] == [
        ("investment", "1000.00", "15.00"),  # the general 1.5%
        ("investment", "1000.00", "40.00"),  # this property's own 4%
    ]
    assert decimal.Decimal(rows[0][2]) == decimal.Decimal("1.5")
    assert decimal.Decimal(rows[1][2]) == decimal.Decimal("4")
    assert db("SELECT balance FROM wallets WHERE user_id=:b", b=buid)[0][0] == decimal.Decimal(
        "55.00"
    )
    # the client pays nothing more for having a broker: 2,000 + the 2.5% platform fee
    assert db("SELECT balance FROM wallets WHERE user_id=:c", c=cuid)[0][0] == decimal.Decimal(
        "2950.00"
    )
    # a rate of 0 on a property: no commission
    zero = _seed_property(db)
    db("UPDATE properties SET broker_commission_pct=0 WHERE id=:p", p=zero)
    r = await client.post(
        "/api/v1/investments",
        json={"property_id": zero, "amount": 500, "method": "wallet"},
        headers=_hdr(ctoken, "auto"),
    )
    assert (
        r.status_code == 200
        and len(db("SELECT 1 FROM broker_commissions WHERE broker_id=:b", b=buid)) == 2
    )

    # the broker sees what they earn on each property
    rates = (await client.get("/api/v1/broker/commission-rates", headers=_hdr(btoken))).json()
    assert rates["general_rate"] == "1.5"
    by_id = {i["property_id"]: i for i in rates["items"]}
    assert (by_id[general]["rate"], by_id[general]["own_rate"]) == ("1.5", False)
    assert (by_id[own]["rate"], by_id[own]["own_rate"]) == ("4", True)
    dash = (await client.get("/api/v1/broker/dashboard", headers=_hdr(btoken))).json()
    assert dash["commission_rate"] == "1.5"


@pytest.mark.asyncio
async def test_commission_on_an_installment_plan_follows_each_payment(client, db, asession):
    _btoken, buid = await _make_broker(client, db, "broker1p@capimax.com")
    code = await _broker_code(client, _btoken)
    ctoken = await _register(client, "client1p@capimax.com", ref=code)
    cuid = _uid(db, "client1p@capimax.com")
    _verify_kyc(db, cuid)
    pid = _seed_property(db)
    db("UPDATE properties SET model='installment', broker_commission_pct=2 WHERE id=:p", p=pid)
    _fund_wallet(db, cuid, 5000)
    plan = await client.post(
        "/api/v1/installments",
        json={"property_id": pid, "amount": 1000, "duration_months": 6, "method": "wallet"},
        headers=_hdr(ctoken, "auto"),
    )
    assert plan.status_code == 201, plan.text
    rows = db(
        "SELECT revenue_event_type, revenue_amount, commission_amount FROM broker_commissions "
        "WHERE broker_id=:b",
        b=buid,
    )
    pays = db(
        "SELECT id, base_amount FROM installment_payments WHERE plan_id=:p ORDER BY seq",
        p=plan.json()["id"],
    )
    cent = decimal.Decimal("0.01")
    assert [(r[0], r[1]) for r in rows] == [("installment_payment", pays[0][1])]
    assert rows[0][2] == (pays[0][1] * decimal.Decimal("0.02")).quantize(cent)

    # each later payment earns on its own principal, once
    r = await client.post(
        f"/api/v1/installments/payments/{pays[1][0]}/pay", headers=_hdr(ctoken, "auto2")
    )
    assert r.status_code in (200, 201), r.text
    assert len(db("SELECT 1 FROM broker_commissions WHERE broker_id=:b", b=buid)) == 2
    bal = db("SELECT balance FROM wallets WHERE user_id=:b", b=buid)[0][0]
    led = db("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=:b", b=buid)[0][0]
    assert bal == led and bal == ((pays[0][1] + pays[1][1]) * decimal.Decimal("0.02")).quantize(
        cent
    )


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
# 3. one accrual per purchase; a distribution pays the broker nothing (2026-10-28)
# =========================================================================== #
@pytest.mark.asyncio
async def test_accrual_on_each_purchase_and_none_on_distributions(client, db, asession):
    btoken, buid = await _make_broker(client, db, "broker3@capimax.com")
    code = await _broker_code(client, btoken)
    ctoken = await _register(client, "client3@capimax.com", ref=code)
    cuid = _uid(db, "client3@capimax.com")
    _verify_kyc(db, cuid)
    pid = _seed_property(db)
    _fund_wallet(db, cuid, 5000)

    for _ in range(2):
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
    assert len(rows) == 2 and {t for t, _ in rows} == {"investment"}
    assert len({eid for _, eid in rows}) == 2


# =========================================================================== #
# 4 & 5. a full exit claws nothing back
# =========================================================================== #
@pytest.mark.asyncio
async def test_no_clawback_on_exit(client, db, asession):
    btoken, buid = await _make_broker(client, db, "broker4@capimax.com")
    code = await _broker_code(client, btoken)
    ctoken = await _register(client, "client4@capimax.com", ref=code)
    cuid = _uid(db, "client4@capimax.com")
    _verify_kyc(db, cuid)
    pid = _seed_property(db)
    _fund_wallet(db, cuid, 5000)
    await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": 1000, "method": "wallet"},
        headers=_hdr(ctoken, "auto"),
    )
    bal_before = db("SELECT balance FROM wallets WHERE user_id=:b", b=buid)[0][0]
    assert bal_before == decimal.Decimal("15.00")
    _grant_units(db, cuid, pid, -10, reason="secondary_sale")
    assert db("SELECT balance FROM wallets WHERE user_id=:b", b=buid)[0][0] == bal_before


# =========================================================================== #
# 6. idempotent — one revenue event → one accrual
# =========================================================================== #
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
        revenue_event_type="investment",
        revenue_event_id=event,
        revenue_amount=decimal.Decimal("100"),
    )
    await asession.commit()
    second = await broker_service.accrue_commission(
        asession,
        client_id=cuid,
        revenue_event_type="investment",
        revenue_event_id=event,  # SAME event
        revenue_amount=decimal.Decimal("100"),
    )
    await asession.commit()
    assert second is None  # no-op
    assert db("SELECT COUNT(*) FROM broker_commissions WHERE broker_id=:b", b=buid)[0][0] == 1
    # broker credited exactly once
    assert decimal.Decimal(
        db("SELECT balance FROM wallets WHERE user_id=:b", b=buid)[0][0]
    ) == decimal.Decimal("1.50")


# =========================================================================== #
# 7. admin rate change reflected; history immutable (per-row snapshot)
# =========================================================================== #
@pytest.mark.asyncio
async def test_admin_rate_change_snapshot(client, db, asession):
    btoken, buid = await _make_broker(client, db, "broker7@capimax.com")
    code = await _broker_code(client, btoken)
    ctoken = await _register(client, "client7@capimax.com", ref=code)
    cuid = _uid(db, "client7@capimax.com")
    _verify_kyc(db, cuid)
    pid = _seed_property(db)
    _fund_wallet(db, cuid, 5000)

    for rate in ("1.5", "3"):
        _set_setting(db, "broker_commission_investment_pct", rate)
        await client.post(
            "/api/v1/investments",
            json={"property_id": pid, "amount": 100, "method": "wallet"},
            headers=_hdr(ctoken, "auto"),
        )
    rates = sorted(
        decimal.Decimal(r[0])
        for r in db("SELECT commission_rate FROM broker_commissions WHERE broker_id=:b", b=buid)
    )
    # The first row keeps its 1.5 snapshot — the rate change is NOT retroactive.
    assert rates == [decimal.Decimal("1.5"), decimal.Decimal("3")]


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

    # Both runs completed; a distribution pays the broker no commission.
    assert db("SELECT COUNT(*) FROM distributions")[0][0] == 2
    assert db("SELECT COUNT(*) FROM broker_commissions WHERE broker_id=:b", b=buid)[0][0] == 0


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
