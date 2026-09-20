"""Batch A (plan Phase 2): role tools, staff copilot, and the four new confirmable actions.

What each test protects:
  * every new tool keeps the allow-list rule (output model forbids extras, sensitive words
    never appear) and its role gate (owner/broker/LP/admin tools refuse other roles);
  * the four executors cancel/change ONLY the caller's own rows, exactly once, through the
    platform services (units are released, preferences upserted), with audit + system note;
  * proposing a cancellation for a row that is not the caller's, or not cancellable, is
    refused at proposal time (no card, no token);
  * staff tools are admin-only, mask identities, and change nothing.
"""

# ruff: noqa: E501
from __future__ import annotations

import base64
import json
import os
import re
import uuid

import pytest

from app.core import crypto
from app.core.config import get_settings
from app.core.errors import AppError
from app.services.assistant import actions, agent, guard
from app.services.assistant.context import AgentContext, load_context
from app.services.assistant.tools import REGISTRY
from app.services.assistant.tools.base import call_tool, parse_args

PW = "Passw0rd!23"
SENSITIVE = re.compile(
    r"national_id|iban|account_number|date_of_birth|passport|document_url|selfie|storage|"
    r"provider_applicant|raw_payload|token_hash|password|id_number|phone|address\b|"
    r"idempotency|download_url|[a-z0-9]@[a-z]+\.(com|io)\b",  # an UNmasked email
    re.I,
)


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


async def _user(client, db, email, *, roles=(), active=None, kyc="verified", balance=5000):
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Batch A"}
    )
    assert r.status_code == 201, r.text
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    for role in roles:
        db(
            "INSERT INTO user_roles (user_id, role) VALUES (:i,:r) ON CONFLICT DO NOTHING",
            i=uid,
            r=role,
        )
    if active:
        db("UPDATE users SET active_role=:r WHERE id=:i", i=uid, r=active)
    db("UPDATE kyc_verifications SET status=:s WHERE user_id=:i", s=kyc, i=uid)
    db("UPDATE wallets SET balance=:b WHERE user_id=:u", b=balance, u=uid)
    tok = (await client.post("/api/v1/auth/login", json={"email": email, "password": PW})).json()[
        "access_token"
    ]
    return uid, tok


def _prop(db, *, owner=None, status="active", slug=None) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,owner_id,title,slug,location,city,country,property_type,model,status,total_value,unit_price,"
        "total_units,available_units,minimum_investment,expected_yield,capital_appreciation,total_return,expected_completion) VALUES "
        "(:id,:o,'Batch Tower',:s,'Dubai','Dubai','UAE','apartment','ready-income',:st,100000,100,1000,600,100,7,3,10,'2027-06-30')",
        id=pid,
        o=owner,
        s=slug or f"batch-{pid[:8]}",
        st=status,
    )
    return pid


def _units(db, uid, pid, n):
    db(
        "INSERT INTO ownership_ledger (user_id, property_id, units, unit_price, reason, fee_rate) VALUES (:u,:p,:n,100,'purchase','1.0')",
        u=uid,
        p=pid,
        n=n,
    )


async def _ctx(asession, uid) -> AgentContext:
    ctx = await load_context(asession, user_id=uid)
    conv = await agent.start_conversation(asession, ctx)
    await asession.commit()
    return AgentContext(**{**ctx.__dict__, "conversation_id": conv.id})


async def _run(asession, ctx, name, args="{}") -> dict:
    spec = REGISTRY[name]
    guard.authorize(spec, ctx)
    return await call_tool(spec, asession, ctx, parse_args(spec, args))


async def _propose(asession, ctx, **args) -> tuple[uuid.UUID, str]:
    spec = REGISTRY["propose_action"]
    sink: list = []
    token_reset = guard.issued_tokens.set(sink)
    try:
        out = await call_tool(spec, asession, ctx, parse_args(spec, json.dumps(args)))
    finally:
        guard.issued_tokens.reset(token_reset)
    await asession.commit()
    return uuid.UUID(out["proposal_id"]), sink[0]["token"]


# --- registry / gating ------------------------------------------------------------------- #
def test_new_tools_are_registered_with_roles():
    assert len(REGISTRY) >= 36
    assert REGISTRY["list_my_properties"].roles == ("owner", "admin")
    assert REGISTRY["get_my_broker_activity"].roles == ("broker",)
    assert REGISTRY["list_my_lp_positions"].roles == ("liquidity_provider",)
    for name in ("get_ops_overview", "list_ops_queue", "lookup_member", "run_reconciliation_check"):
        assert REGISTRY[name].roles == ("admin",), name
    assert set(REGISTRY["propose_action"].input_model.model_fields) >= {
        "listing_id",
        "request_id",
        "gift_id",
        "email_returns",
    }


@pytest.mark.asyncio
async def test_role_tools_refuse_other_roles_and_leak_nothing(client, db, asession, keys):
    inv, _ = await _user(client, db, "inv@b.io")
    owner, _ = await _user(client, db, "own@b.io", roles=("owner",), active="owner")
    broker, _ = await _user(client, db, "brk@b.io", roles=("broker",), active="broker")
    lp, _ = await _user(
        client, db, "lp@b.io", roles=("liquidity_provider",), active="liquidity_provider"
    )
    pid = _prop(db, owner=owner, status="under_review")
    db(
        "INSERT INTO property_milestones (property_id, title, status, sort_index) VALUES (:p,'Foundation','completed',1)",
        p=pid,
    )
    ictx, octx, bctx, lctx = [await _ctx(asession, u) for u in (inv, owner, broker, lp)]

    for name, ctx in (
        ("list_my_properties", ictx),
        ("get_my_broker_activity", ictx),
        ("list_my_lp_positions", octx),
        ("get_ops_overview", octx),
        ("lookup_member", bctx),
    ):
        with pytest.raises(AppError) as exc:
            await _run(
                asession, ctx, name, '{"email":"x@y.io"}' if name == "lookup_member" else "{}"
            )
        assert exc.value.code == "ROLE_REQUIRED", name

    mine = await _run(asession, octx, "list_my_properties")
    assert [p["title"] for p in mine["items"]] == ["Batch Tower"]
    assert mine["items"][0]["status"] == "under_review" and mine["items"][0]["units_sold"] == 400
    assert mine["items"][0]["funding_progress_pct"] == 40.0
    detail = await _run(asession, octx, "get_my_property", json.dumps({"property_id": pid}))
    assert detail["milestones"][0]["title"] == "Foundation" and detail["property"]["id"] == pid
    with pytest.raises(AppError) as exc:
        await _run(
            asession, octx, "get_my_property", json.dumps({"property_id": _prop(db, owner=inv)})
        )
    assert exc.value.code == "NOT_FOUND"
    assert (
        await _run(asession, ictx, "list_my_properties" if False else "list_my_scheduled_gifts")
    )["items"] == []
    prefs = await _run(asession, ictx, "get_my_notification_preferences")
    assert prefs == {
        "email_investment_updates": True,
        "email_returns": True,
        "email_security_alerts": True,
        "email_new_properties": True,
    }
    broker_out = await _run(asession, bctx, "get_my_broker_activity")
    assert broker_out == {"referrals": [], "commissions": [], "commissions_total_count": 0}
    assert (await _run(asession, lctx, "list_my_lp_positions"))["items"] == []
    assert (await _run(asession, ictx, "list_my_family_transfers"))["items"] == []
    for payload in (mine, detail, prefs, broker_out):
        assert not SENSITIVE.search(json.dumps(payload)), payload


# --- executors ---------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_cancel_listing_exit_request_and_gift_are_owner_scoped_and_release_units(
    client, db, asession, keys
):
    seller, stok = await _user(client, db, "seller@b.io")
    other, _ = await _user(client, db, "other@b.io")
    pid = _prop(db)
    _units(db, seller, pid, 10)
    sh = {"Authorization": f"Bearer {stok}"}
    listing = (
        await client.post(
            "/api/v1/secondary/listings",
            json={"property_id": pid, "units": 3, "price_per_unit": 100},
            headers=sh,
        )
    ).json()
    listing_id = listing.get("id") or listing.get("listing_id")
    req = (
        await client.post(
            "/api/v1/liquidity/exit-requests", json={"property_id": pid, "units": 2}, headers=sh
        )
    ).json()
    request_id = req["request_id"]
    gift = await client.post(
        "/api/v1/gifts",
        json={
            "recipient_name": "Kid",
            "recipient_email": "kid@b.io",
            "asset_type": "property_shares",
            "property_id": pid,
            "units": 1,
            "scheduled_for": "2030-01-01",
        },
        headers={**sh, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert gift.status_code == 201, gift.text
    gift_id = gift.json()["id"]
    sctx, octx = await _ctx(asession, seller), await _ctx(asession, other)

    # the other user cannot even propose against the seller's rows
    for kwargs in (
        {"action": "cancel_secondary_listing", "listing_id": listing_id},
        {"action": "cancel_liquidity_exit_request", "request_id": request_id},
        {"action": "cancel_scheduled_gift", "gift_id": gift_id},
    ):
        with pytest.raises(AppError) as exc:
            await _propose(asession, octx, **kwargs)
        assert exc.value.code == "NOT_FOUND", kwargs
    assert db("SELECT count(*) FROM assistant_action_proposals")[0][0] == 0

    # the seller: proposal -> confirm -> row cancelled, units released, audited, system note
    pid_, tok = await _propose(
        asession, sctx, action="cancel_secondary_listing", listing_id=listing_id
    )
    p = await actions.confirm(asession, user_id=seller, proposal_id=pid_, token=tok)
    await asession.commit()
    assert p.status == "executed" and p.result["status"] == "cancelled"
    assert (
        db("SELECT status FROM secondary_listings WHERE id=:i", i=listing_id)[0][0] == "cancelled"
    )
    pid_, tok = await _propose(
        asession, sctx, action="cancel_liquidity_exit_request", request_id=request_id
    )
    p = await actions.confirm(asession, user_id=seller, proposal_id=pid_, token=tok)
    await asession.commit()
    assert p.status == "executed"
    assert db("SELECT status FROM lp_exit_requests WHERE id=:i", i=request_id)[0][0] == "cancelled"
    pid_, tok = await _propose(asession, sctx, action="cancel_scheduled_gift", gift_id=gift_id)
    p = await actions.confirm(asession, user_id=seller, proposal_id=pid_, token=tok)
    await asession.commit()
    assert p.status == "executed"
    assert db("SELECT status FROM scheduled_gifts WHERE id=:i", i=gift_id)[0][0] == "cancelled"
    # all 10 units are free again: a 10-unit listing succeeds
    r = await client.post(
        "/api/v1/secondary/listings",
        json={"property_id": pid, "units": 10, "price_per_unit": 100},
        headers=sh,
    )
    assert r.status_code == 200, r.text
    # a second proposal for the already-cancelled listing is refused
    with pytest.raises(AppError):
        await _propose(asession, sctx, action="cancel_secondary_listing", listing_id=listing_id)
    assert db("SELECT count(*) FROM audit_log WHERE action='assistant.action.executed'")[0][0] == 3
    assert db("SELECT count(*) FROM assistant_messages WHERE role='system_note'")[0][0] == 3


@pytest.mark.asyncio
async def test_update_notification_preferences_changes_only_the_given_keys(
    client, db, asession, keys
):
    uid, _ = await _user(client, db, "prefs@b.io")
    ctx = await _ctx(asession, uid)
    with pytest.raises(AppError) as exc:
        await _propose(asession, ctx, action="update_notification_preferences")
    assert exc.value.code == "INVALID_INPUT"
    pid_, tok = await _propose(
        asession,
        ctx,
        action="update_notification_preferences",
        email_returns=False,
        email_new_properties=False,
    )
    summary = db("SELECT summary FROM assistant_action_proposals WHERE id=:i", i=pid_)[0][0]
    assert "returns off" in summary and "new properties off" in summary
    p = await actions.confirm(asession, user_id=uid, proposal_id=pid_, token=tok)
    await asession.commit()
    assert p.status == "executed"
    prefs = await _run(asession, ctx, "get_my_notification_preferences")
    assert prefs == {
        "email_investment_updates": True,
        "email_returns": False,
        "email_security_alerts": True,
        "email_new_properties": False,
    }


# --- staff copilot ------------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_staff_tools_are_admin_only_read_only_and_masked(client, db, asession, keys):
    admin, _ = await _user(client, db, "admin@b.io", roles=("admin",), active="admin")
    member, mtok = await _user(client, db, "member@b.io", kyc="pending")
    db(
        "UPDATE kyc_verifications SET submitted_at=now(), manual_review_required=true WHERE user_id=:u",
        u=member,
    )
    r = await client.post(
        "/api/v1/withdrawals",
        json={"amount": 100, "method": "bank"},
        headers={"Authorization": f"Bearer {mtok}", "Idempotency-Key": str(uuid.uuid4())},
    )
    db(
        "INSERT INTO support_tickets (kind, user_id, category, priority, status, subject, source) VALUES ('support', :u, 'payments', 'high', 'open', 'Help', 'form'), ('knowledge_gap', :u, 'kyc', 'normal', 'open', 'Gap', 'assistant')",
        u=member,
    )
    _prop(db, owner=member, status="under_review")
    actx, mctx = await _ctx(asession, admin), await _ctx(asession, member)
    with pytest.raises(AppError) as exc:
        await _run(asession, mctx, "get_ops_overview")
    assert exc.value.code == "ROLE_REQUIRED"

    ov = await _run(asession, actx, "get_ops_overview")
    assert (
        ov["kyc_manual_review"] == 1 and ov["tickets_open"] == 1 and ov["knowledge_gaps_open"] == 1
    )
    assert ov["properties_pending_review"] == 1 and ov["assistant_conversations_today"] == 2
    q = await _run(asession, actx, "list_ops_queue", '{"queue":"kyc","limit":5}')
    assert (
        q["total"] == 1
        and q["items"][0]["user_masked"] == "me***@b.io"
        and q["items"][0]["method"] == "manual_review"
    )
    t = await _run(asession, actx, "list_ops_queue", '{"queue":"tickets","limit":5}')
    assert (
        t["items"][0]["reference"].startswith("CPX-") and t["items"][0]["status"] == "open (high)"
    )
    with pytest.raises(AppError):
        await _run(asession, actx, "list_ops_queue", '{"queue":"users","limit":5}')
    look = await _run(asession, actx, "lookup_member", '{"email":"member@b.io"}')
    assert (
        look["found"]
        and look["user_masked"] == "me***@b.io"
        and look["kyc_status"] == "pending"
        and look["open_tickets"] == 1
    )
    assert (await _run(asession, actx, "lookup_member", '{"email":"nobody@b.io"}'))[
        "found"
    ] is False
    rec = await _run(asession, actx, "run_reconciliation_check")
    assert isinstance(rec["ok"], bool) and len(rec["checks"]) >= 5
    for payload in (ov, q, t, look, rec):
        assert not SENSITIVE.search(json.dumps(payload)), payload
    # nothing changed
    assert db("SELECT status FROM kyc_verifications WHERE user_id=:u", u=member)[0][0] == "pending"
    assert db("SELECT count(*) FROM audit_log WHERE action LIKE 'assistant.action%'")[0][0] == 0
    _ = r
