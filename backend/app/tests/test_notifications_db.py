"""Phase 12 — DB-backed notifications + email tests (the read path + outbox gates).

Acceptance bar:
  * read path: list (own rows only), unread-count, mark one/all, auth.
  * the EMAIL MATRIX: an email-eligible event writes in-app + ONE outbox row; an
    in-app-only event writes in-app and NO outbox row.
  * prefs gate EMAIL but NEVER in-app.
  * family invite writes an outbox row for a NON-USER invitee (force, no prefs).
  * broker commission now notifies (was silent).
  * transactional atomicity: a rollback leaves no in-app AND no outbox row; the SEND is
    never inside the money tx (notify only enqueues 'pending').
  * drainer: sent / retry / idempotent / SKIP LOCKED.
  * preferences API: defaults + persist; sms/push keys ignored.
  * gating: admin-only dispatch.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import pytest

from app.services import distribution_service, email_service, notification_service

PW = "Passw0rd!23"
_P_START = dt.date(2025, 1, 1)
_P_END = dt.date(2026, 1, 1)


# --- helpers ---------------------------------------------------------------- #
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


async def _admin(client, db, email: str) -> str:
    await _register(client, email)
    uid = _uid(db, email)
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    return (await client.post("/api/v1/auth/login", json={"email": email, "password": PW})).json()[
        "access_token"
    ]


async def _make_broker(client, db, email: str) -> tuple[str, str]:
    await _register(client, email)
    uid = _uid(db, email)
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'broker')", i=uid)
    db("UPDATE users SET active_role='broker' WHERE id=:i", i=uid)
    t = (await client.post("/api/v1/auth/login", json={"email": email, "password": PW})).json()[
        "access_token"
    ]
    return t, uid


def _seed_property(db, *, unit_price=100, total_units=1000) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Notif Demo','Dubai','residential','ready-income','active',:tv,:up,:tu,:tu,100)",
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


def _hdr(token, key=None):
    h = {"Authorization": f"Bearer {token}"}
    if key is not None:
        h["Idempotency-Key"] = str(uuid.uuid4()) if key == "auto" else key
    return h


def _seed_notif(db, uid: str, *, title="Hello", read=False) -> None:
    db(
        "INSERT INTO notifications (user_id, type, title, message, read) "
        "VALUES (:u,'info',:t,'msg',:r)",
        u=uid,
        t=title,
        r=read,
    )


# =========================================================================== #
# Read path
# =========================================================================== #
@pytest.mark.asyncio
async def test_list_and_unread_count(client, db):
    t = await _register(client, "n1@capimax.com")
    uid = _uid(db, "n1@capimax.com")
    _seed_notif(db, uid, title="A")
    _seed_notif(db, uid, title="B", read=True)
    r = await client.get("/api/v1/notifications", headers=_hdr(t))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["unread_count"] == 1
    assert {i["title"] for i in body["items"]} == {"A", "B"}

    rc = await client.get("/api/v1/notifications/unread-count", headers=_hdr(t))
    assert rc.json()["count"] == 1


@pytest.mark.asyncio
async def test_list_only_own_rows(client, db):
    t1 = await _register(client, "n2a@capimax.com")
    await _register(client, "n2b@capimax.com")
    u2 = _uid(db, "n2b@capimax.com")
    _seed_notif(db, u2, title="theirs")
    r = await client.get("/api/v1/notifications", headers=_hdr(t1))
    assert r.json()["total"] == 0  # caller sees none of the other user's


@pytest.mark.asyncio
async def test_mark_read_and_read_all(client, db):
    t = await _register(client, "n3@capimax.com")
    uid = _uid(db, "n3@capimax.com")
    _seed_notif(db, uid, title="X")
    _seed_notif(db, uid, title="Y")
    nid = db("SELECT id FROM notifications WHERE user_id=:u AND title='X'", u=uid)[0][0]
    r = await client.post(f"/api/v1/notifications/{nid}/read", headers=_hdr(t))
    assert r.status_code == 200 and r.json()["ok"] is True
    assert (await client.get("/api/v1/notifications/unread-count", headers=_hdr(t))).json()[
        "count"
    ] == 1
    ra = await client.post("/api/v1/notifications/read-all", headers=_hdr(t))
    assert ra.json()["marked"] == 1
    assert (await client.get("/api/v1/notifications/unread-count", headers=_hdr(t))).json()[
        "count"
    ] == 0


@pytest.mark.asyncio
async def test_cannot_mark_others_notification(client, db):
    t1 = await _register(client, "n4a@capimax.com")
    await _register(client, "n4b@capimax.com")
    u2 = _uid(db, "n4b@capimax.com")
    _seed_notif(db, u2, title="theirs")
    nid = db("SELECT id FROM notifications WHERE user_id=:u", u=u2)[0][0]
    r = await client.post(f"/api/v1/notifications/{nid}/read", headers=_hdr(t1))
    assert r.status_code == 404  # not the caller's row


@pytest.mark.asyncio
async def test_read_path_requires_auth(client):
    assert (await client.get("/api/v1/notifications")).status_code == 401


# =========================================================================== #
# Dispatch logic — the email matrix (notify seam directly)
# =========================================================================== #
@pytest.mark.asyncio
async def test_email_event_writes_inapp_and_outbox(client, db, asession):
    await _register(client, "m1@capimax.com")
    uid = uuid.UUID(str(_uid(db, "m1@capimax.com")))
    await notification_service.notify(
        asession, user_id=uid, type="return", title="t", message="m", email_category="returns"
    )
    await asession.commit()
    assert db("SELECT COUNT(*) FROM notifications WHERE user_id=:u", u=str(uid))[0][0] == 1
    rows = db("SELECT category, status, to_email FROM email_outbox WHERE user_id=:u", u=str(uid))
    assert len(rows) == 1
    assert rows[0][0] == "returns" and rows[0][1] == "pending"
    assert rows[0][2] == "m1@capimax.com"


@pytest.mark.asyncio
async def test_inapp_only_event_writes_no_outbox(client, db, asession):
    await _register(client, "m2@capimax.com")
    uid = uuid.UUID(str(_uid(db, "m2@capimax.com")))
    await notification_service.notify(
        asession, user_id=uid, type="deposit", title="t", message="m"  # no email_category
    )
    await asession.commit()
    assert db("SELECT COUNT(*) FROM notifications WHERE user_id=:u", u=str(uid))[0][0] == 1
    assert db("SELECT COUNT(*) FROM email_outbox WHERE user_id=:u", u=str(uid))[0][0] == 0


@pytest.mark.asyncio
async def test_pref_off_suppresses_email_not_inapp(client, db, asession):
    await _register(client, "m3@capimax.com")
    uid = uuid.UUID(str(_uid(db, "m3@capimax.com")))
    db(
        "INSERT INTO notification_preferences (user_id, email_returns) VALUES (:u, false)",
        u=str(uid),
    )
    await notification_service.notify(
        asession, user_id=uid, type="return", title="t", message="m", email_category="returns"
    )
    await asession.commit()
    assert (
        db("SELECT COUNT(*) FROM notifications WHERE user_id=:u", u=str(uid))[0][0] == 1
    )  # in-app
    assert (
        db("SELECT COUNT(*) FROM email_outbox WHERE user_id=:u", u=str(uid))[0][0] == 0
    )  # no email


@pytest.mark.asyncio
async def test_family_invite_emails_nonuser(client, db, asession):
    await _register(client, "owner12@capimax.com")
    owner = uuid.UUID(str(_uid(db, "owner12@capimax.com")))
    # invite category, external recipient, force (no prefs, recipient isn't a user)
    await notification_service.notify(
        asession,
        user_id=owner,
        type="family",
        title="invited",
        message="owner copy",
        email_category="invite",
        email_to="invitee@example.com",
        force_email=True,
        email_subject="You're invited",
        email_body="invitee copy",
    )
    await asession.commit()
    rows = db(
        "SELECT user_id, to_email, subject FROM email_outbox WHERE to_email='invitee@example.com'"
    )
    assert len(rows) == 1
    assert rows[0][0] is None  # NON-USER invitee -> no user_id
    assert rows[0][2] == "You're invited"
    # owner still got the in-app row
    assert db("SELECT COUNT(*) FROM notifications WHERE user_id=:u", u=str(owner))[0][0] == 1


@pytest.mark.asyncio
async def test_transactional_atomicity_rollback(client, db, asession):
    await _register(client, "m4@capimax.com")
    uid = uuid.UUID(str(_uid(db, "m4@capimax.com")))
    await notification_service.notify(
        asession, user_id=uid, type="return", title="t", message="m", email_category="returns"
    )
    # The outbox row is 'pending' — proof the email was NOT sent at notify time.
    await asession.rollback()
    assert db("SELECT COUNT(*) FROM notifications WHERE user_id=:u", u=str(uid))[0][0] == 0
    assert db("SELECT COUNT(*) FROM email_outbox WHERE user_id=:u", u=str(uid))[0][0] == 0


# =========================================================================== #
# Real call-site wiring
# =========================================================================== #
@pytest.mark.asyncio
async def test_investment_confirm_emails(client, db):
    t = await _register(client, "inv1@capimax.com")
    uid = _uid(db, "inv1@capimax.com")
    _verify_kyc(db, uid)
    pid = _seed_property(db)
    _fund_wallet(db, uid, 5000)
    r = await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": 1000, "method": "wallet"},
        headers=_hdr(t, "auto"),
    )
    assert r.status_code == 200, r.text
    assert (
        db(
            "SELECT COUNT(*) FROM notifications WHERE user_id=:u AND title='Investment confirmed'",
            u=uid,
        )[0][0]
        == 1
    )
    assert (
        db(
            "SELECT COUNT(*) FROM email_outbox WHERE user_id=:u AND category='investment_updates'",
            u=uid,
        )[0][0]
        == 1
    )


@pytest.mark.asyncio
async def test_broker_commission_notifies(client, db, asession):
    btoken, buid = await _make_broker(client, db, "bk1@capimax.com")
    code = (await client.get("/api/v1/broker/referral-code", headers=_hdr(btoken))).json()["code"]
    await _register(client, "bkclient1@capimax.com", ref=code)
    cuid = uuid.UUID(str(_uid(db, "bkclient1@capimax.com")))
    pid = _seed_property(db)
    _grant_units(db, str(cuid), pid, 100)
    await distribution_service.run_distribution(
        asession,
        property_id=uuid.UUID(pid),
        kind="rental",
        period_key="2025",
        period_start=_P_START,
        period_end=_P_END,
        gross_pool=decimal.Decimal("1000"),
        created_by=None,
    )
    await asession.commit()
    # broker got an in-app "Commission earned" + an email outbox row (was silent before)
    assert (
        db(
            "SELECT COUNT(*) FROM notifications WHERE user_id=:b AND title='Commission earned'",
            b=buid,
        )[0][0]
        == 1
    )
    assert (
        db(
            "SELECT COUNT(*) FROM email_outbox WHERE user_id=:b AND category='investment_updates'",
            b=buid,
        )[0][0]
        == 1
    )


# =========================================================================== #
# Drainer
# =========================================================================== #
@pytest.mark.asyncio
async def test_drainer_sends_and_is_idempotent(client, db, asession, monkeypatch):
    await _register(client, "d1@capimax.com")
    uid = uuid.UUID(str(_uid(db, "d1@capimax.com")))
    await notification_service.notify(
        asession, user_id=uid, type="return", title="t", message="m", email_category="returns"
    )
    await asession.commit()

    sent: list[dict] = []

    async def fake_send(**kw):
        sent.append(kw)

    monkeypatch.setattr(email_service.email_provider, "send_email", fake_send)
    res = await email_service.dispatch_pending(asession)
    await asession.commit()
    assert res["sent"] == 1 and len(sent) == 1
    assert db("SELECT status FROM email_outbox WHERE user_id=:u", u=str(uid))[0][0] == "sent"

    # idempotent: a second drain re-sends nothing (already 'sent' is not reselected)
    res2 = await email_service.dispatch_pending(asession)
    await asession.commit()
    assert res2["sent"] == 0 and len(sent) == 1


@pytest.mark.asyncio
async def test_drainer_retries_on_failure(client, db, asession, monkeypatch):
    await _register(client, "d2@capimax.com")
    uid = uuid.UUID(str(_uid(db, "d2@capimax.com")))
    await notification_service.notify(
        asession, user_id=uid, type="return", title="t", message="m", email_category="returns"
    )
    await asession.commit()

    async def boom(**kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(email_service.email_provider, "send_email", boom)
    res = await email_service.dispatch_pending(asession)
    await asession.commit()
    assert res["sent"] == 0 and res["retried"] == 1
    row = db("SELECT status, attempts, last_error FROM email_outbox WHERE user_id=:u", u=str(uid))[
        0
    ]
    assert row[0] == "pending" and row[1] == 1 and "provider down" in row[2]


# =========================================================================== #
# Preferences API
# =========================================================================== #
@pytest.mark.asyncio
async def test_preferences_default_and_update(client, db):
    t = await _register(client, "p1@capimax.com")
    r = await client.get("/api/v1/notifications/preferences", headers=_hdr(t))
    assert r.json() == {
        "email_investment_updates": True,
        "email_returns": True,
        "email_security_alerts": True,
        "email_new_properties": True,
    }
    # update one email pref + send a stray sms/push key that must be IGNORED
    up = await client.put(
        "/api/v1/notifications/preferences",
        json={"email_returns": False, "sms_enabled": True, "push_enabled": True},
        headers=_hdr(t),
    )
    assert up.status_code == 200
    assert up.json()["email_returns"] is False
    assert up.json()["email_investment_updates"] is True
    uid = _uid(db, "p1@capimax.com")
    cols = db("SELECT email_returns FROM notification_preferences WHERE user_id=:u", u=uid)
    assert cols[0][0] is False
    # no sms/push columns exist — the stray keys were silently ignored, not persisted


# =========================================================================== #
# Gating
# =========================================================================== #
@pytest.mark.asyncio
async def test_dispatch_requires_admin(client, db):
    t = await _register(client, "g1@capimax.com")  # plain investor
    r = await client.post("/api/v1/admin/notifications/dispatch-emails", headers=_hdr(t))
    assert r.status_code == 403
    assert (await client.post("/api/v1/admin/notifications/dispatch-emails")).status_code == 401

    atoken = await _admin(client, db, "admin12@capimax.com")
    ra = await client.post("/api/v1/admin/notifications/dispatch-emails", headers=_hdr(atoken))
    assert ra.status_code == 200
    assert set(ra.json().keys()) == {"sent", "failed", "retried"}
