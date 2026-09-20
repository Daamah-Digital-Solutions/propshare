"""Proactive nudges (Batch B, client doc §22): each kind fires only when its state has
lasted long enough, never repeats inside its cooldown, stops when the state is resolved,
goes through the normal notification feed (+ email outbox where the kind says so), and the
sweep is idempotent so an hourly cron is safe. The cron endpoint is admin-or-secret only."""

# ruff: noqa: E501
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services import nudge_service

PW = "Passw0rd!23"


async def _user(client, db, email, *, verified_email=True, kyc="pending", days_old=10):
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "N"}
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db(
        "UPDATE users SET email_verified=:v, created_at=now() - make_interval(days => :d) WHERE id=:i",
        v=verified_email,
        d=days_old,
        i=uid,
    )
    db("UPDATE kyc_verifications SET status=:s WHERE user_id=:i", s=kyc, i=uid)
    db("DELETE FROM notifications WHERE user_id=:i", i=uid)  # registration notices are not nudges
    return uid


def _nudges(db, uid, kind):
    return db(
        "SELECT count(*) FROM notifications WHERE user_id=:u AND type=:t", u=uid, t=f"nudge:{kind}"
    )[0][0]


@pytest.mark.asyncio
async def test_each_kind_fires_once_respects_cooldown_and_stops_when_resolved(client, db, asession):
    unverified = await _user(client, db, "unv@n.io", verified_email=False, days_old=4)
    fresh = await _user(client, db, "fresh@n.io", verified_email=False, days_old=0)  # too new
    no_kyc = await _user(client, db, "nokyc@n.io", days_old=5)
    in_review = await _user(client, db, "review@n.io", days_old=20)
    db(
        "UPDATE kyc_verifications SET submitted_at=now() - interval '6 days' WHERE user_id=:u",
        u=in_review,
    )
    idle = await _user(client, db, "idle@n.io", kyc="verified", days_old=30)
    db(
        "UPDATE wallets SET balance=1500, updated_at=now() - interval '8 days' WHERE user_id=:u",
        u=idle,
    )
    waiting = await _user(client, db, "wait@n.io", kyc="verified", days_old=30)
    db(
        "INSERT INTO support_tickets (kind, user_id, category, priority, status, subject, source, updated_at) VALUES ('support', :u, 'payments', 'normal', 'waiting_user', 'x', 'form', now() - interval '4 days')",
        u=waiting,
    )

    first = await nudge_service.run_all(asession)
    await asession.commit()
    assert first == {
        "email_unverified": 1,
        "kyc_not_started": 1,
        "kyc_in_review": 1,
        "funded_not_invested": 1,
        "ticket_waiting_user": 1,
    }
    assert (
        _nudges(db, unverified, "email_unverified") == 1
        and _nudges(db, fresh, "email_unverified") == 0
    )
    assert (
        _nudges(db, no_kyc, "kyc_not_started") == 1 and _nudges(db, in_review, "kyc_in_review") == 1
    )
    assert (
        _nudges(db, idle, "funded_not_invested") == 1
        and _nudges(db, waiting, "ticket_waiting_user") == 1
    )
    # the in-review nudge is in-app only; the others queue an email in the outbox
    mails = db(
        "SELECT to_email, subject FROM email_outbox WHERE status='pending' ORDER BY to_email"
    )
    assert [m[0] for m in mails] == ["idle@n.io", "nokyc@n.io", "unv@n.io", "wait@n.io"]
    assert "Confirm your email" in [m[1] for m in mails if m[0] == "unv@n.io"][0]

    # a second sweep inside the cooldown sends nothing
    second = await nudge_service.run_all(asession)
    await asession.commit()
    assert sum(second.values()) == 0

    # after the cooldown the state that persists fires again; a resolved state does not
    db("UPDATE notifications SET created_at=now() - interval '10 days' WHERE type LIKE 'nudge:%'")
    db("UPDATE users SET email_verified=true WHERE id=:u", u=unverified)  # resolved
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:u", u=in_review)  # resolved
    db(
        "INSERT INTO investments (user_id, property_id, units, amount, status) SELECT :u, id, 1, 100, 'confirmed' FROM properties LIMIT 1",
        u=idle,
    ) if db("SELECT count(*) FROM properties")[0][0] else None
    third = await nudge_service.run_all(asession)
    await asession.commit()
    assert third["email_unverified"] == 0 and third["kyc_in_review"] == 0
    # no_kyc again (cooldown over) + the newly verified user who has not started KYC
    assert third["kyc_not_started"] == 2 and third["ticket_waiting_user"] == 1
    # the unverified user, now verified but without KYC, moves to the next nudge kind
    assert _nudges(db, unverified, "kyc_not_started") == 1
    last = await nudge_service.last_nudges(asession, no_kyc)
    assert set(last) == {"kyc_not_started"}


@pytest.mark.asyncio
async def test_cron_endpoint_is_admin_or_secret_only(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "cron_secret", "cr0n", raising=False)
    await _user(client, db, "u1@n.io", verified_email=False, days_old=3)
    assert (await client.post("/api/v1/assistant/maintenance/nudges")).status_code == 401
    assert (
        await client.post("/api/v1/assistant/maintenance/nudges", headers={"X-Cron-Secret": "nope"})
    ).status_code in (401, 403)
    r = await client.post("/api/v1/assistant/maintenance/nudges", headers={"X-Cron-Secret": "cr0n"})
    assert r.status_code == 200 and r.json()["email_unverified"] == 1
    r = await client.post("/api/v1/assistant/maintenance/nudges", headers={"X-Cron-Secret": "cr0n"})
    assert r.status_code == 200 and sum(r.json().values()) == 0
