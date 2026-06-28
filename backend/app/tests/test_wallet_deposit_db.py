"""Phase 4 — DB-backed wallet/deposit tests (the money gates).

Covers: KYC gate, Idempotency-Key requirement + replay, honest 503, and the
webhook-driven credit — exactly-once, server-authoritative amount, replay no-op,
forged-signature rejection, failed-no-credit, atomic ledger, and reconciliation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest

from app.core.config import get_settings
from app.services.integrations.payments import CheckoutResult
from app.services.integrations.payments import nowpayments_gateway as nowp
from app.services.integrations.payments import stripe_gateway as stripe

PW = "Passw0rd!23"


async def _register(client, email: str) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "W"}
    )
    return r.json()["access_token"], r.json().get("access_token")


async def _verified_user(client, db, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "W"}
    )
    token = r.json()["access_token"]
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    return token


def _uid(db, email: str) -> str:
    return db("SELECT id FROM users WHERE email=:e", e=email)[0][0]


def _insert_payment(db, *, pid, uid, provider, ppid, amount, method) -> None:
    db(
        "INSERT INTO payments (id, user_id, provider, provider_payment_id, amount, currency,"
        " status, purpose, payment_method) VALUES"
        " (:id,:uid,:prov,:ppid,:amt,'USD','pending','deposit',:pm)",
        id=pid,
        uid=uid,
        prov=provider,
        ppid=ppid,
        amt=amount,
        pm=method,
    )


def _stripe_session_event(payment_id: str, *, amount_cents: int, event_id="evt_x", paid=True):
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_" + payment_id[:8],
                "client_reference_id": payment_id,
                "payment_status": "paid" if paid else "unpaid",
                "amount_total": amount_cents,
                "currency": "usd",
            }
        },
    }


async def _stripe_post(client, body: bytes, secret="whsec_t"):
    ts = "1700000000"
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return await client.post(
        "/api/v1/payments/webhooks/stripe",
        content=body,
        headers={"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"},
    )


# --- gating / validation ---------------------------------------------------- #
@pytest.mark.asyncio
async def test_deposit_blocked_until_kyc_verified(client, db):
    token, _ = await _register(client, "nokyc@dep.com")
    r = await client.post(
        "/api/v1/wallet/deposit",
        json={"amount": 100, "method": "card"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "k1"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "KYC_REQUIRED"


@pytest.mark.asyncio
async def test_deposit_requires_idempotency_key(client, db):
    token = await _verified_user(client, db, "key@dep.com")
    r = await client.post(
        "/api/v1/wallet/deposit",
        json={"amount": 100, "method": "card"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


@pytest.mark.asyncio
async def test_deposit_503_when_provider_unconfigured(client, db):
    token = await _verified_user(client, db, "unconf@dep.com")
    r = await client.post(
        "/api/v1/wallet/deposit",
        json={"amount": 100, "method": "card"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "k2"},
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "PAYMENTS_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_idempotency_key_replay_returns_same_intent(client, db, monkeypatch):
    token = await _verified_user(client, db, "idem@dep.com")

    async def fake_checkout(**kwargs):
        return CheckoutResult(
            provider_payment_id="cs_fake", checkout_url="https://pay.test", status="pending"
        )

    monkeypatch.setattr(stripe, "is_configured", lambda: True)
    monkeypatch.setattr(stripe, "create_checkout", fake_checkout)
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "same-key"}
    r1 = await client.post(
        "/api/v1/wallet/deposit", json={"amount": 100, "method": "card"}, headers=headers
    )
    r2 = await client.post(
        "/api/v1/wallet/deposit", json={"amount": 100, "method": "card"}, headers=headers
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["payment_id"] == r2.json()["payment_id"]
    assert db("SELECT count(*) FROM payments WHERE idempotency_key='same-key'")[0][0] == 1


# --- webhook credit (the core) --------------------------------------------- #
@pytest.mark.asyncio
async def test_stripe_webhook_credits_once_and_replay_is_noop(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)
    await _register(client, "credit@dep.com")
    uid = _uid(db, "credit@dep.com")
    pid = str(uuid.uuid4())
    _insert_payment(
        db, pid=pid, uid=uid, provider="stripe", ppid="cs_" + pid[:8], amount=50, method="card"
    )

    body = json.dumps(_stripe_session_event(pid, amount_cents=5000, event_id="evt_credit")).encode()
    first = await _stripe_post(client, body)
    assert first.status_code == 200 and first.json()["result"] == "credited"
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 50
    assert db("SELECT status FROM payments WHERE id=:p", p=pid)[0][0] == "succeeded"
    assert (
        db("SELECT count(*) FROM transactions WHERE reference_id=:p AND type='deposit'", p=pid)[0][
            0
        ]
        == 1
    )
    assert db("SELECT count(*) FROM audit_log WHERE action='wallet.credit'")[0][0] == 1

    # replay the identical event -> deduped, balance unchanged, still one ledger row
    second = await _stripe_post(client, body)
    assert second.json()["status"] == "duplicate"
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 50
    assert db("SELECT count(*) FROM transactions WHERE reference_id=:p", p=pid)[0][0] == 1
    # reconciliation: balance == sum(ledger)
    bal = db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0]
    led = db("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=:i", i=uid)[0][0]
    assert bal == led


@pytest.mark.asyncio
async def test_credits_captured_amount_not_client_requested(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)
    await _register(client, "captured@dep.com")
    uid = _uid(db, "captured@dep.com")
    pid = str(uuid.uuid4())
    # requested 10, but provider captured 50 -> we credit the CAPTURED amount
    _insert_payment(
        db, pid=pid, uid=uid, provider="stripe", ppid="cs_" + pid[:8], amount=10, method="card"
    )
    body = json.dumps(_stripe_session_event(pid, amount_cents=5000, event_id="evt_cap")).encode()
    assert (await _stripe_post(client, body)).json()["result"] == "credited"
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 50


@pytest.mark.asyncio
async def test_forged_webhook_rejected_no_credit(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)
    await _register(client, "forge@dep.com")
    uid = _uid(db, "forge@dep.com")
    pid = str(uuid.uuid4())
    _insert_payment(
        db, pid=pid, uid=uid, provider="stripe", ppid="cs_" + pid[:8], amount=50, method="card"
    )
    body = json.dumps(_stripe_session_event(pid, amount_cents=5000)).encode()
    r = await client.post(
        "/api/v1/payments/webhooks/stripe",
        content=body,
        headers={"stripe-signature": "t=1700000000,v1=bad", "content-type": "application/json"},
    )
    assert r.status_code == 401
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 0
    assert db("SELECT status FROM payments WHERE id=:p", p=pid)[0][0] == "pending"


@pytest.mark.asyncio
async def test_failed_webhook_does_not_credit(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)
    await _register(client, "failed@dep.com")
    uid = _uid(db, "failed@dep.com")
    pid = str(uuid.uuid4())
    _insert_payment(
        db, pid=pid, uid=uid, provider="stripe", ppid="cs_" + pid[:8], amount=50, method="card"
    )
    event = {
        "id": "evt_exp",
        "type": "checkout.session.expired",
        "data": {"object": {"id": "cs_" + pid[:8], "client_reference_id": pid}},
    }
    body = json.dumps(event).encode()
    r = await _stripe_post(client, body)
    assert r.json()["result"] == "failed"
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 0
    assert db("SELECT status FROM payments WHERE id=:p", p=pid)[0][0] == "failed"


@pytest.mark.asyncio
async def test_nowpayments_ipn_credits(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "nowpayments_ipn_secret", "ipn_t", raising=False)
    await _register(client, "np@dep.com")
    uid = _uid(db, "np@dep.com")
    pid = str(uuid.uuid4())
    _insert_payment(
        db, pid=pid, uid=uid, provider="nowpayments", ppid="np_1", amount=80, method="crypto"
    )
    payload = {
        "payment_id": "np_1",
        "order_id": pid,
        "payment_status": "finished",
        "price_amount": 80,
    }
    body = json.dumps(payload).encode()
    sig = nowp.compute_signature("ipn_t", body)
    r = await client.post(
        "/api/v1/payments/webhooks/nowpayments",
        content=body,
        headers={"x-nowpayments-sig": sig, "content-type": "application/json"},
    )
    assert r.json()["result"] == "credited"
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 80


@pytest.mark.asyncio
async def test_wallet_me_requires_auth(client):
    assert (await client.get("/api/v1/wallet/me")).status_code == 401
    assert (await client.get("/api/v1/wallet/transactions")).status_code == 401
