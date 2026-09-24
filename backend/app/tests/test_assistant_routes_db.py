"""Assistant HTTP surface + confirmed actions + tickets + consent + maintenance (plan §4/§9).

What each test protects:
  * the gate reports/raises the FIRST failing reason in the documented order (deploy switch,
    DB switch, model, rollout, consent, daily cap) and visitors need visitor mode + a key;
  * consent is per policy version, audited, and a version bump re-requires it;
  * the SSE stream round-trips through the real route with the scripted FakeLLM, the
    transcript is readable only by its owner, and feedback attaches to assistant messages;
  * a proposed action executes exactly once, only for its owner, with audit + system note;
    the three executors do what they say (email token + verification cap, notifications,
    structured ticket) and a failing executor is recorded, not hidden;
  * a ticket handed off from a conversation carries NO chat text (sentinel test) — not in
    the ticket, not in its context, not in the support email — but does carry the audited
    transcript link; the LLM-free form works for members and visitors; internal notes stay
    internal; other users get 404;
  * retention purge deletes old conversations only; key rotation re-encrypts every row with
    the active key and old rows stay readable.
"""

# ruff: noqa: E501
from __future__ import annotations

import base64
import json
import os
import uuid

import pytest

from app.api.routes import assistant as assistant_routes
from app.core import crypto
from app.core.config import get_settings
from app.services.assistant import actions, agent, guard
from app.services.assistant.context import load_context
from app.services.llm.fake import FakeLLM, FakeToolCall, FakeTurn

PW = "Passw0rd!23"
SENTINEL = "ZEBRA-PAPAYA-9931"  # a phrase that only ever appears in chat text
VKEY = "visitor-key-0123456789abcdef"


def _write_keys(tmp_path, *ids) -> str:
    p = tmp_path / f"assistant-{'-'.join(ids)}.keys"
    p.write_text(
        "\n".join(f"{k}:{base64.b64encode(os.urandom(32)).decode()}" for k in ids),
        encoding="utf-8",
    )
    return str(p)


@pytest.fixture
def configured(monkeypatch, tmp_path):
    """Deploy-level configuration present (key file, HMAC, provider key, switch on)."""
    s = get_settings()
    monkeypatch.setattr(
        s, "assistant_encryption_keys_file", _write_keys(tmp_path, "k1"), raising=False
    )
    monkeypatch.setattr(s, "assistant_encryption_active_key", "k1", raising=False)
    monkeypatch.setattr(s, "assistant_hmac_secret", "test-hmac", raising=False)
    monkeypatch.setattr(s, "openai_api_key", "sk-test", raising=False)
    monkeypatch.setattr(s, "assistant_enabled", True, raising=False)
    monkeypatch.setattr(s, "support_inbox_email", "support@test.io", raising=False)
    crypto.reset_cache()
    yield s
    crypto.reset_cache()


def _setting(db, key, value):
    db(
        "INSERT INTO platform_settings (key, value) VALUES (:k,:v) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
        k=key,
        v=value,
    )


def _enable(db, *, rollout="all", model="fake-model", visitors=False, cap="200"):
    _setting(db, "assistant_enabled", "true")
    _setting(db, "assistant_model", model)
    _setting(db, "assistant_rollout", rollout)
    _setting(db, "assistant_visitor_enabled", "true" if visitors else "false")
    _setting(db, "assistant_daily_message_cap", cap)


async def _user(client, db, email, *, admin=False, verified_email=False) -> tuple[str, uuid.UUID]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Route Tester"}
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    if admin:
        db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    if verified_email:
        db("UPDATE users SET email_verified=true WHERE id=:i", i=uid)
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    tok = (await client.post("/api/v1/auth/login", json={"email": email, "password": PW})).json()[
        "access_token"
    ]
    return tok, uid


def _h(tok) -> dict:
    return {"Authorization": f"Bearer {tok}"}


async def _consent(client, tok):
    r = await client.post(
        "/api/v1/assistant/consent",
        json={"policy_version": get_settings().assistant_policy_version},
        headers=_h(tok),
    )
    assert r.status_code == 200, r.text


def _fake(monkeypatch, *turns):
    llm = FakeLLM(list(turns))
    monkeypatch.setattr(assistant_routes, "llm_factory", lambda provider: llm)
    return llm


async def _send(client, cid, text, headers) -> list[dict]:
    async with client.stream(
        "POST",
        f"/api/v1/assistant/conversations/{cid}/messages",
        json={"text": text},
        headers=headers,
    ) as r:
        assert r.status_code == 200, await r.aread()
        assert r.headers["content-type"].startswith("text/event-stream")
        raw = (await r.aread()).decode()
    events = []
    for block in raw.strip().split("\n\n"):
        if block.startswith(":"):  # SSE comment (keep-alive)
            continue
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append({"event": lines["event"], "data": json.loads(lines["data"])})
    return events


# --- gate + consent ------------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_status_reports_first_failing_reason_in_order(client, db, monkeypatch, tmp_path):
    tok, _ = await _user(client, db, "gate@test.io")
    r = await client.get("/api/v1/assistant/status", headers=_h(tok))
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert r.json()["reason"] == "ASSISTANT_DISABLED" and r.json()["encryption"] == "missing"

    s = get_settings()
    monkeypatch.setattr(
        s, "assistant_encryption_keys_file", _write_keys(tmp_path, "k1"), raising=False
    )
    monkeypatch.setattr(s, "assistant_encryption_active_key", "k1", raising=False)
    monkeypatch.setattr(s, "assistant_hmac_secret", "h", raising=False)
    monkeypatch.setattr(s, "openai_api_key", "sk-test", raising=False)
    monkeypatch.setattr(s, "assistant_enabled", True, raising=False)
    crypto.reset_cache()
    assert (await client.get("/api/v1/assistant/status", headers=_h(tok))).json()[
        "reason"
    ] == "ASSISTANT_DISABLED"  # DB switch
    _setting(db, "assistant_enabled", "true")
    assert (await client.get("/api/v1/assistant/status", headers=_h(tok))).json()[
        "reason"
    ] == "ASSISTANT_NOT_CONFIGURED"
    _setting(db, "assistant_model", "fake-model")
    j = (await client.get("/api/v1/assistant/status", headers=_h(tok))).json()
    assert j["reason"] == "NOT_IN_ROLLOUT" and j["rollout"] == "admins" and j["encryption"] == "ok"
    _setting(db, "assistant_rollout", "all")
    j = (await client.get("/api/v1/assistant/status", headers=_h(tok))).json()
    assert j["reason"] == "CONSENT_REQUIRED" and j["consent_required"] is True
    # the message route raises the same reason with the policy version
    r = await client.post("/api/v1/assistant/conversations", headers=_h(tok))
    assert r.status_code == 428 and r.json()["error"]["code"] == "CONSENT_REQUIRED"
    assert r.json()["error"]["details"]["policy_version"] == s.assistant_policy_version
    # wrong version is refused, right version recorded + audited
    r = await client.post(
        "/api/v1/assistant/consent", json={"policy_version": "1999-01"}, headers=_h(tok)
    )
    assert r.status_code == 409
    await _consent(client, tok)
    assert db("SELECT count(*) FROM audit_log WHERE action='assistant.consent_recorded'")[0][0] == 1
    j = (await client.get("/api/v1/assistant/status", headers=_h(tok))).json()
    assert j["enabled"] is True and j["reason"] is None and j["consent_given"] is True
    # a policy bump re-requires consent
    monkeypatch.setattr(s, "assistant_policy_version", "2027-01", raising=False)
    assert (await client.get("/api/v1/assistant/status", headers=_h(tok))).json()[
        "reason"
    ] == "CONSENT_REQUIRED"
    crypto.reset_cache()


@pytest.mark.asyncio
async def test_visitor_mode_needs_setting_and_key(client, db, configured, monkeypatch):
    _enable(db, visitors=False)
    r = await client.get("/api/v1/assistant/status")
    assert r.json()["reason"] == "SIGN_IN_REQUIRED" and r.json()["visitor_allowed"] is False
    _enable(db, visitors=True)
    assert (await client.get("/api/v1/assistant/status")).json()["reason"] == "VISITOR_KEY_REQUIRED"
    assert (
        await client.get("/api/v1/assistant/status", headers={"X-Visitor-Key": "short"})
    ).json()["reason"] == "VISITOR_KEY_REQUIRED"
    j = (await client.get("/api/v1/assistant/status", headers={"X-Visitor-Key": VKEY})).json()
    assert j["enabled"] is True and j["consent_required"] is False
    _fake(monkeypatch, FakeTurn(text="Welcome, visitor."))
    r = await client.post("/api/v1/assistant/conversations", headers={"X-Visitor-Key": VKEY})
    assert r.status_code == 201
    cid = r.json()["id"]
    events = await _send(client, cid, "hello", {"X-Visitor-Key": VKEY})
    assert events[-1]["event"] == "done"
    # another visitor key cannot read it
    r = await client.get(
        f"/api/v1/assistant/conversations/{cid}/messages", headers={"X-Visitor-Key": VKEY + "x"}
    )
    assert r.status_code == 404
    # rollout=admins closes visitor mode regardless of the visitor switch
    _enable(db, visitors=True, rollout="admins")
    assert (await client.get("/api/v1/assistant/status", headers={"X-Visitor-Key": VKEY})).json()[
        "reason"
    ] == "SIGN_IN_REQUIRED"


# --- stream, transcript, feedback, daily cap ----------------------------------------------- #
@pytest.mark.asyncio
async def test_sse_round_trip_transcript_ownership_feedback_and_daily_cap(
    client, db, configured, monkeypatch
):
    _enable(db, cap="2")
    tok, uid = await _user(client, db, "sse@test.io")
    other, _ = await _user(client, db, "other@test.io")
    await _consent(client, tok)
    llm = _fake(
        monkeypatch,
        FakeTurn(tool_calls=[FakeToolCall("get_my_wallet", {})]),
        FakeTurn(text="Your balance is $0.00."),
        FakeTurn(text="Second answer."),
    )
    r = await client.post("/api/v1/assistant/conversations", headers=_h(tok))
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    events = await _send(client, cid, f"what's my balance? {SENTINEL}", _h(tok))
    kinds = [e["event"] for e in events]
    assert kinds[0] == "started" and kinds[-1] == "done" and "delta" in kinds and "tool" in kinds
    assert (
        "".join(e["data"]["text"] for e in events if e["event"] == "delta")
        == "Your balance is $0.00."
    )
    assert llm.calls == 2 and llm.requests[0].user_key == guard.safety_identifier(str(uid))
    done = events[-1]["data"]
    assert done["safe_mode"] is None and done["confidence"] == "normal"

    # transcript: owner sees decrypted text; other user / no auth: 404 / 401
    r = await client.get(f"/api/v1/assistant/conversations/{cid}/messages", headers=_h(tok))
    assert r.status_code == 200
    roles = [m["role"] for m in r.json()]
    assert roles == ["user", "assistant"] and SENTINEL in r.json()[0]["text"]
    assert (
        await client.get(f"/api/v1/assistant/conversations/{cid}/messages", headers=_h(other))
    ).status_code == 404
    assert (await client.get(f"/api/v1/assistant/conversations/{cid}/messages")).status_code == 404
    lst = await client.get("/api/v1/assistant/conversations", headers=_h(tok))
    assert [c["id"] for c in lst.json()] == [cid] and lst.json()[0]["message_count"] == 2
    assert (await client.get("/api/v1/assistant/conversations", headers=_h(other))).json() == []

    # feedback only on assistant messages, only by the owner
    mid = done["message_id"]
    assert (
        await client.post(
            f"/api/v1/assistant/messages/{mid}/feedback", json={"feedback": "up"}, headers=_h(other)
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/assistant/messages/{mid}/feedback", json={"feedback": "up"}, headers=_h(tok)
        )
    ).status_code == 204
    assert db("SELECT feedback FROM assistant_messages WHERE id=:i", i=mid)[0][0] == "up"

    # daily cap: cap=2 -> the second message is the last one allowed
    await _send(client, cid, "again", _h(tok))
    r = await client.post(
        f"/api/v1/assistant/conversations/{cid}/messages", json={"text": "third"}, headers=_h(tok)
    )
    assert r.status_code == 429 and r.json()["error"]["code"] == "DAILY_CAP"
    assert (await client.get("/api/v1/assistant/status", headers=_h(tok))).json()[
        "reason"
    ] == "DAILY_CAP"


@pytest.mark.asyncio
async def test_stream_reports_provider_failure_as_safe_mode_not_500(
    client, db, configured, monkeypatch
):
    _enable(db)
    tok, _ = await _user(client, db, "fail@test.io")
    await _consent(client, tok)
    _fake(monkeypatch, FakeTurn(fail=("PROVIDER_DOWN", "boom")))
    cid = (await client.post("/api/v1/assistant/conversations", headers=_h(tok))).json()["id"]
    events = await _send(client, cid, "hi", _h(tok))
    assert events[-1]["event"] == "done" and events[-1]["data"]["safe_mode"] == "PROVIDER_DOWN"
    assert any(e["event"] == "reset" for e in events)
    assert [e["data"] for e in events if e["event"] == "card"] == [
        {"kind": "link", "path": "/support", "label": "Contact support"}
    ]


# --- confirmed actions: end to end + no-leak handoff ------------------------------------- #
@pytest.mark.asyncio
async def test_ticket_handoff_carries_no_chat_text_and_executes_once(
    client, db, configured, monkeypatch
):
    _enable(db)
    tok, uid = await _user(client, db, "handoff@test.io")
    other, _ = await _user(client, db, "thief@test.io")
    await _consent(client, tok)
    _fake(
        monkeypatch,
        FakeTurn(tool_calls=[FakeToolCall("get_my_wallet", {})]),
        FakeTurn(
            text=f"I will open a ticket. {SENTINEL}",
            tool_calls=[
                FakeToolCall(
                    "propose_action",
                    {"action": "create_support_ticket", "category": "payments", "priority": "high"},
                )
            ],
        ),
        FakeTurn(text="Please confirm below."),
    )
    cid = (await client.post("/api/v1/assistant/conversations", headers=_h(tok))).json()["id"]
    events = await _send(client, cid, f"my deposit is missing {SENTINEL}", _h(tok))
    card = next(
        e["data"] for e in events if e["event"] == "card" and e["data"]["kind"] == "confirm_action"
    )
    pid, token = card["proposal_id"], card["token"]

    # wrong user, wrong token, then the real confirmation, then a replay
    r = await client.post(
        f"/api/v1/assistant/actions/{pid}/confirm", json={"token": token}, headers=_h(other)
    )
    assert r.status_code == 404
    r = await client.post(
        f"/api/v1/assistant/actions/{pid}/confirm", json={"token": "x" * 40}, headers=_h(tok)
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "BAD_TOKEN"
    r = await client.post(
        f"/api/v1/assistant/actions/{pid}/confirm", json={"token": token}, headers=_h(tok)
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "executed" and r.json()["result"]["ticket_no"].startswith("CPX-")
    r = await client.post(
        f"/api/v1/assistant/actions/{pid}/confirm", json={"token": token}, headers=_h(tok)
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "PROPOSAL_USED"
    assert db("SELECT count(*) FROM support_tickets")[0][0] == 1

    # the ticket: structured summary, transcript link, refs, tool names — and NO chat text
    t = db(
        "SELECT ticket_no, kind, category, priority, subject, summary, context::text, source, user_id, conversation_id FROM support_tickets"
    )[0]
    assert t[1] == "support" and t[2] == "payments" and t[3] == "high" and t[7] == "assistant"
    assert t[8] == uid and str(t[9]) == cid
    assert SENTINEL not in (t[4] or "") and SENTINEL not in (t[5] or "") and SENTINEL not in t[6]
    assert f"/admin/assistant-conversation/details/{cid}" in t[5]
    assert "get_my_wallet, propose_action" in t[5] and "Conversation turns: 1" in t[5]
    assert "KYC status: verified" in t[5]
    assert db("SELECT count(*) FROM support_ticket_messages")[0][0] == 0
    # the support inbox email: same summary, no chat text
    mail = db("SELECT to_email, subject, body FROM email_outbox WHERE category='support'")
    assert len(mail) == 1 and mail[0][0] == "support@test.io" and t[0] in mail[0][1]
    assert (
        SENTINEL not in mail[0][2] and f"/admin/assistant-conversation/details/{cid}" in mail[0][2]
    )
    # audit + system note + conversation linked + user notified
    assert db("SELECT count(*) FROM audit_log WHERE action='assistant.action.executed'")[0][0] == 1
    assert db("SELECT count(*) FROM audit_log WHERE action='ticket.created'")[0][0] == 1
    assert db("SELECT ticket_id FROM assistant_conversations WHERE id=:c", c=cid)[0][0] is not None
    assert (
        db("SELECT count(*) FROM notifications WHERE user_id=:u AND type='support_ticket'", u=uid)[
            0
        ][0]
        == 1
    )
    assert (
        db(
            "SELECT count(*) FROM assistant_messages WHERE conversation_id=:c AND role='system_note'",
            c=cid,
        )[0][0]
        == 1
    )
    # the owner sees the ticket through the support API; the other user does not
    tid = db("SELECT id FROM support_tickets")[0][0]
    assert (await client.get(f"/api/v1/support/tickets/{tid}", headers=_h(tok))).json()[
        "ticket_no"
    ] == t[0]
    assert (
        await client.get(f"/api/v1/support/tickets/{tid}", headers=_h(other))
    ).status_code == 404


@pytest.mark.asyncio
async def test_resend_and_notifications_executors_and_cancel(client, db, configured, asession):
    tok, uid = await _user(client, db, "exec@test.io")
    db(
        "INSERT INTO notifications (user_id, title, message) VALUES (:u,'a','b'), (:u,'c','d')",
        u=uid,
    )
    ctx = await load_context(asession, user_id=uid)
    conv = await agent.start_conversation(asession, ctx)
    ctx = type(ctx)(**{**ctx.__dict__, "conversation_id": conv.id})

    async def propose(action):
        p, token = await guard.issue_confirmation(
            asession, ctx=ctx, action=action, params={}, summary=action
        )
        await asession.commit()
        return p.id, token

    # resend: one email token exists from registration; the action adds one
    pid, token = await propose("resend_verification_email")
    p = await actions.confirm(asession, user_id=uid, proposal_id=pid, token=token)
    await asession.commit()
    assert p.status == "executed" and p.result == {"sent": True}
    assert (
        db("SELECT count(*) FROM email_tokens WHERE user_id=:u AND kind='verify'", u=uid)[0][0] == 2
    )
    # the per-hour cap (3): two more sends reach it, the fourth fails and is RECORDED
    for _ in range(1):
        pid, token = await propose("resend_verification_email")
        await actions.confirm(asession, user_id=uid, proposal_id=pid, token=token)
    pid, token = await propose("resend_verification_email")
    p = await actions.confirm(asession, user_id=uid, proposal_id=pid, token=token)
    await asession.commit()
    assert p.status == "failed" and p.result["error"] == "TOO_MANY_REQUESTS"
    assert db("SELECT count(*) FROM audit_log WHERE action='assistant.action.failed'")[0][0] == 1
    notes = db(
        "SELECT text_enc FROM assistant_messages WHERE conversation_id=:c AND role='system_note'",
        c=conv.id,
    )
    assert len(notes) == 3 and all(bytes(n[0]).startswith(b"k1:") for n in notes)
    # already verified -> recorded failure too
    db("UPDATE users SET email_verified=true WHERE id=:i", i=uid)
    pid, token = await propose("resend_verification_email")
    p = await actions.confirm(asession, user_id=uid, proposal_id=pid, token=token)
    assert p.status == "failed" and p.result["error"] == "ALREADY_VERIFIED"

    # notifications
    pid, token = await propose("mark_all_notifications_read")
    p = await actions.confirm(asession, user_id=uid, proposal_id=pid, token=token)
    await asession.commit()
    assert p.status == "executed" and p.result == {"marked": 2}
    assert (
        db("SELECT count(*) FROM notifications WHERE user_id=:u AND read=false", u=uid)[0][0] == 0
    )

    # cancel: one-shot, owner-only, leaves a note
    pid, token = await propose("mark_all_notifications_read")
    await asession.commit()
    r = await client.post(f"/api/v1/assistant/actions/{pid}/cancel", headers=_h(tok))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert (
        await client.post(f"/api/v1/assistant/actions/{pid}/cancel", headers=_h(tok))
    ).status_code == 409
    assert (
        await client.post(
            f"/api/v1/assistant/actions/{pid}/confirm", json={"token": token}, headers=_h(tok)
        )
    ).status_code == 409

    # the resend route itself (rate limited, signed-in)
    r = await client.post("/api/v1/auth/resend-verification", headers=_h(tok))
    assert r.status_code == 409  # verified above


@pytest.mark.asyncio
async def test_resend_verification_route_for_unverified_user(client, db):
    tok, uid = await _user(client, db, "unverified@test.io")
    assert (
        await client.post("/api/v1/auth/resend-verification", headers=_h(tok))
    ).status_code == 204
    assert (
        db("SELECT count(*) FROM email_tokens WHERE user_id=:u AND kind='verify'", u=uid)[0][0] == 2
    )
    assert (await client.post("/api/v1/auth/resend-verification")).status_code == 401


# --- support form + thread ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_support_form_member_visitor_thread_and_internal_notes(
    client, db, configured, asession
):
    tok, uid = await _user(client, db, "form@test.io")
    other, _ = await _user(client, db, "form2@test.io")
    # visitor without email -> 422; with email -> created (no user), email queued
    r = await client.post(
        "/api/v1/support/tickets", json={"category": "kyc", "subject": "Help", "body": "I am stuck"}
    )
    assert r.status_code == 422
    r = await client.post(
        "/api/v1/support/tickets",
        json={
            "category": "kyc",
            "subject": "Help",
            "body": "I am stuck",
            "contact_email": "v@x.io",
        },
    )
    assert (
        r.status_code == 201
        and r.json()["source"] == "form"
        and r.json()["messages"][0]["body"] == "I am stuck"
    )
    assert db("SELECT user_id, contact_email FROM support_tickets WHERE id=:i", i=r.json()["id"])[
        0
    ] == (None, "v@x.io")
    # member
    r = await client.post(
        "/api/v1/support/tickets",
        json={"category": "bogus", "subject": "x", "body": "y"},
        headers=_h(tok),
    )
    assert r.status_code == 422
    r = await client.post(
        "/api/v1/support/tickets",
        json={
            "category": "withdrawals",
            "subject": "Where is my money",
            "body": "Requested 3 days ago",
        },
        headers=_h(tok),
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert db("SELECT count(*) FROM email_outbox WHERE category='support'")[0][0] == 2
    # staff reply + internal note; the owner sees the reply, not the note; gets a notification
    from app.services import ticket_service

    _, staff = await _user(client, db, "staff@test.io", admin=True)
    await ticket_service.staff_reply(
        asession, actor_id=staff, ticket_id=uuid.UUID(tid), body="Looking into it", internal=False
    )
    await ticket_service.staff_reply(
        asession,
        actor_id=staff,
        ticket_id=uuid.UUID(tid),
        body="INTERNAL: check bank ref",
        internal=True,
    )
    await asession.commit()
    r = await client.get(f"/api/v1/support/tickets/{tid}", headers=_h(tok))
    bodies = [m["body"] for m in r.json()["messages"]]
    assert (
        bodies == ["Requested 3 days ago", "Looking into it"]
        and r.json()["status"] == "waiting_user"
    )
    assert (
        db("SELECT count(*) FROM notifications WHERE user_id=:u AND type='support_ticket'", u=uid)[
            0
        ][0]
        == 1
    )
    # owner reply reopens; other user 404; list shows only mine
    r = await client.post(
        f"/api/v1/support/tickets/{tid}/messages", json={"body": "Still waiting"}, headers=_h(tok)
    )
    assert r.status_code == 200 and r.json()["status"] == "open" and len(r.json()["messages"]) == 3
    assert (
        await client.post(
            f"/api/v1/support/tickets/{tid}/messages", json={"body": "hi"}, headers=_h(other)
        )
    ).status_code == 404
    assert [
        t["id"] for t in (await client.get("/api/v1/support/tickets", headers=_h(tok))).json()
    ] == [tid]
    assert (await client.get("/api/v1/support/tickets", headers=_h(other))).json() == []
    # closing stops replies
    await ticket_service.set_status(
        asession, actor_id=staff, ticket_id=uuid.UUID(tid), status="closed"
    )
    await asession.commit()
    r = await client.post(
        f"/api/v1/support/tickets/{tid}/messages", json={"body": "more"}, headers=_h(tok)
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "TICKET_CLOSED"


# --- maintenance ----------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_purge_and_reencrypt_via_cron_endpoints(
    client, db, configured, monkeypatch, tmp_path, asession
):
    _enable(db)
    monkeypatch.setattr(get_settings(), "cron_secret", "cr0n", raising=False)
    _setting(db, "assistant_retention_days", "30")
    tok, uid = await _user(client, db, "purge@test.io")
    await _consent(client, tok)
    _fake(monkeypatch, FakeTurn(text="old"), FakeTurn(text="new"))
    old = (await client.post("/api/v1/assistant/conversations", headers=_h(tok))).json()["id"]
    await _send(client, old, "first", _h(tok))
    new = (await client.post("/api/v1/assistant/conversations", headers=_h(tok))).json()["id"]
    await _send(client, new, "second", _h(tok))
    db(
        "UPDATE assistant_conversations SET last_message_at=now() - interval '31 days' WHERE id=:c",
        c=old,
    )

    assert (
        await client.post("/api/v1/assistant/maintenance/purge", headers={"X-Cron-Secret": "nope"})
    ).status_code in (401, 403)
    r = await client.post("/api/v1/assistant/maintenance/purge", headers={"X-Cron-Secret": "cr0n"})
    assert r.status_code == 200 and r.json()["purged"] == 1
    assert [str(x[0]) for x in db("SELECT id FROM assistant_conversations")] == [new]
    assert db("SELECT count(*) FROM assistant_messages WHERE conversation_id=:c", c=old)[0][0] == 0

    # rotate: add k2, make it active; old rows still decrypt; reencrypt rewrites them
    s = get_settings()
    old_keys = open(s.assistant_encryption_keys_file, encoding="utf-8").read().strip()
    rotated = tmp_path / "rotated.keys"
    rotated.write_text(
        old_keys + "\nk2:" + base64.b64encode(os.urandom(32)).decode(), encoding="utf-8"
    )
    monkeypatch.setattr(s, "assistant_encryption_keys_file", str(rotated), raising=False)
    monkeypatch.setattr(s, "assistant_encryption_active_key", "k2", raising=False)
    crypto.reset_cache()
    assert all(
        bytes(b[0]).startswith(b"k1:") for b in db("SELECT text_enc FROM assistant_messages")
    )
    r = await client.get(f"/api/v1/assistant/conversations/{new}/messages", headers=_h(tok))
    assert [m["text"] for m in r.json()] == ["second", "new"]  # still readable with k1
    r = await client.post(
        "/api/v1/assistant/maintenance/reencrypt", headers={"X-Cron-Secret": "cr0n"}
    )
    assert r.status_code == 200, r.text
    assert (
        r.json()["reencrypted"] == 2
        and r.json()["remaining"] == 0
        and r.json()["active_key"] == "k2"
    )
    assert all(
        bytes(b[0]).startswith(b"k2:") for b in db("SELECT text_enc FROM assistant_messages")
    )
    assert db("SELECT DISTINCT enc_key_id FROM assistant_messages") == [("k2",)]
    r = await client.get(f"/api/v1/assistant/conversations/{new}/messages", headers=_h(tok))
    assert [m["text"] for m in r.json()] == ["second", "new"]
    crypto.reset_cache()


def test_handoff_render_is_a_fixed_template():
    from app.services.ticket_service import HandoffSummary

    h = HandoffSummary(
        category="payments",
        priority="high",
        refs={"payment_id": "abc"},
        attempted_actions=[],
        tool_calls_made=["get_my_wallet"],
        kyc_status="verified",
        roles=["investor"],
        active_role="investor",
        email_verified=True,
        lang="ar",
        conversation_id="c",
        transcript_url="/admin/x",
        turns=3,
    )
    text = h.render()
    assert text.startswith("Category: payments\nPriority: high\nReferences: payment_id=abc\n")
    assert "Transcript (admin panel, audited): /admin/x" in text and "turns: 3" in text


# --- release hardening (2026-09-24) -------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_quiet_stream_sends_keep_alives_and_still_finishes(
    client, db, configured, monkeypatch
):
    """nginx drops a proxied response after 60 s without data; a slow model must not cut the
    reply off, and the client ignores the comment lines."""
    import asyncio

    class SlowLLM(FakeLLM):
        async def stream(self, req):
            await asyncio.sleep(0.25)
            async for ev in super().stream(req):
                yield ev

    monkeypatch.setattr(assistant_routes, "KEEPALIVE_SECONDS", 0.05)
    llm = SlowLLM([FakeTurn(text="Hello after a pause.")])
    monkeypatch.setattr(assistant_routes, "llm_factory", lambda provider: llm)
    _enable(db)
    tok, _ = await _user(client, db, "slow@test.io")
    await _consent(client, tok)
    cid = (await client.post("/api/v1/assistant/conversations", headers=_h(tok))).json()["id"]
    async with client.stream(
        "POST",
        f"/api/v1/assistant/conversations/{cid}/messages",
        json={"text": "hi"},
        headers=_h(tok),
    ) as r:
        raw = (await r.aread()).decode()
    assert ": keep-alive" in raw
    events = [b for b in raw.split("\n\n") if b and not b.startswith(":")]
    assert events[0].startswith("event: started") and events[-1].startswith("event: done")
    assert any(b.startswith("event: delta") for b in events)


@pytest.mark.asyncio
async def test_consent_screen_only_for_users_the_assistant_is_open_to(client, db, configured):
    """Admins-only rollout: an ordinary user must not be asked to consent to a feature they
    cannot use (the widget would replace the site chat with a consent screen)."""
    _enable(db, rollout="admins")
    tok, _ = await _user(client, db, "notyet@test.io")
    st = (await client.get("/api/v1/assistant/status", headers=_h(tok))).json()
    assert (st["reason"], st["consent_required"]) == ("NOT_IN_ROLLOUT", False)
    _enable(db, rollout="all")
    st = (await client.get("/api/v1/assistant/status", headers=_h(tok))).json()
    assert (st["reason"], st["consent_required"]) == ("CONSENT_REQUIRED", True)


@pytest.mark.asyncio
async def test_no_chat_text_is_stored_readable(client, db, configured, monkeypatch):
    """Conversation rows are plaintext: the user's words must never be copied into them."""
    _enable(db)
    tok, _ = await _user(client, db, "plain@test.io")
    await _consent(client, tok)
    _fake(monkeypatch, FakeTurn(text="Sure."))
    cid = (await client.post("/api/v1/assistant/conversations", headers=_h(tok))).json()["id"]
    await _send(client, cid, f"my secret plan {SENTINEL}", _h(tok))
    row = db("SELECT title, visitor_key, status FROM assistant_conversations WHERE id=:i", i=cid)[0]
    assert all(SENTINEL not in str(v) for v in row)


@pytest.mark.asyncio
async def test_switches_accept_every_value_the_admin_panel_accepts(client, db, configured):
    _enable(db)
    _setting(db, "assistant_enabled", "yes")
    tok, _ = await _user(client, db, "yes@test.io")
    await _consent(client, tok)
    assert (await client.get("/api/v1/assistant/status", headers=_h(tok))).json()["enabled"] is True


def test_an_unreadable_key_file_switches_features_off_instead_of_crashing(monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(
        s, "assistant_encryption_keys_file", _write_keys(tmp_path, "k1"), raising=False
    )
    monkeypatch.setattr(s, "assistant_encryption_active_key", "k1", raising=False)

    def denied(*a, **kw):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(crypto, "open", denied, raising=False)
    crypto.reset_cache()
    try:
        assert crypto.is_configured() is False
    finally:
        crypto.reset_cache()


@pytest.mark.asyncio
async def test_visitors_are_capped_and_share_the_daily_budget(client, db, configured, monkeypatch):
    """Visitors are anonymous: without these limits, open visitor mode would let anyone spend
    the platform's AI budget without bound."""
    _enable(db, visitors=True, cap="1")
    _fake(monkeypatch, FakeTurn(text="One answer."))
    v = {"X-Visitor-Key": VKEY}
    cid = (await client.post("/api/v1/assistant/conversations", headers=v)).json()["id"]
    await _send(client, cid, "first", v)
    st = (await client.get("/api/v1/assistant/status", headers=v)).json()
    assert st["reason"] == "DAILY_CAP"
    # a new browser key gets its own cap, but not past the platform's daily token budget
    other = {"X-Visitor-Key": VKEY + "zz"}
    assert (await client.get("/api/v1/assistant/status", headers=other)).json()["enabled"] is True
    _setting(db, "assistant_daily_token_budget", "1")
    st = (await client.get("/api/v1/assistant/status", headers=other)).json()
    assert st["reason"] == "BUDGET_EXHAUSTED"
