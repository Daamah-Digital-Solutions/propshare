"""Phase 15c — DB-backed tests for investor communications (developer updates).

Acceptance bar: a send fans out to the property's net-holders (Σ units > 0; fully-exited
excluded; a ledger-only secondary-style holder included), recording one recipient row per
holder linked to the created notification; recipient_count snapshot is real; email honours
the investment_updates preference (opt-out → in-app only, no outbox row); read_count is
real (notifications.read); history is owner-scoped; (update_id, user_id) is unique
(idempotent); empty audience is handled; validation → 422; auth 401 / non-owner-role 403;
notify() returns the created notification.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Notification
from app.services import notification_service

PW = "Passw0rd!23"


# --- helpers ---------------------------------------------------------------- #
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
    """Real user (ownership_ledger.user_id has a DB FK to users)."""
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "U"}
    )
    return str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])


def _seed_property(db, owner_id: str | None, *, status: str = "active") -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,owner_id,title,location,property_type,model,status,"
        "total_value,unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,:o,'Prop','Dubai','residential','ready-income',:st,1000000,100,100,100,100)",
        id=pid,
        o=owner_id,
        st=status,
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


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _send(
    client, token, pid, subject="Construction update", body="We poured the foundation."
):
    return await client.post(
        f"/api/v1/owner/properties/{pid}/updates",
        json={"subject": subject, "body": body},
        headers=_h(token),
    )


# --- fan-out / audience ----------------------------------------------------- #
async def test_send_fans_out_to_net_holders(client, db):
    tok, oid = await _owner(client, db, "uc-owner1@x.com")
    pid = _seed_property(db, oid)
    a = await _mk_user(client, db, "uc-a@x.com")
    b = await _mk_user(client, db, "uc-b@x.com")  # ledger-only (no investment row) — still a holder
    exited = await _mk_user(client, db, "uc-exited@x.com")
    _ledger(db, a, pid, 10)
    _ledger(db, b, pid, 5)
    _ledger(db, exited, pid, 10)
    _ledger(db, exited, pid, -10)  # net 0 → excluded

    r = await _send(client, tok, pid)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["recipient_count"] == 2  # a + b; exited excluded
    assert body["read_count"] == 0

    # one recipient row per holder, each linked to a real notification
    recips = db(
        "SELECT user_id, notification_id FROM developer_update_recipients WHERE update_id=:u",
        u=body["id"],
    )
    assert len(recips) == 2
    assert all(row[1] is not None for row in recips)  # notification_id linked
    # each holder got an in-app notification of the right type
    for uid in (a, b):
        n = db("SELECT type FROM notifications WHERE user_id=:u", u=uid)
        assert len(n) == 1 and n[0][0] == "developer_update"
    assert not db("SELECT 1 FROM notifications WHERE user_id=:u", u=exited)


async def test_empty_audience(client, db):
    tok, oid = await _owner(client, db, "uc-empty@x.com")
    pid = _seed_property(db, oid)  # no holders
    r = await _send(client, tok, pid)
    assert r.status_code == 201
    assert r.json()["recipient_count"] == 0
    assert not db("SELECT 1 FROM developer_update_recipients")


# --- email preference gate -------------------------------------------------- #
async def test_email_respects_preference(client, db):
    tok, oid = await _owner(client, db, "uc-owner2@x.com")
    pid = _seed_property(db, oid)
    on = await _mk_user(client, db, "uc-on@x.com")
    off = await _mk_user(client, db, "uc-off@x.com")
    _ledger(db, on, pid, 10)
    _ledger(db, off, pid, 10)
    # 'off' opts out of investment-update emails (in-app still always delivered)
    db(
        "INSERT INTO notification_preferences (user_id, email_investment_updates) "
        "VALUES (:u, false)",
        u=off,
    )

    await _send(client, tok, pid)
    # both got an in-app notification
    assert len(db("SELECT 1 FROM notifications WHERE user_id=:u", u=on)) == 1
    assert len(db("SELECT 1 FROM notifications WHERE user_id=:u", u=off)) == 1
    # only the opted-in holder got an email outbox row
    assert len(db("SELECT 1 FROM email_outbox WHERE user_id=:u", u=on)) == 1
    assert len(db("SELECT 1 FROM email_outbox WHERE user_id=:u", u=off)) == 0


# --- read count (real) ------------------------------------------------------ #
async def test_read_count_is_real(client, db):
    tok, oid = await _owner(client, db, "uc-owner3@x.com")
    pid = _seed_property(db, oid)
    a = await _mk_user(client, db, "uc-r-a@x.com")
    b = await _mk_user(client, db, "uc-r-b@x.com")
    _ledger(db, a, pid, 10)
    _ledger(db, b, pid, 10)
    await _send(client, tok, pid)
    # holder A reads their notification
    db("UPDATE notifications SET read=true WHERE user_id=:u", u=a)

    rows = (await client.get("/api/v1/owner/updates", headers=_h(tok))).json()
    assert len(rows) == 1
    assert rows[0]["recipient_count"] == 2
    assert rows[0]["read_count"] == 1  # only A read


# --- owner scoping ---------------------------------------------------------- #
async def test_non_owner_cannot_send_or_list(client, db):
    tok_a, oid_a = await _owner(client, db, "uc-a-owner@x.com")
    tok_b, _oid_b = await _owner(client, db, "uc-b-owner@x.com")
    pid = _seed_property(db, oid_a)
    s = await _send(client, tok_b, pid)
    assert s.status_code == 403 and s.json()["error"]["code"] == "NOT_PROPERTY_OWNER"
    lst = await client.get(f"/api/v1/owner/updates?property_id={pid}", headers=_h(tok_b))
    assert lst.status_code == 403


async def test_history_owner_scoped(client, db):
    tok_a, oid_a = await _owner(client, db, "uc-hist-a@x.com")
    tok_b, oid_b = await _owner(client, db, "uc-hist-b@x.com")
    pa = _seed_property(db, oid_a)
    pb = _seed_property(db, oid_b)
    ha = await _mk_user(client, db, "uc-hist-ha@x.com")
    _ledger(db, ha, pa, 10)
    await _send(client, tok_a, pa, subject="A update")
    await _send(client, tok_b, pb, subject="B update")

    a_rows = (await client.get("/api/v1/owner/updates", headers=_h(tok_a))).json()
    assert [r["subject"] for r in a_rows] == ["A update"]  # only owner A's update


# --- idempotency guard ------------------------------------------------------ #
async def test_recipient_unique_constraint(client, db):
    tok, oid = await _owner(client, db, "uc-uniq@x.com")
    pid = _seed_property(db, oid)
    a = await _mk_user(client, db, "uc-uniq-a@x.com")
    _ledger(db, a, pid, 10)
    body = (await _send(client, tok, pid)).json()
    # a duplicate (update_id, user_id) recipient is rejected by the UNIQUE constraint
    with pytest.raises(IntegrityError):
        db(
            "INSERT INTO developer_update_recipients (update_id, user_id) VALUES (:u,:usr)",
            u=body["id"],
            usr=a,
        )


# --- validation + auth ------------------------------------------------------ #
async def test_validation(client, db):
    tok, oid = await _owner(client, db, "uc-val@x.com")
    pid = _seed_property(db, oid)
    assert (await _send(client, tok, pid, subject="", body="x")).status_code == 422
    assert (await _send(client, tok, pid, subject="x", body="")).status_code == 422


async def test_auth_and_role(client, db):
    tok, oid = await _owner(client, db, "uc-auth-owner@x.com")
    pid = _seed_property(db, oid)
    assert (
        await client.post(
            f"/api/v1/owner/properties/{pid}/updates", json={"subject": "s", "body": "b"}
        )
    ).status_code == 401
    assert (await client.get("/api/v1/owner/updates")).status_code == 401
    inv = await _investor_token(client, db, "uc-plain-inv@x.com")
    assert (await _send(client, inv, pid)).status_code == 403
    assert (await client.get("/api/v1/owner/updates", headers=_h(inv))).status_code == 403


# --- notify() return extension ---------------------------------------------- #
async def test_notify_returns_created_notification(client, db, asession):
    uid = uuid.UUID(await _mk_user(client, db, "uc-notify@x.com"))  # notifications.user_id has a FK
    n = await notification_service.notify(asession, user_id=uid, type="x", title="T", message="M")
    assert n is not None and n.id is not None
    await asession.flush()
    row = (await asession.execute(select(Notification).where(Notification.id == n.id))).scalar_one()
    assert row.user_id == uid and row.read is False
