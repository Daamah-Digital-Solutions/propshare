"""Provider lookup — the safety net when a payment webhook never arrives.

A card/crypto payment used to be credited ONLY by the provider's webhook. If the endpoint was
created after the payment, its signing secret was wrong, or the delivery failed, the money
left the customer and nothing moved on the platform. These tests pin the two recovery paths:
the cron sweep (``POST /payments/maintenance/reconcile``) and the on-read lookup behind
``GET /payments/{id}`` that the return page polls — and that neither can ever credit twice.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.integrations.payments import CheckoutResult, ParsedWebhook
from app.services.integrations.payments import nowpayments_gateway as nowp
from app.services.integrations.payments import stripe_gateway as stripe

PW = "Passw0rd!23"


async def _register(client, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "W"}
    )
    return r.json()["access_token"]


async def _verified_user(client, db, email: str) -> str:
    token = await _register(client, email)
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=_uid(db, email))
    return token


def _uid(db, email: str) -> str:
    return db("SELECT id FROM users WHERE email=:e", e=email)[0][0]


def _pending_card_deposit(db, *, uid: str, cs: str, amount, minutes_old: int) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO payments (id, user_id, provider, provider_payment_id, amount, currency,"
        " status, purpose, payment_method, created_at) VALUES"
        " (:id,:uid,'stripe',:cs,:amt,'USD','pending','deposit','card',"
        " now() - make_interval(mins => :m))",
        id=pid,
        uid=uid,
        cs=cs,
        amt=amount,
        m=minutes_old,
    )
    return pid


def _lookup_answer(monkeypatch, *, status: str, captured=None) -> list[str]:
    """Stripe's answer to 'how did this session end?', without the network."""
    calls: list[str] = []

    async def fake_lookup(session_id: str) -> ParsedWebhook:
        calls.append(session_id)
        return ParsedWebhook(
            event_id=f"sync:{session_id}:{status}",
            provider_payment_id=session_id,
            order_id=None,
            status=status,
            captured_amount=captured,
            type="checkout.session.lookup",
            raw={},
        )

    monkeypatch.setattr(stripe, "lookup_configured", lambda: True)
    monkeypatch.setattr(stripe, "get_checkout_status", fake_lookup)
    return calls


async def _webhook(client, *, payment_id: str, cs: str, cents: int, event_id: str):
    body = json.dumps(
        {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": cs,
                    "client_reference_id": payment_id,
                    "payment_status": "paid",
                    "amount_total": cents,
                    "currency": "usd",
                }
            },
        }
    ).encode()
    ts = "1700000000"
    sig = hmac.new(b"whsec_t", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return await client.post(
        "/api/v1/payments/webhooks/stripe",
        content=body,
        headers={"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"},
    )


async def _reconcile(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "cron_secret", "cron-t", raising=False)
    return await client.post(
        "/api/v1/payments/maintenance/reconcile", headers={"X-Cron-Secret": "cron-t"}
    )


def _told(db, uid: str, title: str) -> int:
    return db("SELECT count(*) FROM notifications WHERE user_id=:i AND title=:t", i=uid, t=title)[
        0
    ][0]


@pytest.mark.asyncio
async def test_reconcile_credits_a_paid_deposit_the_webhook_missed(client, db, monkeypatch):
    """The customer paid, Stripe never delivered the event (endpoint created later / wrong
    secret): the sweep asks Stripe and credits once; the late webhook then changes nothing."""
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)
    await _register(client, "missed@rec.com")
    uid = _uid(db, "missed@rec.com")
    pid = _pending_card_deposit(db, uid=uid, cs="cs_missed", amount=80, minutes_old=5)
    calls = _lookup_answer(monkeypatch, status="succeeded", captured=80)

    r = await _reconcile(client, monkeypatch)
    assert r.status_code == 200, r.text
    assert r.json()["checked"] == 1 and r.json()["settled"] == 1
    assert calls == ["cs_missed"]
    row = db("SELECT status, amount_captured FROM payments WHERE id=:p", p=pid)[0]
    assert (row[0], row[1]) == ("succeeded", 80)
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 80
    assert db("SELECT count(*) FROM transactions WHERE reference_id=:p", p=pid)[0][0] == 1
    assert db("SELECT count(*) FROM audit_log WHERE action='payment.sync.succeeded'")[0][0] == 1
    # the member is told exactly like after a webhook: in-app + email
    assert _told(db, uid, "Deposit received") == 1
    assert (
        db(
            "SELECT count(*) FROM email_outbox WHERE user_id=:i AND category='investment_updates'",
            i=uid,
        )[0][0]
        == 1
    )

    # the real event finally arrives -> already settled, nothing moves twice
    late = await _webhook(client, payment_id=pid, cs="cs_missed", cents=8000, event_id="evt_l")
    assert late.json()["status"] == "already_processed"
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 80
    assert db("SELECT count(*) FROM transactions WHERE reference_id=:p", p=pid)[0][0] == 1
    assert _told(db, uid, "Deposit received") == 1
    # a second sweep has nothing left to do
    assert (await _reconcile(client, monkeypatch)).json()["checked"] == 0


@pytest.mark.asyncio
async def test_reconcile_leaves_unpaid_alone_and_fails_expired(client, db, monkeypatch):
    await _register(client, "unpaid@rec.com")
    uid = _uid(db, "unpaid@rec.com")
    pid = _pending_card_deposit(db, uid=uid, cs="cs_open", amount=30, minutes_old=5)

    _lookup_answer(monkeypatch, status="pending")
    r = await _reconcile(client, monkeypatch)
    assert r.json()["pending"] == 1 and r.json()["settled"] == 0
    assert db("SELECT status FROM payments WHERE id=:p", p=pid)[0][0] == "pending"
    # nothing applied, nothing recorded — the later look that finds it paid is not blocked
    assert db("SELECT count(*) FROM payment_events")[0][0] == 0
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 0

    _lookup_answer(monkeypatch, status="failed")
    r = await _reconcile(client, monkeypatch)
    assert r.json()["failed"] == 1
    assert db("SELECT status FROM payments WHERE id=:p", p=pid)[0][0] == "failed"
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 0
    assert db("SELECT count(*) FROM audit_log WHERE action='payment.sync.failed'")[0][0] == 1


@pytest.mark.asyncio
async def test_reconcile_skips_fresh_rows_counts_errors_and_is_honest_when_unconfigured(
    client, db, monkeypatch
):
    await _register(client, "fresh@rec.com")
    uid = _uid(db, "fresh@rec.com")
    _pending_card_deposit(db, uid=uid, cs="cs_fresh", amount=10, minutes_old=0)
    old = _pending_card_deposit(db, uid=uid, cs="cs_err", amount=10, minutes_old=5)

    async def boom(session_id: str):
        raise AppError("PAYMENT_PROVIDER_ERROR", "Stripe error (500).", status_code=502)

    monkeypatch.setattr(stripe, "lookup_configured", lambda: True)
    monkeypatch.setattr(stripe, "get_checkout_status", boom)
    r = await _reconcile(client, monkeypatch)
    # the fresh one is still on the checkout page (not asked); the old one errored, batch went on
    assert r.json() == {
        "configured": True,
        "checked": 1,
        "settled": 0,
        "failed": 0,
        "pending": 0,
        "errors": 1,
    }
    assert db("SELECT status FROM payments WHERE id=:p", p=old)[0][0] == "pending"

    monkeypatch.setattr(stripe, "lookup_configured", lambda: False)
    monkeypatch.setattr(nowp, "is_configured", lambda: False)
    r = await _reconcile(client, monkeypatch)
    assert r.json()["configured"] is False and r.json()["checked"] == 0

    # not for anonymous callers
    assert (await client.post("/api/v1/payments/maintenance/reconcile")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_reading_a_pending_payment_asks_the_provider(client, db, monkeypatch):
    """The return page polls GET /payments/{id}: the read itself settles the payment when the
    provider says it is paid, so the payer sees the credit without any webhook."""
    token = await _register(client, "poll@rec.com")
    uid = _uid(db, "poll@rec.com")
    pid = _pending_card_deposit(db, uid=uid, cs="cs_poll", amount=25, minutes_old=1)
    calls = _lookup_answer(monkeypatch, status="succeeded", captured=25)
    hdr = {"Authorization": f"Bearer {token}"}

    r = await client.get(f"/api/v1/payments/{pid}", headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "succeeded" and r.json()["amount_captured"] == "25.00"
    assert calls == ["cs_poll"]
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 25
    assert _told(db, uid, "Deposit received") == 1
    # settled rows are never looked up again
    r = await client.get(f"/api/v1/payments/{pid}", headers=hdr)
    assert r.json()["status"] == "succeeded" and calls == ["cs_poll"]


@pytest.mark.asyncio
async def test_reading_a_pending_payment_survives_a_provider_error(client, db, monkeypatch):
    token = await _register(client, "pollerr@rec.com")
    uid = _uid(db, "pollerr@rec.com")
    pid = _pending_card_deposit(db, uid=uid, cs="cs_perr", amount=25, minutes_old=1)

    async def boom(session_id: str):
        raise AppError("PAYMENT_PROVIDER_ERROR", "Stripe error (502).", status_code=502)

    monkeypatch.setattr(stripe, "lookup_configured", lambda: True)
    monkeypatch.setattr(stripe, "get_checkout_status", boom)
    r = await client.get(f"/api/v1/payments/{pid}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 0


@pytest.mark.asyncio
async def test_return_urls_carry_the_payment_id_and_the_roles_wallet(client, db, monkeypatch):
    """Stripe sends the payer back to the wallet tab of the dashboard they were using, with
    our payment id so that page can follow the payment until it is credited."""
    captured: dict = {}

    async def fake_checkout(**kwargs):
        captured.update(kwargs)
        return CheckoutResult(
            provider_payment_id="cs_ret", checkout_url="https://s/c", status="pending"
        )

    monkeypatch.setattr(stripe, "is_configured", lambda: True)
    monkeypatch.setattr(stripe, "create_checkout", fake_checkout)
    token = await _verified_user(client, db, "ret@rec.com")
    r = await client.post(
        "/api/v1/wallet/deposit",
        json={"amount": 40, "method": "card"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "ret-1"},
    )
    assert r.status_code == 200, r.text
    pid = r.json()["payment_id"]
    base = get_settings().app_base_url.rstrip("/")
    assert captured["success_url"] == f"{base}/dashboard?tab=wallet&deposit=success&payment={pid}"
    assert captured["cancel_url"] == f"{base}/dashboard?tab=wallet&deposit=cancelled&payment={pid}"

    # a member using the liquidity-provider dashboard is sent back to THAT wallet tab
    uid = _uid(db, "ret@rec.com")
    db(
        "INSERT INTO user_roles (user_id, role) VALUES (:u, 'liquidity_provider')"
        " ON CONFLICT DO NOTHING",
        u=uid,
    )
    sw = await client.post(
        "/api/v1/auth/switch-role",
        json={"role": "liquidity_provider"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sw.status_code == 200, sw.text
    # the active role lives on the user; a fresh login carries it in the token
    login = await client.post("/api/v1/auth/login", json={"email": "ret@rec.com", "password": PW})
    lp_token = login.json()["access_token"]
    r = await client.post(
        "/api/v1/wallet/deposit",
        json={"amount": 40, "method": "card"},
        headers={"Authorization": f"Bearer {lp_token}", "Idempotency-Key": "ret-2"},
    )
    assert r.status_code == 200, r.text
    assert captured["success_url"].startswith(
        f"{base}/liquidity-dashboard?tab=wallet&deposit=success"
    )


@pytest.mark.asyncio
async def test_webhook_credit_tells_the_member_in_app_and_by_email(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)
    await _register(client, "told@rec.com")
    uid = _uid(db, "told@rec.com")
    pid = _pending_card_deposit(db, uid=uid, cs="cs_told", amount=15, minutes_old=0)
    r = await _webhook(client, payment_id=pid, cs="cs_told", cents=1500, event_id="evt_told")
    assert r.json()["result"] == "credited"
    assert _told(db, uid, "Deposit received") == 1
    assert (
        db(
            "SELECT count(*) FROM email_outbox WHERE user_id=:i AND category='investment_updates'"
            " AND status='pending'",
            i=uid,
        )[0][0]
        == 1
    )
    # a replayed delivery does not tell them twice
    r = await _webhook(client, payment_id=pid, cs="cs_told", cents=1500, event_id="evt_told")
    assert r.json()["status"] == "duplicate"
    assert _told(db, uid, "Deposit received") == 1


@pytest.mark.asyncio
async def test_late_failure_event_never_undoes_a_settled_payment(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)
    await _register(client, "latefail@rec.com")
    uid = _uid(db, "latefail@rec.com")
    pid = _pending_card_deposit(db, uid=uid, cs="cs_lf", amount=15, minutes_old=0)
    assert (
        await _webhook(client, payment_id=pid, cs="cs_lf", cents=1500, event_id="evt_ok")
    ).json()["result"] == "credited"
    body = json.dumps(
        {
            "id": "evt_exp",
            "type": "checkout.session.expired",
            "data": {"object": {"id": "cs_lf", "client_reference_id": pid}},
        }
    ).encode()
    ts = "1700000000"
    sig = hmac.new(b"whsec_t", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    r = await client.post(
        "/api/v1/payments/webhooks/stripe",
        content=body,
        headers={"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"},
    )
    assert r.json()["status"] == "already_processed"
    assert db("SELECT status FROM payments WHERE id=:p", p=pid)[0][0] == "succeeded"
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 15
