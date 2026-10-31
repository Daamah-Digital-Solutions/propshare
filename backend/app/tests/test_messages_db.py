"""Messages from the platform team to users (client, 2026-10-28, as on Capimax BRX).

What each test protects:
  * a group message reaches exactly the open accounts holding that role (a user with two
    roles once; closed accounts and other roles never); each gets it in the inbox, as a
    notification and by email; whoever turned "Announcements" off is not emailed but still
    gets it in the inbox; the email links to the message;
  * a message to one user is always emailed, even with announcements off;
  * "Also email it" off: inbox and notification only;
  * the same form sent twice (refresh, double click) sends once;
  * bad input is refused with a message, nothing sent;
  * the inbox: the member's own messages only, unread count, opening marks read, read-all;
  * the admin panel: compose -> review (count, sample, the email) -> send -> the record per
    recipient (read, email sent / waiting / failed / opted out); templates; full admins only;
  * the settings switch round-trips through the preferences API.
"""

from __future__ import annotations

import re
import uuid

import pytest

from app.services import email_service, message_service

PW = "Passw0rd!23"


async def _member(client, db, email: str, *roles: str, name: str = "Member") -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": name}
    )
    uid = str(db("SELECT id FROM users WHERE lower(email)=lower(:e)", e=email)[0][0])
    for role in roles:
        db(
            "INSERT INTO user_roles (user_id, role) VALUES (:i, CAST(:r AS app_role)) "
            "ON CONFLICT DO NOTHING",
            i=uid,
            r=role,
        )
    return r.json()["access_token"], uid


async def _admin(client, db, email: str = "msg-admin@x.com") -> str:
    _tok, uid = await _member(client, db, email, "admin", name="Desk")
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    r = await client.post("/admin/login", data={"username": email, "password": PW})
    assert r.status_code in (200, 302, 303)
    return uid


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


async def _send(asession, audience, subject="Platform update", body="Hello\nSecond line", **kw):
    draft = await message_service.check(
        asession,
        audience=audience,
        user_email=kw.pop("user_email", None),
        subject=subject,
        body=body,
    )
    out = await message_service.send(
        asession,
        draft,
        send_email=kw.pop("send_email", True),
        client_token=kw.pop("token", uuid.uuid4().hex),
        actor_id=None,
    )
    await asession.commit()
    return out


@pytest.mark.asyncio
async def test_a_group_message_reaches_that_role_once_each(client, db, asession):
    _a, a = await _member(client, db, "brk-a@x.com", "broker")
    _b, b = await _member(client, db, "brk-b@x.com", "broker", "owner")  # two roles, once
    _c, c = await _member(client, db, "brk-closed@x.com", "broker")
    db("UPDATE users SET closed_at=now() WHERE id=:i", i=c)  # closed: nothing
    _d, d = await _member(client, db, "owner-only@x.com", "owner")  # other role: nothing
    db(
        "INSERT INTO notification_preferences (user_id, email_announcements) VALUES (:i, false)",
        i=b,
    )

    broadcast, fresh = await _send(asession, "brokers")
    assert fresh and broadcast.recipients == 2 and broadcast.emails_queued == 1

    inbox = db(
        "SELECT u.email, m.email_status FROM platform_messages m JOIN users u "
        "ON u.id=m.recipient_id ORDER BY u.email"
    )
    assert [tuple(r) for r in inbox] == [("brk-a@x.com", "queued"), ("brk-b@x.com", "opted_out")]
    told = db("SELECT user_id::text, type, title FROM notifications WHERE type='message'")
    assert sorted(r[0] for r in told) == sorted([a, b]) and told[0][2] == "Platform update"
    mails = db("SELECT to_email, subject, body, category FROM email_outbox")
    assert len(mails) == 1
    to, subject, body, category = mails[0]
    mid = db("SELECT id FROM platform_messages WHERE recipient_id=:i", i=a)[0][0]
    assert (to, subject, category) == ("brk-a@x.com", "Platform update", "announcements")
    assert body.startswith("Hello\nSecond line\n") and f"/messages?id={mid}" in body
    assert 'turn off "Announcements" in Settings' in body
    assert not db("SELECT 1 FROM platform_messages WHERE recipient_id IN (:c, :d)", c=c, d=d)
    audit = db("SELECT action, after->>'recipients' FROM audit_log WHERE action='message.sent'")
    assert [tuple(r) for r in audit] == [("message.sent", "2")]


@pytest.mark.asyncio
async def test_everyone_and_investors(client, db, asession):
    await _member(client, db, "inv@x.com", "investor")
    await _member(client, db, "lp@x.com", "liquidity_provider")
    everyone = db("SELECT count(*) FROM users WHERE closed_at IS NULL")[0][0]
    investors = db(
        "SELECT count(DISTINCT user_id) FROM user_roles ur JOIN users u ON u.id=ur.user_id "
        "WHERE role='investor' AND u.closed_at IS NULL"
    )[0][0]
    b1, _ = await _send(asession, "everyone")
    b2, _ = await _send(asession, "investors")
    b3, _ = await _send(asession, "liquidity_providers")
    assert (b1.recipients, b2.recipients, b3.recipients) == (everyone, investors, 1)


@pytest.mark.asyncio
async def test_a_message_to_one_user_is_always_emailed(client, db, asession):
    _t, uid = await _member(client, db, "Direct@X.com", "investor")
    db(
        "INSERT INTO notification_preferences (user_id, email_announcements) VALUES (:i, false)",
        i=uid,
    )
    b, _ = await _send(asession, "user", user_email="  direct@x.com ")
    assert b.recipients == 1 and b.user_id == uuid.UUID(uid)
    to, body, category = db("SELECT to_email, body, category FROM email_outbox")[0]
    assert (to, category) == ("Direct@x.com", "message")  # found whatever the case typed
    assert "Announcements" not in body  # no opt-out line on a direct message


@pytest.mark.asyncio
async def test_without_email_it_is_inbox_and_notification_only(client, db, asession):
    await _member(client, db, "quiet@x.com", "investor")
    b, _ = await _send(asession, "user", user_email="quiet@x.com", send_email=False)
    assert b.emails_queued == 0 and not db("SELECT 1 FROM email_outbox")
    assert db("SELECT email_status FROM platform_messages")[0][0] == "no_email"
    assert db("SELECT count(*) FROM notifications WHERE type='message'")[0][0] == 1


@pytest.mark.asyncio
async def test_the_same_form_sent_twice_sends_once(client, db, asession):
    await _member(client, db, "twice@x.com", "investor")
    first, fresh = await _send(asession, "user", user_email="twice@x.com", token="t" * 30)
    again, fresh2 = await _send(asession, "user", user_email="twice@x.com", token="t" * 30)
    assert fresh and not fresh2 and again.id == first.id
    assert db("SELECT count(*) FROM platform_messages")[0][0] == 1
    assert db("SELECT count(*) FROM email_outbox")[0][0] == 1


@pytest.mark.asyncio
async def test_bad_input_is_refused(client, db, asession):
    _t, uid = await _member(client, db, "gone@x.com", "investor")
    db("UPDATE users SET closed_at=now() WHERE id=:i", i=uid)
    cases = [
        (dict(audience="partners"), "INVALID_AUDIENCE"),
        (dict(audience="everyone", subject="Hi"), "SUBJECT_REQUIRED"),
        (dict(audience="everyone", subject="x" * 201), "SUBJECT_TOO_LONG"),
        (dict(audience="everyone", body=" \n "), "BODY_REQUIRED"),
        (dict(audience="everyone", body="x" * 10_001), "BODY_TOO_LONG"),
        (dict(audience="user", user_email="nobody@x.com"), "USER_NOT_FOUND"),
        (dict(audience="user", user_email="gone@x.com"), "ACCOUNT_CLOSED"),
    ]
    for kw, code in cases:
        args = {"subject": "Valid subject", "body": "Body", "user_email": None} | kw
        with pytest.raises(Exception) as exc:
            await message_service.check(asession, **args)
        assert getattr(exc.value, "code", "") == code, kw
    draft = await message_service.check(
        asession, audience="everyone", user_email=None, subject="  A   b  c ", body="\x00ok\r\n"
    )
    assert (draft.subject, draft.body) == ("A b c", "ok")
    with pytest.raises(Exception) as exc:
        await message_service.send(
            asession, draft, send_email=True, client_token="x", actor_id=None
        )
    assert exc.value.code == "BAD_TOKEN"


@pytest.mark.asyncio
async def test_the_inbox_is_the_members_own(client, db, asession):
    tok, uid = await _member(client, db, "reader@x.com", "investor")
    other, _ = await _member(client, db, "other@x.com", "investor")
    await _send(asession, "user", user_email="reader@x.com", subject="First one")
    await _send(asession, "user", user_email="reader@x.com", subject="Second one", body="B" * 300)

    box = (await client.get("/api/v1/messages", headers=_h(tok))).json()
    assert box["unread"] == 2 and [i["subject"] for i in box["items"]] == [
        "Second one",
        "First one",
    ]
    assert len(box["items"][0]["preview"]) == 160 and box["items"][0]["body"] is None
    mid = box["items"][1]["id"]
    assert (await client.get(f"/api/v1/messages/{mid}", headers=_h(other))).status_code == 404
    assert (await client.get("/api/v1/messages/not-a-uuid", headers=_h(tok))).status_code == 404
    one = (await client.get(f"/api/v1/messages/{mid}", headers=_h(tok))).json()
    assert one["read"] and one["body"] == "Hello\nSecond line"
    assert (await client.get("/api/v1/messages", headers=_h(tok))).json()["unread"] == 1
    assert (await client.get("/api/v1/messages", headers=_h(other))).json() == {
        "items": [],
        "unread": 0,
    }
    marked = await client.post("/api/v1/messages/read-all", headers=_h(tok))
    assert marked.json() == {"marked": 1}
    assert (await client.get("/api/v1/messages", headers=_h(tok))).json()["unread"] == 0
    assert (await client.get("/api/v1/messages")).status_code == 401


@pytest.mark.asyncio
async def test_the_admin_composes_reviews_sends_and_sees_each_recipient(client, db):
    await _member(client, db, "lp-1@x.com", "liquidity_provider", name="Lina")
    _t, opted = await _member(client, db, "lp-2@x.com", "liquidity_provider")
    db(
        "INSERT INTO notification_preferences (user_id, email_announcements) VALUES (:i, false)",
        i=opted,
    )
    assert (await client.get("/admin/messages", follow_redirects=False)).status_code in (302, 303)
    await _admin(client, db)

    page = await client.get("/admin/messages/new")
    assert page.status_code == 200 and "Review before sending" in page.text
    token = re.search(r'name="token" value="([^"]+)"', page.text).group(1)
    form = {
        "token": token,
        "template_id": "",
        "audience": "liquidity_providers",
        "user_email": "",
        "subject": "Pool <update>",
        "body": "New tiers open <b>Monday</b>.",
        "send_email": "1",
    }
    review = await client.post("/admin/messages/new", data=form | {"action": "review"})
    assert review.status_code == 200, review.text
    assert "Send to 2 people" in review.text and "lp-1@x.com" in review.text
    assert "turned announcement emails off" in review.text
    assert "&lt;b&gt;Monday&lt;/b&gt;" in review.text and "<b>Monday</b>" not in review.text
    assert not db("SELECT 1 FROM message_broadcasts")  # reviewing sends nothing

    bad = await client.post("/admin/messages/new", data=form | {"subject": "", "action": "review"})
    assert bad.status_code == 400 and "Write a subject" in bad.text

    sent = await client.post(
        "/admin/messages/new", data=form | {"action": "send"}, follow_redirects=False
    )
    assert sent.status_code == 303
    url = sent.headers["location"]
    assert url.endswith("?sent=1")
    again = await client.post(
        "/admin/messages/new", data=form | {"action": "send"}, follow_redirects=False
    )
    assert again.headers["location"].endswith("?again=1")
    assert db("SELECT count(*) FROM message_broadcasts")[0][0] == 1

    # the drainer sends the waiting email (console provider here); the record says so
    await _drain()
    detail = await client.get(url)
    assert detail.status_code == 200
    assert "Sent to 2 people." in detail.text and "Pool &lt;update&gt;" in detail.text
    assert "Email sent" in detail.text and "Not emailed (opted out)" in detail.text
    only_out = await client.get(url.split("?")[0], params={"status": "opted_out"})
    assert "lp-2@x.com" in only_out.text and "lp-1@x.com" not in only_out.text
    listing = await client.get("/admin/messages")
    assert "All liquidity providers" in listing.text and "Pool &lt;update&gt;" in listing.text
    db("UPDATE email_outbox SET status='failed', last_error='Mailbox unavailable'")
    failed = await client.get(url.split("?")[0], params={"status": "failed"})
    assert "lp-1@x.com" in failed.text and "Mailbox unavailable" in failed.text
    assert "Email failed" in failed.text


async def _drain():
    from app.core.db import session_scope

    async with session_scope() as session:
        await email_service.dispatch_pending(session)


@pytest.mark.asyncio
async def test_templates_fill_the_composer(client, db):
    await _admin(client, db)
    saved = await client.post(
        "/admin/messages/templates",
        data={"action": "save", "name": "Monthly", "subject": "This month", "body": "Dear all"},
    )
    assert saved.status_code == 200 and "saved" in saved.text
    dup = await client.post(
        "/admin/messages/templates",
        data={"action": "save", "name": "monthly", "subject": "Again", "body": "x"},
    )
    assert dup.status_code == 400 and "already has that name" in dup.text
    tid = db("SELECT id FROM message_templates")[0][0]
    page = await client.get("/admin/messages/new", params={"template": str(tid)})
    assert 'value="This month"' in page.text and ">Dear all</textarea>" in page.text
    gone = await client.post("/admin/messages/templates", data={"action": "delete", "id": str(tid)})
    assert "Template deleted." in gone.text and not db("SELECT 1 FROM message_templates")


@pytest.mark.asyncio
async def test_the_announcements_switch_round_trips(client, db):
    tok, _uid = await _member(client, db, "prefs@x.com", "investor")
    got = (await client.get("/api/v1/notifications/preferences", headers=_h(tok))).json()
    assert got["email_announcements"] is True
    put = await client.put(
        "/api/v1/notifications/preferences",
        json={"email_announcements": False},
        headers=_h(tok),
    )
    assert put.json()["email_announcements"] is False


@pytest.mark.asyncio
async def test_staff_are_an_audience_too(client, db, asession):
    await _member(client, db, "ed@x.com", "content_editor")
    await _member(client, db, "adm@x.com", "admin")
    await _member(client, db, "plain@x.com", "investor")
    b, _ = await _send(asession, "staff")
    emails = db(
        "SELECT u.email FROM platform_messages m JOIN users u ON u.id=m.recipient_id "
        "WHERE m.broadcast_id=:b ORDER BY u.email",
        b=b.id,
    )
    assert [r[0] for r in emails] == ["adm@x.com", "ed@x.com"]
