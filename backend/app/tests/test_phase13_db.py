"""Phase 13 — DB-backed admin/cron/reconciliation/hardening tests.

Acceptance bar: cron-auth (X-Cron-Secret OR admin; missing/wrong/unset → 401); LP-expiry
sweep (lapsed open→expired, units freed, idempotent, valid untouched); reconciliation
(clean→ok, injected drift→flagged, never mutates); settings validation (bad pcts/limits
rejected, lp_passive_enabled=true rejected); portfolio endpoint (real ledger values);
rate-limit 429; health with Redis down → 200.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.services import (
    liquidity_service,
    reconciliation_service,
    secondary_service,
    settings_service,
)

PW = "Passw0rd!23"


# --- helpers ---------------------------------------------------------------- #
async def _register(client, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "U"}
    )
    return r.json()["access_token"]


def _uid(db, email: str) -> str:
    return db("SELECT id FROM users WHERE email=:e", e=email)[0][0]


def _verify_kyc(db, uid: str) -> None:
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)


async def _admin(client, db, email: str) -> str:
    await _register(client, email)
    uid = _uid(db, email)
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    return (await client.post("/api/v1/auth/login", json={"email": email, "password": PW})).json()[
        "access_token"
    ]


def _seed_property(db, *, unit_price=100, total_units=1000, available=None) -> str:
    pid = str(uuid.uuid4())
    av = total_units if available is None else available
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'P13 Demo','Dubai','residential','ready-income','active',:tv,:up,:tu,:av,100)",
        id=pid,
        tv=unit_price * total_units,
        up=unit_price,
        tu=total_units,
        av=av,
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


def _seed_lp_request(db, seller: str, pid: str, units: int, *, expires_at) -> str:
    rid = str(uuid.uuid4())
    db(
        "INSERT INTO lp_exit_requests (id, seller_id, property_id, units, units_remaining, "
        "unit_price_snapshot, discount_pct_snapshot, fee_pct_snapshot, gross, lp_price, "
        "liquidity_fee, seller_net, status, expires_at) VALUES "
        "(:id,:s,:p,:n,:n,100,3,2,:g,:lp,:fee,:net,'open',:exp)",
        id=rid,
        s=seller,
        p=pid,
        n=units,
        g=units * 100,
        lp=units * 97,
        fee=units * 2,
        net=units * 95,
        exp=expires_at,
    )
    return rid


def _hdr(token=None, cron=None):
    h: dict[str, str] = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if cron is not None:
        h["X-Cron-Secret"] = cron
    return h


# =========================================================================== #
# 1. Cron auth
# =========================================================================== #
@pytest.mark.asyncio
async def test_cron_auth_secret_admin_and_rejections(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cr3t")
    # valid cron secret → 200 (GET reconciliation + POST jobs)
    assert (
        await client.get("/api/v1/admin/reconciliation", headers=_hdr(cron="s3cr3t"))
    ).status_code == 200
    assert (
        await client.post("/api/v1/admin/liquidity/expire-requests", headers=_hdr(cron="s3cr3t"))
    ).status_code == 200
    assert (
        await client.post(
            "/api/v1/admin/notifications/dispatch-emails", headers=_hdr(cron="s3cr3t")
        )
    ).status_code == 200
    # wrong secret → 401; missing creds entirely → 401
    assert (
        await client.post("/api/v1/admin/liquidity/expire-requests", headers=_hdr(cron="nope"))
    ).status_code == 401
    assert (await client.post("/api/v1/admin/liquidity/expire-requests")).status_code == 401
    # admin JWT still works
    atoken = await _admin(client, db, "p13admin@capimax.com")
    assert (
        await client.post("/api/v1/admin/liquidity/expire-requests", headers=_hdr(token=atoken))
    ).status_code == 200
    # a plain investor is forbidden
    itoken = await _register(client, "p13inv@capimax.com")
    assert (
        await client.post("/api/v1/admin/liquidity/expire-requests", headers=_hdr(token=itoken))
    ).status_code == 403


@pytest.mark.asyncio
async def test_cron_unset_secret_never_authorizes(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "cron_secret", "")  # unset
    # any header value must NOT authorize when the secret is unset
    assert (
        await client.post("/api/v1/admin/liquidity/expire-requests", headers=_hdr(cron=""))
    ).status_code == 401
    assert (
        await client.post("/api/v1/admin/liquidity/expire-requests", headers=_hdr(cron="anything"))
    ).status_code == 401


# =========================================================================== #
# 2. LP-expiry sweep
# =========================================================================== #
@pytest.mark.asyncio
async def test_lp_expiry_frees_units(client, db, asession):
    await _register(client, "lpseller@capimax.com")
    sid = _uid(db, "lpseller@capimax.com")
    pid = _seed_property(db)
    _grant_units(db, sid, pid, 100)
    past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
    _seed_lp_request(db, sid, pid, 40, expires_at=past)

    # Before: the open (but lapsed) request reserves 40 units across both markets.
    reserved_before = await secondary_service.reserved_units(
        asession, uuid.UUID(str(sid)), uuid.UUID(pid)
    )
    assert reserved_before == 40

    n = await liquidity_service.expire_open_requests(asession)
    await asession.commit()
    assert n == 1
    assert db("SELECT status FROM lp_exit_requests WHERE seller_id=:s", s=sid)[0][0] == "expired"

    # After: units freed → reservation drops to 0 (seller can re-list / secondary-sell).
    reserved_after = await secondary_service.reserved_units(
        asession, uuid.UUID(str(sid)), uuid.UUID(pid)
    )
    assert reserved_after == 0

    # Idempotent: a second sweep expires nothing more.
    assert await liquidity_service.expire_open_requests(asession) == 0


@pytest.mark.asyncio
async def test_lp_expiry_leaves_valid_requests(client, db, asession):
    await _register(client, "lpseller2@capimax.com")
    sid = _uid(db, "lpseller2@capimax.com")
    pid = _seed_property(db)
    _grant_units(db, sid, pid, 100)
    future = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
    _seed_lp_request(db, sid, pid, 30, expires_at=future)

    assert await liquidity_service.expire_open_requests(asession) == 0
    await asession.commit()
    assert db("SELECT status FROM lp_exit_requests WHERE seller_id=:s", s=sid)[0][0] == "open"


# =========================================================================== #
# 3. Reconciliation
# =========================================================================== #
@pytest.mark.asyncio
async def test_reconciliation_clean_is_ok(client, db, asession):
    await _register(client, "clean@capimax.com")
    report = await reconciliation_service.run(asession)
    assert report["ok"] is True
    assert all(c["drift_count"] == 0 for c in report["checks"])


@pytest.mark.asyncio
async def test_reconciliation_flags_wallet_drift(client, db, asession):
    await _register(client, "drift@capimax.com")
    uid = _uid(db, "drift@capimax.com")
    # Inject: balance not matching the (empty) ledger.
    db("UPDATE wallets SET balance=999 WHERE user_id=:u", u=uid)
    report = await reconciliation_service.run(asession)
    assert report["ok"] is False
    wb = next(c for c in report["checks"] if c["name"] == "wallet_balance")
    assert wb["drift_count"] >= 1
    # Read-only: the report did NOT fix the injected value.
    assert str(db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0]) == "999.00"


@pytest.mark.asyncio
async def test_reconciliation_flags_property_and_family_drift(client, db, asession):
    # property units skew: available != total and no ledger/reserved to explain it
    _seed_property(db, total_units=100, available=50)
    rep = await reconciliation_service.run(asession)
    pu = next(c for c in rep["checks"] if c["name"] == "property_units")
    assert pu["drift_count"] >= 1

    # family pending > holder net (over-allocation)
    await _register(client, "holder13@capimax.com")
    hid = _uid(db, "holder13@capimax.com")
    pid2 = _seed_property(db)
    _grant_units(db, hid, pid2, 10)
    gid = str(uuid.uuid4())
    db("INSERT INTO family_groups (id, owner_id, name) VALUES (:g,:o,'Fam')", g=gid, o=hid)
    fmid = str(uuid.uuid4())
    db(
        "INSERT INTO family_members (id, family_group_id, user_id, name, relationship) "
        "VALUES (:m,:g,:u,'Self','Self')",
        m=fmid,
        g=gid,
        u=hid,
    )
    tmid = str(uuid.uuid4())
    db(
        "INSERT INTO family_members (id, family_group_id, name, relationship) "
        "VALUES (:m,:g,'Kid','Son')",
        m=tmid,
        g=gid,
    )
    db(
        "INSERT INTO family_transfers (family_group_id, from_member_id, to_member_id, "
        "property_id, units, status) VALUES (:g,:f,:t,:p,50,'pending')",  # 50 > 10 held
        g=gid,
        f=fmid,
        t=tmid,
        p=pid2,
    )
    rep2 = await reconciliation_service.run(asession)
    fam = next(c for c in rep2["checks"] if c["name"] == "family_pending")
    assert fam["drift_count"] >= 1


# =========================================================================== #
# 4. Settings validation
# =========================================================================== #
def test_settings_validation_rules():
    v = settings_service.validate_setting
    v("platform_fee_pct", "2.5")  # ok
    v("secondary_price_max_pct", "")  # open bound ok
    v("withdrawal_auto_approve_limit", "5000")  # ok
    for key, bad in [
        ("platform_fee_pct", "150"),
        ("platform_fee_pct", "-1"),
        ("management_fee_pct", "abc"),
        ("withdrawal_auto_approve_limit", "-5"),
        ("secondary_lockup_days", "1.5"),
    ]:
        with pytest.raises(AppError):
            v(key, bad)


def test_passive_flag_hard_locked():
    settings_service.validate_setting("lp_passive_enabled", "false")  # ok
    with pytest.raises(AppError):
        settings_service.validate_setting("lp_passive_enabled", "true")


# =========================================================================== #
# 5. Portfolio endpoint
# =========================================================================== #
@pytest.mark.asyncio
async def test_portfolio_real_values(client, db):
    t = await _register(client, "pf1@capimax.com")
    uid = _uid(db, "pf1@capimax.com")
    _verify_kyc(db, uid)
    pid = _seed_property(db)
    _fund_wallet(db, uid, 5000)
    await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": 1000, "method": "wallet"},
        headers={"Authorization": f"Bearer {t}", "Idempotency-Key": str(uuid.uuid4())},
    )
    r = await client.get("/api/v1/investments/portfolio", headers=_hdr(token=t))
    assert r.status_code == 200
    body = r.json()
    assert body["units"] == 10
    assert body["properties"] == 1
    assert body["current_value"] == "1000.00"  # 10 units × $100
    assert body["invested"] == "1000.00"


@pytest.mark.asyncio
async def test_portfolio_zero_state_and_auth(client, db):
    t = await _register(client, "pf2@capimax.com")
    r = await client.get("/api/v1/investments/portfolio", headers=_hdr(token=t))
    assert r.json() == {
        "invested": "0.00",
        "current_value": "0.00",
        "total_returns": "0.00",
        "properties": 0,
        "units": 0,
    }
    assert (await client.get("/api/v1/investments/portfolio")).status_code == 401


# =========================================================================== #
# 6. Rate limiting
# =========================================================================== #
@pytest.mark.asyncio
async def test_login_rate_limited(client):
    from app.core.ratelimit import limiter

    limiter.enabled = True
    try:
        codes = []
        for _ in range(12):  # limit is 10/minute
            r = await client.post(
                "/api/v1/auth/login", json={"email": "x@capimax.com", "password": "nope"}
            )
            codes.append(r.status_code)
        assert 429 in codes  # the limiter kicked in
        assert codes[0] != 429  # early requests were allowed
    finally:
        limiter.enabled = False


# =========================================================================== #
# 7. Health with Redis down
# =========================================================================== #
@pytest.mark.asyncio
async def test_healthz_ok_when_redis_down(client, monkeypatch):
    async def _redis_down():
        return False

    monkeypatch.setattr("app.api.routes.health.ping_redis", _redis_down)
    r = await client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["dependencies"]["database"] == "up"
    assert body["dependencies"]["redis"] == "down"
