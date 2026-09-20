"""Admin panel for the assistant (plan §4): audited transcript decrypt, ticket reply form,
knowledge-base approval, dashboard — all full-admin only.

What each test protects:
  * opening a conversation's details page shows the DECRYPTED text and writes exactly one
    ``assistant.transcript_viewed`` audit row (actor, conversation, ticket number);
  * a content editor gets 403 on every assistant page (list, details, reply form, dashboard);
  * the staff reply form posts through the audited service: a public reply notifies the
    owner and moves the ticket to waiting_user, an internal note does not;
  * approving a KB draft from the panel makes it live and retires the older version; an
    approved version cannot be edited in place; a draft can;
  * the dashboard renders the live switches and today's counters.
"""

# ruff: noqa: E501
from __future__ import annotations

import base64
import os
import uuid

import pytest

from app.core import crypto
from app.core.config import get_settings
from app.services import kb_service, ticket_service
from app.services.assistant import agent
from app.services.assistant.context import load_context
from app.services.llm.fake import FakeLLM, FakeTurn

PW = "Passw0rd!23"
SENTINEL = "ORCHID-LANTERN-4471"


@pytest.fixture
def keys(monkeypatch, tmp_path):
    s = get_settings()
    p = tmp_path / "assistant.keys"
    p.write_text("k1:" + base64.b64encode(os.urandom(32)).decode(), encoding="utf-8")
    monkeypatch.setattr(s, "assistant_encryption_keys_file", str(p), raising=False)
    monkeypatch.setattr(s, "assistant_encryption_active_key", "k1", raising=False)
    monkeypatch.setattr(s, "assistant_hmac_secret", "test-hmac", raising=False)
    crypto.reset_cache()
    yield
    crypto.reset_cache()


async def _panel_user(client, db, email: str, role: str) -> uuid.UUID:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": role}
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db(
        "INSERT INTO user_roles (user_id, role) VALUES (:i,:r) ON CONFLICT DO NOTHING",
        i=uid,
        r=role,
    )
    db("UPDATE users SET active_role=:r WHERE id=:i", i=uid, r=role)
    return uid


async def _panel_login(client, email: str) -> None:
    r = await client.post("/admin/login", data={"username": email, "password": PW})
    assert r.status_code in (200, 302, 303) and "session" in client.cookies, r.text[:200]


async def _conversation_with_ticket(client, db, asession, email="member@x.com"):
    """A member's conversation with one turn (containing the sentinel) and a handoff ticket."""
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Member"}
    )
    assert r.status_code == 201
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    ctx = await load_context(asession, user_id=uid)
    conv = await agent.start_conversation(asession, ctx)
    ctx = type(ctx)(**{**ctx.__dict__, "conversation_id": conv.id})
    settings = agent.AssistantSettings(
        enabled=True,
        visitor_enabled=False,
        provider="fake",
        model="fake-model",
        effort="low",
        max_output_tokens=256,
        disabled_tools=frozenset(),
        daily_message_cap=0,
        daily_token_budget=0,
        retention_days=180,
        rollout="all",
        pricing={},
    )
    llm = FakeLLM([FakeTurn(text=f"Answer {SENTINEL}")])
    async for _ in agent.run_turn(asession, ctx, f"Question {SENTINEL}", llm, settings=settings):
        pass
    handoff = await ticket_service.build_handoff_summary(
        asession, conversation_id=conv.id, category="payments", priority="high"
    )
    ticket = await ticket_service.create_from_handoff(asession, user_id=uid, handoff=handoff)
    await asession.commit()
    return uid, conv.id, ticket


@pytest.mark.asyncio
async def test_transcript_page_decrypts_and_is_audited(client, db, asession, keys):
    admin = await _panel_user(client, db, "admin@x.com", "admin")
    _uid, cid, ticket = await _conversation_with_ticket(client, db, asession)
    # ciphertext at rest, sentinel nowhere in the DB text columns
    assert all(
        bytes(r[0]).startswith(b"k1:") for r in db("SELECT text_enc FROM assistant_messages")
    )
    await _panel_login(client, "admin@x.com")

    r = await client.get(f"/admin/assistant-conversation/details/{cid}")
    assert r.status_code == 200, r.text[:300]
    assert r.text.count(SENTINEL) >= 2  # user question + assistant answer, decrypted (+ title)
    assert "assistant.transcript_viewed" in r.text and ticket.ticket_no in r.text
    audit = db(
        "SELECT actor_id, entity_id, after FROM audit_log WHERE action='assistant.transcript_viewed'"
    )
    assert len(audit) == 1 and audit[0][0] == admin and audit[0][1] == str(cid)
    assert audit[0][2] == {"messages": 2, "ticket_no": ticket.ticket_no}
    # the list page does not decrypt (no audit row, no text)
    r = await client.get("/admin/assistant-conversation/list")
    assert r.status_code == 200 and SENTINEL not in r.text
    assert (
        db("SELECT count(*) FROM audit_log WHERE action='assistant.transcript_viewed'")[0][0] == 1
    )
    # the ticket page links to the audited transcript and shows the structured summary only
    r = await client.get(f"/admin/support-ticket/details/{ticket.id}")
    assert r.status_code == 200 and f"/admin/assistant-conversation/details/{cid}" in r.text
    assert "Handoff summary" in r.text and SENTINEL not in r.text
    # dashboard
    r = await client.get("/admin/assistant-status")
    assert r.status_code == 200 and "Readiness" in r.text and "User messages" in r.text


@pytest.mark.asyncio
async def test_content_editor_is_locked_out_of_every_assistant_page(client, db, asession, keys):
    _uid, cid, ticket = await _conversation_with_ticket(client, db, asession)
    await _panel_user(client, db, "editor@x.com", "content_editor")
    await _panel_login(client, "editor@x.com")
    for path in (
        "/admin/assistant-conversation/list",
        f"/admin/assistant-conversation/details/{cid}",
        "/admin/support-ticket/list",
        f"/admin/support-ticket/details/{ticket.id}",
        f"/admin/support-ticket/reply/{ticket.id}",
        "/admin/kb-article/list",
        "/admin/kb-article/create",
        "/admin/assistant-action-proposal/list",
        "/admin/assistant-status",
    ):
        r = await client.get(path)
        assert r.status_code == 403, (path, r.status_code)
    r = await client.post(f"/admin/support-ticket/reply/{ticket.id}", data={"body": "nope"})
    assert r.status_code == 403
    assert (
        db("SELECT count(*) FROM audit_log WHERE action='assistant.transcript_viewed'")[0][0] == 0
    )
    assert db("SELECT count(*) FROM support_ticket_messages")[0][0] == 0


@pytest.mark.asyncio
async def test_reply_form_public_reply_and_internal_note(client, db, asession, keys):
    admin = await _panel_user(client, db, "admin2@x.com", "admin")
    uid, _cid, ticket = await _conversation_with_ticket(client, db, asession, email="m2@x.com")
    await _panel_login(client, "admin2@x.com")
    r = await client.get(f"/admin/support-ticket/reply/{ticket.id}")
    assert r.status_code == 200 and ticket.ticket_no in r.text
    # empty body -> 400 with the message, nothing written
    r = await client.post(f"/admin/support-ticket/reply/{ticket.id}", data={"body": "   "})
    assert r.status_code == 400 and "required" in r.text
    # public reply -> waiting_user, owner notified (+ email queued), audited
    r = await client.post(
        f"/admin/support-ticket/reply/{ticket.id}", data={"body": "We are on it.", "status": ""}
    )
    assert r.status_code == 303 and r.headers["location"].endswith(
        f"/admin/support-ticket/details/{ticket.id}"
    )
    assert db("SELECT status FROM support_tickets WHERE id=:i", i=ticket.id)[0][0] == "waiting_user"
    assert (
        db(
            "SELECT count(*) FROM notifications WHERE user_id=:u AND title LIKE 'Reply on ticket%'",
            u=uid,
        )[0][0]
        == 1
    )
    # internal note with a status change -> not visible to the owner, no notification
    r = await client.post(
        f"/admin/support-ticket/reply/{ticket.id}",
        data={"body": "check the bank ref", "internal": "1", "status": "in_progress"},
    )
    assert r.status_code == 303
    assert db("SELECT status FROM support_tickets WHERE id=:i", i=ticket.id)[0][0] == "in_progress"
    assert (
        db(
            "SELECT count(*) FROM notifications WHERE user_id=:u AND title LIKE 'Reply on ticket%'",
            u=uid,
        )[0][0]
        == 1
    )
    rows = db(
        "SELECT author_type, internal, author_id FROM support_ticket_messages ORDER BY created_at"
    )
    assert [(r[0], r[1]) for r in rows] == [("staff", False), ("staff", True)] and rows[0][
        2
    ] == admin
    assert db("SELECT count(*) FROM audit_log WHERE action='ticket.replied'")[0][0] == 2
    # the owner's API view hides the internal note
    tok = (
        await client.post("/api/v1/auth/login", json={"email": "m2@x.com", "password": PW})
    ).json()["access_token"]
    r = await client.get(
        f"/api/v1/support/tickets/{ticket.id}", headers={"Authorization": f"Bearer {tok}"}
    )
    assert [m["body"] for m in r.json()["messages"]] == ["We are on it."]
    # details page shows both, the note flagged
    r = await client.get(f"/admin/support-ticket/details/{ticket.id}")
    assert "check the bank ref" in r.text and "internal note" in r.text
    # list action: close
    r = await client.get(f"/admin/support-ticket/action/ticket-close?pks={ticket.id}")
    assert r.status_code in (200, 302)
    assert db(
        "SELECT status, resolved_at IS NOT NULL FROM support_tickets WHERE id=:i", i=ticket.id
    )[0] == ("closed", True)


@pytest.mark.asyncio
async def test_kb_approve_action_and_edit_lock(client, db, asession, keys):
    admin = await _panel_user(client, db, "admin3@x.com", "admin")
    await _panel_login(client, "admin3@x.com")
    # create a draft through the panel form
    r = await client.post(
        "/admin/kb-article/create",
        data={
            "slug": "fees",
            "lang": "en",
            "title": "Fees",
            "body_md": "Fees are shown before you pay.",
            "category": "fees",
            "audience": "all",
            "priority": "10",
            "source_ref": "/fees",
        },
    )
    assert r.status_code in (200, 302, 303), r.text[:300]
    row = db("SELECT id, status, version FROM kb_articles WHERE slug='fees'")
    assert len(row) == 1 and row[0][1] == "draft" and row[0][2] == 1
    v1 = row[0][0]
    assert await kb_service.render_bundle(asession) == "(no approved articles yet)"
    # approve from the list action
    r = await client.get(f"/admin/kb-article/action/kb-approve?pks={v1}")
    assert r.status_code in (200, 302)
    assert db("SELECT status, approved_by FROM kb_articles WHERE id=:i", i=v1)[0] == (
        "approved",
        admin,
    )
    assert "Fees are shown before you pay." in await kb_service.render_bundle(asession)
    # editing the approved version in place is refused
    r = await client.post(
        f"/admin/kb-article/edit/{v1}",
        data={
            "slug": "fees",
            "lang": "en",
            "title": "Fees",
            "body_md": "CHANGED",
            "category": "fees",
            "audience": "all",
            "priority": "10",
            "source_ref": "",
        },
    )
    assert "cannot be edited" in r.text
    assert (
        db("SELECT body_md FROM kb_articles WHERE id=:i", i=v1)[0][0]
        == "Fees are shown before you pay."
    )
    # a second version (same slug/lang) becomes v2 draft; approving it retires v1
    r = await client.post(
        "/admin/kb-article/create",
        data={
            "slug": "fees",
            "lang": "en",
            "title": "Fees",
            "body_md": "Fees v2.",
            "category": "fees",
            "audience": "all",
            "priority": "10",
            "source_ref": "",
        },
    )
    v2 = db("SELECT id FROM kb_articles WHERE slug='fees' AND version=2")[0][0]
    assert db("SELECT status FROM kb_articles WHERE id=:i", i=v2)[0][0] == "draft"
    await client.get(f"/admin/kb-article/action/kb-approve?pks={v2}")
    assert db("SELECT status FROM kb_articles WHERE id=:i", i=v1)[0][0] == "retired"
    bundle = await kb_service.render_bundle(asession)
    assert "Fees v2." in bundle and "before you pay" not in bundle
    assert db("SELECT count(*) FROM audit_log WHERE action='kb.approved'")[0][0] == 2
    # retire from the panel; the assistant loses the article
    await client.get(f"/admin/kb-article/action/kb-retire?pks={v2}")
    assert await kb_service.render_bundle(asession) == "(no approved articles yet)"


@pytest.mark.asyncio
async def test_assistant_setting_changes_are_validated_and_audited(client, db, keys):
    admin = await _panel_user(client, db, "admin4@x.com", "admin")
    await _panel_login(client, "admin4@x.com")
    r = await client.post(
        "/admin/platform-setting/create",
        data={"key": "assistant_rollout", "value": "everyone", "description": ""},
    )
    assert "must be one of" in r.text
    assert db("SELECT count(*) FROM platform_settings WHERE key='assistant_rollout'")[0][0] == 0
    r = await client.post(
        "/admin/platform-setting/create",
        data={"key": "assistant_rollout", "value": "all", "description": ""},
    )
    assert r.status_code in (200, 302, 303)
    assert db("SELECT value FROM platform_settings WHERE key='assistant_rollout'")[0][0] == "all"
    r = await client.post(
        "/admin/platform-setting/edit/assistant_rollout",
        data={"key": "assistant_rollout", "value": "admins", "description": ""},
    )
    assert r.status_code in (200, 302, 303)
    audit = db(
        "SELECT actor_id, entity_id, before, after FROM audit_log WHERE action='assistant.settings_changed' ORDER BY created_at"
    )
    assert len(audit) == 2 and audit[1][0] == admin and audit[1][1] == "assistant_rollout"
    assert audit[1][2] == {"value": "all"} and audit[1][3] == {"value": "admins"}
    r = await client.post(
        "/admin/platform-setting/create",
        data={"key": "assistant_model_pricing", "value": "[1,2]", "description": ""},
    )
    assert "JSON object" in r.text
