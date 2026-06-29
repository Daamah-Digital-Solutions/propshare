"""Group 5 — DB-backed tests for inter-vivos gifting (scheduled + recurring).

Acceptance: scheduling reserves units / escrows cash; the executor moves real ownership
(or credits cash) atomically on the date + conserves Σ; recurrence re-enqueues the next
occurrence (UNIQUE(series_id, scheduled_for) → no dup); a non-user recipient materializes
on KYC (property + wallet); cancel releases the reservation / refunds the escrow; execution
is idempotent (no double move); passive_income/tokenized are rejected; zero-fee by default;
owner-scoped; the run-due endpoint is admin-OR-cron gated; the 7-day reminder fires once.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

PW = "Passw0rd!23"


# --- helpers ---------------------------------------------------------------- #
async def _user(client, db, email: str) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "U"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    return r.json()["access_token"], str(uid)


async def _admin(client, db, email: str) -> tuple[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Admin"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return login.json()["access_token"], str(uid)


def _kyc_verify(db, uid: str) -> None:
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:u", u=uid)


def _seed_property(db, *, unit_price: int = 100) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,"
        "total_value,unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Prop','Dubai','residential','ready-income','active',1000000,:up,100,100,100)",
        id=pid,
        up=unit_price,
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


def _net(db, user_id: str, property_id: str) -> int:
    return int(
        db(
            "SELECT COALESCE(SUM(units),0) FROM ownership_ledger "
            "WHERE user_id=:u AND property_id=:p",
            u=user_id,
            p=property_id,
        )[0][0]
    )


def _total_units(db, property_id: str) -> int:
    return int(
        db(
            "SELECT COALESCE(SUM(units),0) FROM ownership_ledger WHERE property_id=:p",
            p=property_id,
        )[0][0]
    )


def _set_balance(db, uid: str, amount: int) -> None:
    db("UPDATE wallets SET balance=:b WHERE user_id=:u", b=amount, u=uid)


def _balance(db, uid: str) -> float:
    return float(db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0])


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def _idem() -> dict:
    return {"Idempotency-Key": str(uuid.uuid4())}


def _tomorrow() -> dt.date:
    return dt.datetime.now(dt.UTC).date() + dt.timedelta(days=1)


async def _schedule(client, tok, **body) -> object:
    return await client.post("/api/v1/gifts", json=body, headers={**_h(tok), **_idem()})


# --- schedule: reservation + escrow ----------------------------------------- #
async def test_property_schedule_reserves_units(client, db):
    tok, uid = await _user(client, db, "gf-a@x.com")
    _kyc_verify(db, uid)
    pid = _seed_property(db)
    _ledger(db, uid, pid, 10)
    # reserve 4 of 10
    r1 = await _schedule(
        client,
        tok,
        recipient_name="Kid",
        recipient_email="gf-rcpt@x.com",
        asset_type="property_shares",
        property_id=pid,
        units=4,
        scheduled_for=_tomorrow().isoformat(),
    )
    assert r1.status_code == 201, r1.text
    # only 6 free now -> a 7-unit gift is rejected (units are reserved)
    r2 = await _schedule(
        client,
        tok,
        recipient_name="Kid",
        recipient_email="gf-rcpt@x.com",
        asset_type="property_shares",
        property_id=pid,
        units=7,
        scheduled_for=_tomorrow().isoformat(),
    )
    assert r2.status_code == 422 and r2.json()["error"]["code"] == "INSUFFICIENT_UNITS"


async def test_wallet_schedule_escrows_cash(client, db):
    tok, uid = await _user(client, db, "gf-w1@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 1000)
    r = await _schedule(
        client,
        tok,
        recipient_name="Kid",
        recipient_email="gf-wr@x.com",
        asset_type="wallet",
        amount="250.00",
        scheduled_for=_tomorrow().isoformat(),
    )
    assert r.status_code == 201, r.text
    assert _balance(db, uid) == 750.0  # escrowed (debited now)


async def test_wallet_schedule_insufficient_funds(client, db):
    tok, uid = await _user(client, db, "gf-w2@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 100)
    r = await _schedule(
        client,
        tok,
        recipient_name="Kid",
        recipient_email="gf-wr2@x.com",
        asset_type="wallet",
        amount="250.00",
        scheduled_for=_tomorrow().isoformat(),
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "INSUFFICIENT_FUNDS"


# --- execution (the cron) --------------------------------------------------- #
async def test_property_execution_atomic_and_idempotent(client, db, asession):
    from app.services import gift_service

    g_tok, g_id = await _user(client, db, "gf-giver@x.com")
    _kyc_verify(db, g_id)
    r_tok, r_id = await _user(client, db, "gf-recv@x.com")
    _kyc_verify(db, r_id)
    pid = _seed_property(db)
    _ledger(db, g_id, pid, 10)
    _set_balance(db, g_id, 100)  # used to prove zero-fee (no fee debit)
    await _schedule(
        client,
        g_tok,
        recipient_name="Recv",
        recipient_email="gf-recv@x.com",
        asset_type="property_shares",
        property_id=pid,
        units=4,
        scheduled_for=_tomorrow().isoformat(),
    )
    # run the cron AS-OF tomorrow: reminder + execution in one pass
    res = await gift_service.run_due(asession, now=dt.datetime.now(dt.UTC) + dt.timedelta(days=1))
    await asession.commit()
    assert res["executed"] == 1 and res["reminders_sent"] == 1
    assert _net(db, g_id, pid) == 6
    assert _net(db, r_id, pid) == 4
    assert _total_units(db, pid) == 10  # conserved
    assert _balance(db, g_id) == 100.0  # zero-fee: no fee debited

    # idempotent: a second run does not move again
    res2 = await gift_service.run_due(asession, now=dt.datetime.now(dt.UTC) + dt.timedelta(days=1))
    await asession.commit()
    assert res2["executed"] == 0
    assert _net(db, r_id, pid) == 4


async def test_wallet_execution_credits_recipient(client, db, asession):
    from app.services import gift_service

    g_tok, g_id = await _user(client, db, "gf-wgiver@x.com")
    _kyc_verify(db, g_id)
    r_tok, r_id = await _user(client, db, "gf-wrecv@x.com")
    _kyc_verify(db, r_id)
    _set_balance(db, g_id, 1000)
    _set_balance(db, r_id, 0)
    await _schedule(
        client,
        g_tok,
        recipient_name="Recv",
        recipient_email="gf-wrecv@x.com",
        asset_type="wallet",
        amount="250.00",
        scheduled_for=_tomorrow().isoformat(),
    )
    assert _balance(db, g_id) == 750.0  # escrowed at schedule
    await gift_service.run_due(asession, now=dt.datetime.now(dt.UTC) + dt.timedelta(days=1))
    await asession.commit()
    assert _balance(db, r_id) == 250.0  # credited from escrow
    assert _balance(db, g_id) == 750.0  # unchanged (already escrowed)


# --- cancel: release / refund ----------------------------------------------- #
async def test_cancel_releases_reservation(client, db):
    tok, uid = await _user(client, db, "gf-c1@x.com")
    _kyc_verify(db, uid)
    pid = _seed_property(db)
    _ledger(db, uid, pid, 5)
    r = await _schedule(
        client,
        tok,
        recipient_name="Kid",
        recipient_email="gf-cr@x.com",
        asset_type="property_shares",
        property_id=pid,
        units=5,
        scheduled_for=_tomorrow().isoformat(),
    )
    gid = r.json()["id"]
    # all 5 reserved -> another gift fails
    over = await _schedule(
        client,
        tok,
        recipient_name="Kid",
        recipient_email="gf-cr@x.com",
        asset_type="property_shares",
        property_id=pid,
        units=1,
        scheduled_for=_tomorrow().isoformat(),
    )
    assert over.status_code == 422
    # cancel releases the reservation
    c = await client.post(f"/api/v1/gifts/{gid}/cancel", headers=_h(tok))
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    ok = await _schedule(
        client,
        tok,
        recipient_name="Kid",
        recipient_email="gf-cr@x.com",
        asset_type="property_shares",
        property_id=pid,
        units=5,
        scheduled_for=_tomorrow().isoformat(),
    )
    assert ok.status_code == 201


async def test_cancel_refunds_wallet_escrow(client, db):
    tok, uid = await _user(client, db, "gf-c2@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 500)
    r = await _schedule(
        client,
        tok,
        recipient_name="Kid",
        recipient_email="gf-cr2@x.com",
        asset_type="wallet",
        amount="200.00",
        scheduled_for=_tomorrow().isoformat(),
    )
    assert _balance(db, uid) == 300.0
    c = await client.post(f"/api/v1/gifts/{r.json()['id']}/cancel", headers=_h(tok))
    assert c.status_code == 200
    assert _balance(db, uid) == 500.0  # refunded


# --- pending recipient materializes on KYC ---------------------------------- #
async def test_pending_property_materializes_on_kyc(client, db, asession):
    from app.services import gift_service

    g_tok, g_id = await _user(client, db, "gf-pg@x.com")
    _kyc_verify(db, g_id)
    pid = _seed_property(db)
    _ledger(db, g_id, pid, 8)
    await _schedule(
        client,
        g_tok,
        recipient_name="Future",
        recipient_email="gf-future@x.com",
        asset_type="property_shares",
        property_id=pid,
        units=8,
        scheduled_for=_tomorrow().isoformat(),
    )
    res = await gift_service.run_due(asession, now=dt.datetime.now(dt.UTC) + dt.timedelta(days=1))
    await asession.commit()
    assert res["pending"] == 1
    assert _net(db, g_id, pid) == 8  # units stay with giver, reserved
    assert db("SELECT 1 FROM scheduled_gifts WHERE status='pending'")

    # recipient registers + KYC -> materialize moves the units
    _rt, r_id = await _user(client, db, "gf-future@x.com")
    _kyc_verify(db, r_id)
    moved = await gift_service.materialize_for_user(asession, user_id=uuid.UUID(r_id))
    await asession.commit()
    assert moved == 1
    assert _net(db, g_id, pid) == 0
    assert _net(db, r_id, pid) == 8
    assert _total_units(db, pid) == 8  # conserved


async def test_pending_wallet_materializes_on_kyc(client, db, asession):
    from app.services import gift_service

    g_tok, g_id = await _user(client, db, "gf-pw@x.com")
    _kyc_verify(db, g_id)
    _set_balance(db, g_id, 500)
    await _schedule(
        client,
        g_tok,
        recipient_name="Future",
        recipient_email="gf-fut-w@x.com",
        asset_type="wallet",
        amount="200.00",
        scheduled_for=_tomorrow().isoformat(),
    )
    await gift_service.run_due(asession, now=dt.datetime.now(dt.UTC) + dt.timedelta(days=1))
    await asession.commit()
    assert _balance(db, g_id) == 300.0  # escrow still held (recipient not ready)

    _rt, r_id = await _user(client, db, "gf-fut-w@x.com")
    _kyc_verify(db, r_id)
    moved = await gift_service.materialize_for_user(asession, user_id=uuid.UUID(r_id))
    await asession.commit()
    assert moved == 1
    assert _balance(db, r_id) == 200.0
    assert _balance(db, g_id) == 300.0  # conserved


# --- recurrence ------------------------------------------------------------- #
async def test_recurrence_reenqueues_next_occurrence_once(client, db, asession):
    from app.services import gift_service

    g_tok, g_id = await _user(client, db, "gf-rec@x.com")
    _kyc_verify(db, g_id)
    r_tok, r_id = await _user(client, db, "gf-rec-r@x.com")
    _kyc_verify(db, r_id)
    pid = _seed_property(db)
    _ledger(db, g_id, pid, 10)
    r = await _schedule(
        client,
        g_tok,
        recipient_name="Recv",
        recipient_email="gf-rec-r@x.com",
        asset_type="property_shares",
        property_id=pid,
        units=2,
        recurring=True,
        scheduled_for=_tomorrow().isoformat(),
    )
    series = db("SELECT series_id FROM scheduled_gifts WHERE id=:i", i=r.json()["id"])[0][0]
    # run twice as-of tomorrow: execute + enqueue next year; second run must NOT duplicate
    asof = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
    await gift_service.run_due(asession, now=asof)
    await asession.commit()
    await gift_service.run_due(asession, now=asof)
    await asession.commit()
    rows = db("SELECT COUNT(*) FROM scheduled_gifts WHERE series_id=:s", s=series)[0][0]
    assert int(rows) == 2  # original (executed) + exactly one next-year occurrence
    nxt = db(
        "SELECT status FROM scheduled_gifts WHERE series_id=:s AND status='scheduled'", s=series
    )
    assert len(nxt) == 1
    assert _net(db, r_id, pid) == 2  # executed once, not twice


# --- asset scope rejected --------------------------------------------------- #
@pytest.mark.parametrize("asset", ["passive_income", "tokenized", "rental_returns", "allocation"])
async def test_disabled_assets_rejected(client, db, asset):
    tok, uid = await _user(client, db, f"gf-dis-{asset}@x.com")
    _kyc_verify(db, uid)
    r = await _schedule(
        client,
        tok,
        recipient_name="Kid",
        recipient_email="gf-dr@x.com",
        asset_type=asset,
        amount="10.00",
        scheduled_for=_tomorrow().isoformat(),
    )
    assert r.status_code == 422  # schema rejects non-real asset types


# --- owner scoping ---------------------------------------------------------- #
async def test_cancel_owner_scoped(client, db):
    a_tok, a_id = await _user(client, db, "gf-own-a@x.com")
    _kyc_verify(db, a_id)
    b_tok, b_id = await _user(client, db, "gf-own-b@x.com")
    _kyc_verify(db, b_id)
    _set_balance(db, a_id, 100)
    r = await _schedule(
        client,
        a_tok,
        recipient_name="Kid",
        recipient_email="gf-or@x.com",
        asset_type="wallet",
        amount="10.00",
        scheduled_for=_tomorrow().isoformat(),
    )
    foreign = await client.post(f"/api/v1/gifts/{r.json()['id']}/cancel", headers=_h(b_tok))
    assert foreign.status_code == 404


# --- the 7-day reminder fires once ------------------------------------------ #
async def test_reminder_fires_once(client, db, asession):
    from app.services import gift_service

    g_tok, g_id = await _user(client, db, "gf-rem@x.com")
    _kyc_verify(db, g_id)
    _set_balance(db, g_id, 100)
    in3 = (dt.datetime.now(dt.UTC).date() + dt.timedelta(days=3)).isoformat()
    await _schedule(
        client,
        g_tok,
        recipient_name="Kid",
        recipient_email="gf-remr@x.com",
        asset_type="wallet",
        amount="10.00",
        scheduled_for=in3,
    )
    # as-of today: within 7 days -> reminder; NOT yet due -> no execution
    res = await gift_service.run_due(asession, now=dt.datetime.now(dt.UTC))
    await asession.commit()
    assert res["reminders_sent"] == 1 and res["executed"] == 0
    # a second run does not re-send the reminder
    res2 = await gift_service.run_due(asession, now=dt.datetime.now(dt.UTC))
    await asession.commit()
    assert res2["reminders_sent"] == 0
    n = db(
        "SELECT COUNT(*) FROM notifications WHERE user_id=:u AND type='gift' "
        "AND title='Upcoming scheduled gift'",
        u=g_id,
    )[0][0]
    assert int(n) == 1


# --- run-due endpoint is admin-OR-cron gated -------------------------------- #
async def test_run_due_requires_admin_or_cron(client, db, monkeypatch):
    from app.core.config import get_settings

    # no auth -> 401
    assert (await client.post("/api/v1/admin/gifts/run-due")).status_code == 401
    # wrong secret -> 401 (with a configured secret)
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cr3t", raising=False)
    bad = await client.post("/api/v1/admin/gifts/run-due", headers={"X-Cron-Secret": "nope"})
    assert bad.status_code == 401
    # correct secret -> 200
    ok = await client.post("/api/v1/admin/gifts/run-due", headers={"X-Cron-Secret": "s3cr3t"})
    assert ok.status_code == 200
    # admin -> 200
    a_tok, _ = await _admin(client, db, "gf-cronadmin@x.com")
    assert (await client.post("/api/v1/admin/gifts/run-due", headers=_h(a_tok))).status_code == 200
