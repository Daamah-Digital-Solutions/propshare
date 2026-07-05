"""Group 6 — DB-backed tests for installment plans (progressive vesting).

Acceptance: plan creation reserves the whole allocation out of available_units + charges the
down payment + vests its slice atomically; installments vest more units per payment; units
conserve (available + ledger + plan-unvested == total); pre-handover vested units are RESERVED
(can't be listed) and EXCLUDED from rental yield, then released/included at handover; the cron
charges due installments, marks a missed one overdue (grace, no forfeit) and retries, sends a
one-time reminder; completion when all payments are paid; idempotent; owner-scoped; the run-due
endpoint is admin-OR-cron gated; the fee is admin-configurable + snapshotted at creation.
"""

from __future__ import annotations

import datetime as dt
import uuid

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


def _seed_property(db, *, unit_price: int = 100, units: int = 100) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,"
        "total_value,unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Tower','Dubai','residential','installment','active',:tv,:up,:tu,:au,100)",
        id=pid,
        tv=unit_price * units,
        up=unit_price,
        tu=units,
        au=units,
    )
    return pid


def _set_balance(db, uid: str, amount: int) -> None:
    db("UPDATE wallets SET balance=:b WHERE user_id=:u", b=amount, u=uid)


def _balance(db, uid: str) -> float:
    return float(db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0])


def _net(db, uid: str, pid: str) -> int:
    return int(
        db(
            "SELECT COALESCE(SUM(units),0) FROM ownership_ledger "
            "WHERE user_id=:u AND property_id=:p",
            u=uid,
            p=pid,
        )[0][0]
    )


def _available(db, pid: str) -> int:
    return int(db("SELECT available_units FROM properties WHERE id=:p", p=pid)[0][0])


def _total_ledger(db, pid: str) -> int:
    return int(
        db("SELECT COALESCE(SUM(units),0) FROM ownership_ledger WHERE property_id=:p", p=pid)[0][0]
    )


def _plan_unvested(db, pid: str) -> int:
    return int(
        db(
            "SELECT COALESCE(SUM(units_total - vested_units),0) FROM installment_plans "
            "WHERE property_id=:p AND status='active'",
            p=pid,
        )[0][0]
    )


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def _idem() -> dict:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def _create(client, tok, pid, amount=1200, duration=12, **hdr):
    return await client.post(
        "/api/v1/installments",
        json={"property_id": pid, "amount": amount, "duration_months": duration},
        headers={**_h(tok), **(hdr or _idem())},
    )


# --- create: reserve + down payment + vest ---------------------------------- #
async def test_create_reserves_allocation_and_pays_down_payment(client, db):
    tok, uid = await _user(client, db, "in-a@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 100000)
    pid = _seed_property(db)  # unit_price 100, 100 units
    r = await _create(client, tok, pid, amount=1200, duration=12)  # 12 units, 25% down
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["units_total"] == 12 and plan["down_payment_pct"] == 25
    assert len(plan["payments"]) == 12
    down = plan["payments"][0]
    assert down["kind"] == "downpayment" and down["status"] == "paid"
    assert down["base_amount"] == "300.00" and down["fee_amount"] == "12.00"  # 25% of 1200, 4% fee
    assert down["vest_units"] == 3  # 300/1200 * 12
    # allocation reserved out of the pool; only the down slice is on the ledger
    assert _available(db, pid) == 88  # 100 - 12
    assert _net(db, uid, pid) == 3
    assert plan["vested_units"] == 3
    assert _balance(db, uid) == 100000 - 312  # base 300 + 4% fee 12
    # conservation: available + ledger + plan-unvested == total
    assert _available(db, pid) + _total_ledger(db, pid) + _plan_unvested(db, pid) == 100


async def test_create_insufficient_units_rejected(client, db):
    tok, uid = await _user(client, db, "in-few@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 100000)
    pid = _seed_property(db, unit_price=100, units=5)
    r = await _create(client, tok, pid, amount=1000, duration=12)  # wants 10 units, only 5
    assert r.status_code == 409 and r.json()["error"]["code"] == "INSUFFICIENT_UNITS"


async def test_create_down_payment_insufficient_funds_rolls_back(client, db):
    tok, uid = await _user(client, db, "in-poor@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 50)  # can't cover the 312 down payment
    pid = _seed_property(db)
    r = await _create(client, tok, pid, amount=1200, duration=12)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
    # rolled back: allocation not reserved, no plan, no ledger
    assert _available(db, pid) == 100
    assert _net(db, uid, pid) == 0
    assert db("SELECT COUNT(*) FROM installment_plans")[0][0] == 0


# --- pay installments to completion (conservation + handover) --------------- #
async def test_pay_to_completion_conserves_and_completes(client, db):
    tok, uid = await _user(client, db, "in-complete@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 100000)
    pid = _seed_property(db)
    plan = (await _create(client, tok, pid, amount=1200, duration=12)).json()
    # pay every scheduled installment (manual early pay is allowed)
    for p in plan["payments"]:
        if p["status"] != "paid":
            resp = await client.post(
                f"/api/v1/installments/payments/{p['id']}/pay", headers={**_h(tok), **_idem()}
            )
            assert resp.status_code == 200, resp.text
    final = (await client.get("/api/v1/installments", headers=_h(tok))).json()[0]
    assert final["status"] == "completed"
    assert final["vested_units"] == 12
    assert _net(db, uid, pid) == 12  # full ownership on the ledger at handover
    assert _available(db, pid) == 88
    assert _plan_unvested(db, pid) == 0
    assert _available(db, pid) + _total_ledger(db, pid) + _plan_unvested(db, pid) == 100


# --- pre-handover: units reserved (not sellable) ---------------------------- #
async def test_pre_handover_units_are_reserved(client, db, asession):
    from app.services import secondary_service

    tok, uid = await _user(client, db, "in-reserve@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 100000)
    pid = _seed_property(db)
    await _create(client, tok, pid, amount=1200, duration=12)  # 3 units vested, plan active
    reserved = await secondary_service.reserved_units(asession, uuid.UUID(uid), uuid.UUID(pid))
    assert reserved == 3  # the vested units are held until handover
    # attempting to list any of them fails (all reserved)
    try:
        await secondary_service.create_listing(
            asession,
            seller_id=uuid.UUID(uid),
            property_id=uuid.UUID(pid),
            units=1,
            price_per_unit=100,
        )
        raised = False
    except Exception as e:  # AppError INSUFFICIENT_UNITS
        raised = getattr(e, "code", "") == "INSUFFICIENT_UNITS"
    assert raised


# --- rental yield excludes pre-handover, includes at handover --------------- #
async def test_yield_excluded_pre_handover_then_included(client, db, asession):
    from app.services.distribution_service import _ownership

    tok, uid = await _user(client, db, "in-yield@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 100000)
    pid = _seed_property(db)
    plan = (await _create(client, tok, pid, amount=1200, duration=12)).json()

    # mid-plan: 3 units on the ledger but ALL under an active plan -> excluded from yield
    owners = await _ownership(asession, uuid.UUID(pid))
    assert all(str(u) != uid for u, _ in owners)

    # complete the plan
    for p in plan["payments"]:
        if p["status"] != "paid":
            await client.post(
                f"/api/v1/installments/payments/{p['id']}/pay", headers={**_h(tok), **_idem()}
            )
    owners_after = await _ownership(asession, uuid.UUID(pid))
    assert (uuid.UUID(uid), 12) in owners_after  # now yield-eligible at handover


# --- cron: due charge, missed=overdue (grace), retry, reminder-once --------- #
async def test_cron_charges_due_and_completes(client, db, asession):
    from app.services import installment_service

    tok, uid = await _user(client, db, "in-cron@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 100000)
    pid = _seed_property(db)
    await _create(client, tok, pid, amount=1200, duration=12)
    # 13 months later everything is due -> the cron charges all remaining installments
    res = await installment_service.run_due(
        asession, now=dt.datetime.now(dt.UTC) + dt.timedelta(days=32 * 13)
    )
    await asession.commit()
    assert res["paid"] == 11 and res["overdue"] == 0
    assert _net(db, uid, pid) == 12
    status = db("SELECT status FROM installment_plans WHERE property_id=:p", p=pid)[0][0]
    assert status == "completed"


async def test_cron_missed_payment_is_overdue_then_retried(client, db, asession):
    from app.services import installment_service

    tok, uid = await _user(client, db, "in-miss@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 100000)
    pid = _seed_property(db)
    await _create(client, tok, pid, amount=1200, duration=12)
    _set_balance(db, uid, 0)  # drain the wallet -> next installment can't be charged
    asof = dt.datetime.now(dt.UTC) + dt.timedelta(days=40)  # first installment now due
    res = await installment_service.run_due(asession, now=asof)
    await asession.commit()
    assert res["overdue"] >= 1 and res["paid"] == 0
    assert _net(db, uid, pid) == 3  # nothing vested beyond the down payment
    assert db("SELECT COUNT(*) FROM installment_payments WHERE status='overdue'")[0][0] >= 1
    # missed-payment rule: GRACE — plan stays active, vested units untouched
    assert db("SELECT status FROM installment_plans WHERE property_id=:p", p=pid)[0][0] == "active"
    # top up + retry -> the overdue installment is charged
    _set_balance(db, uid, 100000)
    res2 = await installment_service.run_due(asession, now=asof)
    await asession.commit()
    assert res2["paid"] >= 1
    assert _net(db, uid, pid) > 3


async def test_cron_reminder_sent_once(client, db, asession):
    from app.services import installment_service

    tok, uid = await _user(client, db, "in-remind@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 100000)
    pid = _seed_property(db)
    plan = (await _create(client, tok, pid, amount=1200, duration=12)).json()
    seq1_due = dt.date.fromisoformat(plan["payments"][1]["due_date"])
    asof = dt.datetime.combine(seq1_due - dt.timedelta(days=2), dt.time(12, 0), dt.UTC)
    res = await installment_service.run_due(asession, now=asof)
    await asession.commit()
    assert res["reminders_sent"] >= 1 and res["paid"] == 0  # due-soon, not yet due
    await installment_service.run_due(asession, now=asof)  # second run must not re-send
    await asession.commit()
    # not re-sent for seq1 (reminder_sent_at guards it)
    n = db(
        "SELECT COUNT(*) FROM notifications WHERE user_id=:u AND type='installment' "
        "AND title='Upcoming installment payment'",
        u=uid,
    )[0][0]
    assert int(n) == 1


# --- idempotency ------------------------------------------------------------ #
async def test_create_idempotent(client, db):
    tok, uid = await _user(client, db, "in-idem@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 100000)
    pid = _seed_property(db)
    hdr = _idem()
    r1 = await _create(client, tok, pid, amount=1200, duration=12, **hdr)
    r2 = await _create(client, tok, pid, amount=1200, duration=12, **hdr)  # replay
    assert r1.json()["id"] == r2.json()["id"]
    assert db("SELECT COUNT(*) FROM installment_plans")[0][0] == 1  # no double plan
    assert _available(db, pid) == 88  # reserved once, not twice


# --- owner scoping ---------------------------------------------------------- #
async def test_pay_owner_scoped(client, db):
    a_tok, a_id = await _user(client, db, "in-own-a@x.com")
    b_tok, b_id = await _user(client, db, "in-own-b@x.com")
    _kyc_verify(db, a_id)
    _kyc_verify(db, b_id)
    _set_balance(db, a_id, 100000)
    pid = _seed_property(db)
    plan = (await _create(client, a_tok, pid, amount=1200, duration=12)).json()
    unpaid = next(p for p in plan["payments"] if p["status"] != "paid")
    foreign = await client.post(
        f"/api/v1/installments/payments/{unpaid['id']}/pay", headers={**_h(b_tok), **_idem()}
    )
    assert foreign.status_code == 404


# --- fee is admin-configurable + snapshotted -------------------------------- #
async def test_fee_admin_configurable_and_snapshotted(client, db):
    tok, uid = await _user(client, db, "in-fee@x.com")
    _kyc_verify(db, uid)
    _set_balance(db, uid, 1000000)
    pid = _seed_property(db, units=100)
    # the test harness truncates platform_settings (get_setting falls back to DEFAULTS),
    # so upsert the row to exercise an admin-set rate.
    db(
        "INSERT INTO platform_settings (key,value) VALUES ('installment_fee_pct','6.0') "
        "ON CONFLICT (key) DO UPDATE SET value='6.0'"
    )
    plan1 = (await _create(client, tok, pid, amount=1200, duration=12)).json()
    assert float(plan1["fee_rate"]) == 6.0
    assert plan1["payments"][0]["fee_amount"] == "18.00"  # 300 * 6%
    # change the admin rate -> the existing plan keeps its snapshot; a NEW plan uses the new rate
    db("UPDATE platform_settings SET value='10.0' WHERE key='installment_fee_pct'")
    plan2 = (await _create(client, tok, pid, amount=1200, duration=12)).json()
    assert float(plan2["fee_rate"]) == 10.0
    assert plan2["payments"][0]["fee_amount"] == "30.00"  # 300 * 10%
    # plan1 unchanged (snapshot)
    again = (await client.get("/api/v1/installments", headers=_h(tok))).json()
    p1 = next(p for p in again if p["id"] == plan1["id"])
    assert float(p1["fee_rate"]) == 6.0
    assert p1["payments"][0]["fee_amount"] == "18.00"


# --- the run-due endpoint is admin-OR-cron gated ---------------------------- #
async def test_run_due_requires_admin_or_cron(client, db, monkeypatch):
    from app.core.config import get_settings

    assert (await client.post("/api/v1/admin/installments/run-due")).status_code == 401
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cr3t", raising=False)
    bad = await client.post("/api/v1/admin/installments/run-due", headers={"X-Cron-Secret": "nope"})
    assert bad.status_code == 401
    ok = await client.post(
        "/api/v1/admin/installments/run-due", headers={"X-Cron-Secret": "s3cr3t"}
    )
    assert ok.status_code == 200
    a_tok, _ = await _admin(client, db, "in-cronadmin@x.com")
    assert (
        await client.post("/api/v1/admin/installments/run-due", headers=_h(a_tok))
    ).status_code == 200


# --- the installment fee reaches the property detail (server-driven) -------- #
async def test_property_detail_exposes_installment_fee(client, db):
    _tok, _uid = await _user(client, db, "in-detail@x.com")
    pid = _seed_property(db)
    detail = (await client.get(f"/api/v1/properties/{pid}")).json()
    assert "installment_fee" in detail["fees"]
