"""Batch C — tickets & operations (client doc §28, §29, §33, §34).

* a second ticket from the same person in the same category within 24h is flagged as a
  possible duplicate (linked, never blocked) — on the ticket and in the inbox email;
* SLA: an open ticket with no public staff reply past its hours (by priority, from
  settings) is escalated exactly once: priority high, breach recorded, admins notified,
  inbox emailed, audited; an internal note does not count as a reply; a public reply
  stops the clock; re-running is a no-op;
* CSAT: only the owner, only once resolved/closed, 1..5;
* the daily digest is counts only (no ticket bodies, no chat text) and is queued to the
  inbox; both cron endpoints are admin-or-secret only.
"""

# ruff: noqa: E501
from __future__ import annotations

import uuid

import pytest

from app.core.config import get_settings
from app.services import ticket_service

PW = "Passw0rd!23"
SENTINEL = "PLUM-WALRUS-7712"


async def _user(client, db, email, *, admin=False):
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "T"}
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    if admin:
        db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    tok = (await client.post("/api/v1/auth/login", json={"email": email, "password": PW})).json()[
        "access_token"
    ]
    return uid, {"Authorization": f"Bearer {tok}"}


async def _ticket(client, h, category="payments", body="help me", priority="normal"):
    r = await client.post(
        "/api/v1/support/tickets",
        json={
            "category": category,
            "subject": "Subj " + SENTINEL,
            "body": body,
            "priority": priority,
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_duplicates_are_linked_not_blocked(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "support_inbox_email", "support@t.io", raising=False)
    _uid, h = await _user(client, db, "dup@t.io")
    first = await _ticket(client, h, body="first")
    second = await _ticket(client, h, body="again")
    other_cat = await _ticket(client, h, category="kyc", body="different")
    ctx = db("SELECT ticket_no, context FROM support_tickets ORDER BY created_at")
    assert ctx[0][1].get("possible_duplicate_of") is None
    assert ctx[1][1]["possible_duplicate_of"] == first["ticket_no"]
    assert ctx[2][1].get("possible_duplicate_of") is None
    mail = db("SELECT body FROM email_outbox WHERE subject LIKE :s", s=f"[{second['ticket_no']}]%")[
        0
    ][0]
    assert f"POSSIBLE DUPLICATE of {first['ticket_no']}" in mail
    assert second["id"] != first["id"] and other_cat["id"]
    # a visitor is matched by contact email
    for _ in range(2):
        r = await client.post(
            "/api/v1/support/tickets",
            json={"category": "other", "subject": "v", "body": "b", "contact_email": "vis@t.io"},
        )
        assert r.status_code == 201
    vis = db(
        "SELECT context FROM support_tickets WHERE contact_email='vis@t.io' ORDER BY created_at"
    )
    assert vis[0][0].get("possible_duplicate_of") is None and vis[1][0].get("possible_duplicate_of")


@pytest.mark.asyncio
async def test_sla_escalation_once_with_notifications_and_audit(client, db, asession, monkeypatch):
    monkeypatch.setattr(get_settings(), "support_inbox_email", "support@t.io", raising=False)
    admin, _ = await _user(client, db, "adm@t.io", admin=True)
    uid, h = await _user(client, db, "sla@t.io")
    old_normal = await _ticket(client, h, category="payments", body="old normal")
    old_high = await _ticket(client, h, category="kyc", body="old high", priority="high")
    fresh = await _ticket(client, h, category="account", body="fresh")
    answered = await _ticket(client, h, category="listing", body="answered")
    noted = await _ticket(client, h, category="other", body="internal note only")
    db(
        "UPDATE support_tickets SET created_at=now() - interval '30 hours' WHERE id IN (:a,:b,:c,:d)",
        a=old_normal["id"],
        b=old_high["id"],
        c=answered["id"],
        d=noted["id"],
    )
    db(
        "UPDATE support_tickets SET created_at=now() - interval '6 hours' WHERE id=:i",
        i=fresh["id"],
    )
    await ticket_service.staff_reply(
        asession, actor_id=admin, ticket_id=uuid.UUID(answered["id"]), body="On it", internal=False
    )
    await ticket_service.staff_reply(
        asession, actor_id=admin, ticket_id=uuid.UUID(noted["id"]), body="note", internal=True
    )
    await asession.commit()

    out = await ticket_service.escalate_overdue(asession)
    await asession.commit()
    assert out == {"escalated": 3, "overdue": 3}
    rows = {r[0]: (r[1], r[2]) for r in db("SELECT id, priority, context FROM support_tickets")}
    assert (
        rows[uuid.UUID(old_normal["id"])][0] == "high"
        and rows[uuid.UUID(old_normal["id"])][1]["priority_before_sla"] == "normal"
    )
    assert (
        rows[uuid.UUID(old_high["id"])][0] == "high"
        and "sla_breached_at" in rows[uuid.UUID(old_high["id"])][1]
    )
    assert "sla_breached_at" in rows[uuid.UUID(noted["id"])][1]  # an internal note is not a reply
    assert "sla_breached_at" not in rows[uuid.UUID(fresh["id"])][1]
    assert "sla_breached_at" not in rows[uuid.UUID(answered["id"])][1]
    assert db("SELECT count(*) FROM audit_log WHERE action='ticket.sla_breached'")[0][0] == 3
    assert (
        db("SELECT count(*) FROM notifications WHERE user_id=:a AND type='ticket_sla'", a=admin)[0][
            0
        ]
        == 1
    )
    mail = db("SELECT subject, body FROM email_outbox WHERE subject LIKE '[SLA]%'")
    assert len(mail) == 1 and "3 ticket(s)" in mail[0][0] and old_normal["ticket_no"] in mail[0][1]
    assert SENTINEL not in mail[0][1]  # subjects are user-authored; the SLA mail lists numbers only
    # idempotent
    assert await ticket_service.escalate_overdue(asession) == {"escalated": 0, "overdue": 0}
    # the SLA hours come from settings: a 1-hour normal SLA catches the fresh ticket
    db(
        "INSERT INTO platform_settings (key, value) VALUES ('support_sla_hours_normal','1') ON CONFLICT (key) DO UPDATE SET value='1'"
    )
    out = await ticket_service.escalate_overdue(asession)
    await asession.commit()
    assert out["escalated"] == 1
    assert db("SELECT context->>'sla_breached_at' FROM support_tickets WHERE id=:i", i=fresh["id"])[
        0
    ][0]


@pytest.mark.asyncio
async def test_csat_only_by_owner_once_resolved(client, db, asession):
    admin, _ = await _user(client, db, "adm2@t.io", admin=True)
    _uid, h = await _user(client, db, "csat@t.io")
    _other, oh = await _user(client, db, "other@t.io")
    t = await _ticket(client, h)
    r = await client.post(f"/api/v1/support/tickets/{t['id']}/csat", json={"score": 5}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "TICKET_NOT_RESOLVED"
    await ticket_service.set_status(
        asession, actor_id=admin, ticket_id=uuid.UUID(t["id"]), status="resolved"
    )
    await asession.commit()
    assert (
        await client.post(f"/api/v1/support/tickets/{t['id']}/csat", json={"score": 4}, headers=oh)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/support/tickets/{t['id']}/csat", json={"score": 7}, headers=h)
    ).status_code == 422
    r = await client.post(f"/api/v1/support/tickets/{t['id']}/csat", json={"score": 4}, headers=h)
    assert r.status_code == 200 and r.json()["csat"] == 4
    assert db("SELECT csat FROM support_tickets WHERE id=:i", i=t["id"])[0][0] == 4


@pytest.mark.asyncio
async def test_daily_digest_counts_only_and_cron_endpoints(client, db, asession, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "support_inbox_email", "support@t.io", raising=False)
    monkeypatch.setattr(s, "cron_secret", "cr0n", raising=False)
    admin, _ = await _user(client, db, "adm3@t.io", admin=True)
    _uid, h = await _user(client, db, "dig@t.io")
    await _ticket(client, h, category="payments", body="body " + SENTINEL)
    b = await _ticket(client, h, category="kyc", body="b")
    await ticket_service.set_status(
        asession, actor_id=admin, ticket_id=uuid.UUID(b["id"]), status="resolved"
    )
    await ticket_service.rate_ticket(asession, user_id=_uid, ticket_id=uuid.UUID(b["id"]), score=5)
    await asession.commit()
    db(
        "INSERT INTO support_tickets (kind, user_id, category, priority, status, subject, source) VALUES ('knowledge_gap', :u, 'kyc', 'normal', 'open', 'gap', 'assistant')",
        u=_uid,
    )

    d = await ticket_service.daily_digest(asession)
    assert d["tickets_new_24h"] == 2 and d["tickets_resolved_24h"] == 1 and d["tickets_open"] == 1
    assert d["open_by_category"] == {"payments": 1} and d["knowledge_gaps_open"] == 1
    assert d["csat_avg_24h"] == 5.0 and d["sla_overdue_now"] == 0
    text = ticket_service.render_digest(d)
    assert SENTINEL not in text and "1 open" in text and "CSAT (24h): 5.0" in text

    assert (await client.post("/api/v1/assistant/maintenance/daily-digest")).status_code == 401
    assert (
        await client.post(
            "/api/v1/assistant/maintenance/ticket-sla", headers={"X-Cron-Secret": "nope"}
        )
    ).status_code in (401, 403)
    r = await client.post(
        "/api/v1/assistant/maintenance/daily-digest", headers={"X-Cron-Secret": "cr0n"}
    )
    assert r.status_code == 200 and r.json()["tickets_open"] == 1
    mail = db("SELECT subject, body FROM email_outbox WHERE subject LIKE '[Digest]%'")
    assert len(mail) == 1 and SENTINEL not in mail[0][1] and "1 open tickets" in mail[0][0]
    r = await client.post(
        "/api/v1/assistant/maintenance/ticket-sla", headers={"X-Cron-Secret": "cr0n"}
    )
    assert r.status_code == 200 and r.json() == {"escalated": 0, "overdue": 0}
