"""Phase 7 — DB-backed withdrawal/payout tests (the money-OUT gates).

Acceptance bar: over-balance rejected; exact-balance OK; concurrent double-withdraw
can't double-spend; request idempotency; auto-approve ≤ limit vs review > limit;
rejected review releases funds; failed/returned payout returns funds; executor
submit-failure releases; atomicity rollback; reconciliation of stuck payouts; and
the invariants (balance == SUM(ledger) incl. holds; pending_balance == Σ non-terminal).

Providers are MOCKED (payouts hit real sandboxes only on the VPS); settlement
webhooks are simulated with valid signatures.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid

import pytest

from app.core.config import get_settings
from app.services.integrations.payments import PayoutResult
from app.services.integrations.payments import nowpayments_gateway as nowp
from app.services.integrations.payments import stripe_gateway as stripe

PW = "Passw0rd!23"


# --- helpers ---------------------------------------------------------------- #
async def _verified(client, db, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "W"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    return r.json()["access_token"]


async def _admin(client, db, email: str) -> str:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "A"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("INSERT INTO user_roles (user_id, role) VALUES (:i,'admin')", i=uid)
    db("UPDATE users SET active_role='admin' WHERE id=:i", i=uid)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return login.json()["access_token"]


def _uid(db, email: str) -> str:
    return db("SELECT id FROM users WHERE email=:e", e=email)[0][0]


def _fund(db, uid: str, amount) -> None:
    db(
        "INSERT INTO transactions (user_id, type, amount, status) "
        "VALUES (:u,'deposit',:a,'completed')",
        u=uid,
        a=amount,
    )
    db("UPDATE wallets SET balance=:a WHERE user_id=:u", a=amount, u=uid)


def _bal(db, uid):
    return db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0]


def _pending(db, uid):
    return db("SELECT pending_balance FROM wallets WHERE user_id=:i", i=uid)[0][0]


def _configure_crypto(monkeypatch):
    s = get_settings()
    for attr, val in [
        ("nowpayments_api_key", "k"),
        ("nowpayments_email", "e@x.com"),
        ("nowpayments_password", "pw"),
        ("nowpayments_ipn_secret", "ipn_t"),
    ]:
        monkeypatch.setattr(s, attr, val, raising=False)

    async def fake_payout(**kw):
        return PayoutResult(
            provider_payout_id="np_" + str(kw["withdrawal_id"])[:8], status="processing"
        )

    monkeypatch.setattr(nowp, "create_payout", fake_payout)


def _configure_bank(monkeypatch, db, uid: str):
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_t", raising=False)
    db(
        "INSERT INTO connect_accounts (user_id, stripe_account_id, payouts_enabled, "
        "details_submitted, status) VALUES (:u,'acct_x',true,true,'verified')",
        u=uid,
    )

    async def fake_payout(**kw):
        return PayoutResult(
            provider_payout_id="tr_" + str(kw["withdrawal_id"])[:8], status="processing"
        )

    monkeypatch.setattr(stripe, "create_payout", fake_payout)


async def _withdraw(client, token, amount, method="crypto", address="addr1", key="auto"):
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = str(uuid.uuid4()) if key == "auto" else key
    body = {"amount": amount, "method": method}
    if address is not None:
        body["address"] = address
    return await client.post("/api/v1/wallet/withdrawals", json=body, headers=headers)


async def _execute(client, admin_tok):
    return await client.post(
        "/api/v1/admin/withdrawals/execute", headers={"Authorization": f"Bearer {admin_tok}"}
    )


async def _signed_nowp(client, payload: dict):
    body = json.dumps(payload).encode()
    sig = nowp.compute_signature("ipn_t", body)
    return await client.post(
        "/api/v1/payments/webhooks/nowpayments-payouts",
        content=body,
        headers={"x-nowpayments-sig": sig, "content-type": "application/json"},
    )


async def _signed_stripe(client, event: dict):
    body = json.dumps(event).encode()
    ts = "1700000000"
    sig = hmac.new(b"whsec_t", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return await client.post(
        "/api/v1/payments/webhooks/stripe-payouts",
        content=body,
        headers={"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"},
    )


def _assert_balance_invariant(db, uid):
    bal = _bal(db, uid)
    led = db("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=:i", i=uid)[0][0]
    assert bal == led, f"balance {bal} != ledger {led}"


def _assert_pending_invariant(db, uid):
    pending = _pending(db, uid)
    inflight = db(
        "SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE user_id=:i AND status IN "
        "('pending_review','approved','processing')",
        i=uid,
    )[0][0]
    assert pending == inflight, f"pending {pending} != in-flight {inflight}"


@pytest.fixture(autouse=True)
def _automated_payout_mode(_clean, db):
    """This module exercises the AUTOMATED (Stripe/NOWPayments) payout path. Manual mode is the
    live default (Task 3), so turn it OFF here so requests flow through the provider executor;
    the manual admin-settled path is covered by test_manual_payout_db.py. Depends on ``_clean``
    so the row is written AFTER the per-test truncation (else it would be wiped)."""
    db(
        "INSERT INTO platform_settings (key, value) VALUES ('manual_payouts_enabled','false') "
        "ON CONFLICT (key) DO UPDATE SET value='false'"
    )


# --- gating / validation ---------------------------------------------------- #
@pytest.mark.asyncio
async def test_withdraw_requires_kyc(client, db, monkeypatch):
    _configure_crypto(monkeypatch)
    r = await client.post(
        "/api/v1/auth/register", json={"email": "nk@w.com", "password": PW, "full_name": "N"}
    )
    res = await _withdraw(client, r.json()["access_token"], 10)
    assert res.status_code == 403 and res.json()["error"]["code"] == "KYC_REQUIRED"


@pytest.mark.asyncio
async def test_withdraw_requires_idempotency_key(client, db, monkeypatch):
    _configure_crypto(monkeypatch)
    t = await _verified(client, db, "key@w.com")
    _fund(db, _uid(db, "key@w.com"), 100)
    res = await _withdraw(client, t, 10, key=None)
    assert res.status_code == 400 and res.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


@pytest.mark.asyncio
async def test_503_when_rail_unconfigured(client, db):
    t = await _verified(client, db, "noconf@w.com")
    _fund(db, _uid(db, "noconf@w.com"), 100)
    res = await _withdraw(client, t, 10, method="crypto")
    assert res.status_code == 503 and res.json()["error"]["code"] == "PAYOUTS_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_bank_requires_connect_ready(client, db, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_t", raising=False)
    t = await _verified(client, db, "nobank@w.com")
    _fund(db, _uid(db, "nobank@w.com"), 100)
    res = await _withdraw(client, t, 10, method="bank", address=None)
    assert res.status_code == 409 and res.json()["error"]["code"] == "CONNECT_NOT_READY"


# --- money-out safety ------------------------------------------------------- #
@pytest.mark.asyncio
async def test_over_balance_rejected(client, db, monkeypatch):
    _configure_crypto(monkeypatch)
    t = await _verified(client, db, "over@w.com")
    uid = _uid(db, "over@w.com")
    _fund(db, uid, 50)
    res = await _withdraw(client, t, 100)
    assert res.status_code == 422 and res.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
    assert _bal(db, uid) == 50
    assert db("SELECT count(*) FROM withdrawals WHERE user_id=:i", i=uid)[0][0] == 0
    _assert_balance_invariant(db, uid)


@pytest.mark.asyncio
async def test_exact_balance_ok_and_holds(client, db, monkeypatch):
    _configure_crypto(monkeypatch)
    t = await _verified(client, db, "exact@w.com")
    uid = _uid(db, "exact@w.com")
    _fund(db, uid, 100)
    res = await _withdraw(client, t, 100)
    assert res.status_code == 200 and res.json()["status"] == "approved"
    assert _bal(db, uid) == 0  # debited to hold
    assert _pending(db, uid) == 100  # mirrored in flight
    _assert_balance_invariant(db, uid)
    _assert_pending_invariant(db, uid)


@pytest.mark.asyncio
async def test_concurrent_double_withdraw_cannot_double_spend(client, db, monkeypatch):
    _configure_crypto(monkeypatch)
    t = await _verified(client, db, "race@w.com")
    uid = _uid(db, "race@w.com")
    _fund(db, uid, 100)
    a, b = await asyncio.gather(_withdraw(client, t, 100), _withdraw(client, t, 100))
    codes = sorted([a.status_code, b.status_code])
    assert codes == [200, 422], f"{a.status_code}/{a.text} | {b.status_code}/{b.text}"
    assert _bal(db, uid) == 0  # only ONE hold took the balance
    assert db("SELECT count(*) FROM withdrawals WHERE user_id=:i", i=uid)[0][0] == 1
    _assert_balance_invariant(db, uid)
    _assert_pending_invariant(db, uid)


@pytest.mark.asyncio
async def test_idempotency_replay_one_hold(client, db, monkeypatch):
    _configure_crypto(monkeypatch)
    t = await _verified(client, db, "idem@w.com")
    uid = _uid(db, "idem@w.com")
    _fund(db, uid, 100)
    r1 = await _withdraw(client, t, 40, key="dup")
    r2 = await _withdraw(client, t, 40, key="dup")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["withdrawal_id"] == r2.json()["withdrawal_id"]
    assert db("SELECT count(*) FROM withdrawals WHERE idempotency_key='dup'")[0][0] == 1
    assert _bal(db, uid) == 60  # debited once
    _assert_balance_invariant(db, uid)


@pytest.mark.asyncio
async def test_atomic_rollback_on_hold_failure(client, db, monkeypatch):
    _configure_crypto(monkeypatch)
    from app.services import wallet_service

    async def boom(**kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(wallet_service, "hold_for_withdrawal", boom)
    t = await _verified(client, db, "atom@w.com")
    uid = _uid(db, "atom@w.com")
    _fund(db, uid, 100)
    res = await _withdraw(client, t, 50)
    assert res.status_code >= 500
    # no withdrawal row, balance intact
    assert db("SELECT count(*) FROM withdrawals WHERE user_id=:i", i=uid)[0][0] == 0
    assert _bal(db, uid) == 100
    _assert_balance_invariant(db, uid)


# --- threshold + review ----------------------------------------------------- #
@pytest.mark.asyncio
async def test_auto_approve_under_limit_vs_review_over(client, db, monkeypatch):
    _configure_crypto(monkeypatch)
    t = await _verified(client, db, "thr@w.com")
    uid = _uid(db, "thr@w.com")
    _fund(db, uid, 20000)
    under = await _withdraw(client, t, 5000)  # == limit -> auto
    over = await _withdraw(client, t, 6000)  # > limit -> review
    assert under.json()["status"] == "approved"
    assert over.json()["status"] == "pending_review"
    # both held
    assert _pending(db, uid) == 11000
    assert _bal(db, uid) == 9000
    _assert_balance_invariant(db, uid)
    _assert_pending_invariant(db, uid)


@pytest.mark.asyncio
async def test_rejected_review_releases_funds(client, db, monkeypatch):
    _configure_crypto(monkeypatch)
    admin = await _admin(client, db, "adm1@w.com")
    t = await _verified(client, db, "rej@w.com")
    uid = _uid(db, "rej@w.com")
    _fund(db, uid, 10000)
    res = await _withdraw(client, t, 6000)
    wid = res.json()["withdrawal_id"]
    assert _bal(db, uid) == 4000 and _pending(db, uid) == 6000
    rej = await client.post(
        f"/api/v1/admin/withdrawals/{wid}/reject",
        json={"reason": "no"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert rej.status_code == 200 and rej.json()["status"] == "rejected"
    assert _bal(db, uid) == 10000 and _pending(db, uid) == 0  # released
    _assert_balance_invariant(db, uid)
    _assert_pending_invariant(db, uid)


# --- execute + settle / fail ------------------------------------------------ #
@pytest.mark.asyncio
async def test_execute_then_webhook_completes_crypto(client, db, monkeypatch):
    _configure_crypto(monkeypatch)
    admin = await _admin(client, db, "adm2@w.com")
    t = await _verified(client, db, "done@w.com")
    uid = _uid(db, "done@w.com")
    _fund(db, uid, 100)
    wid = (await _withdraw(client, t, 100)).json()["withdrawal_id"]
    assert (await _execute(client, admin)).json()["submitted"] >= 1
    assert db("SELECT status FROM withdrawals WHERE id=:i", i=wid)[0][0] == "processing"
    ppid = db("SELECT provider_payout_id FROM withdrawals WHERE id=:i", i=wid)[0][0]

    r = await _signed_nowp(client, {"id": ppid, "unique_external_id": wid, "status": "finished"})
    assert r.json()["result"] == "completed"
    assert db("SELECT status FROM withdrawals WHERE id=:i", i=wid)[0][0] == "completed"
    assert _bal(db, uid) == 0 and _pending(db, uid) == 0  # money gone, hold cleared
    # replay the same IPN -> deduped, no change
    r2 = await _signed_nowp(client, {"id": ppid, "unique_external_id": wid, "status": "finished"})
    assert r2.json()["status"] == "duplicate"
    _assert_balance_invariant(db, uid)
    _assert_pending_invariant(db, uid)


@pytest.mark.asyncio
async def test_failed_payout_returns_funds(client, db, monkeypatch):
    _configure_crypto(monkeypatch)
    admin = await _admin(client, db, "adm3@w.com")
    t = await _verified(client, db, "fail@w.com")
    uid = _uid(db, "fail@w.com")
    _fund(db, uid, 100)
    wid = (await _withdraw(client, t, 100)).json()["withdrawal_id"]
    await _execute(client, admin)
    ppid = db("SELECT provider_payout_id FROM withdrawals WHERE id=:i", i=wid)[0][0]
    r = await _signed_nowp(client, {"id": ppid, "unique_external_id": wid, "status": "failed"})
    assert r.json()["result"] == "failed"
    assert db("SELECT status FROM withdrawals WHERE id=:i", i=wid)[0][0] == "failed"
    assert _bal(db, uid) == 100 and _pending(db, uid) == 0  # returned to wallet
    _assert_balance_invariant(db, uid)
    _assert_pending_invariant(db, uid)


@pytest.mark.asyncio
async def test_execute_submit_failure_releases(client, db, monkeypatch):
    _configure_crypto(monkeypatch)
    admin = await _admin(client, db, "adm4@w.com")
    t = await _verified(client, db, "subfail@w.com")
    uid = _uid(db, "subfail@w.com")
    _fund(db, uid, 100)
    wid = (await _withdraw(client, t, 100)).json()["withdrawal_id"]

    from app.core.errors import AppError

    async def boom(**kw):
        raise AppError("PAYOUT_PROVIDER_ERROR", "provider down", status_code=502)

    monkeypatch.setattr(nowp, "create_payout", boom)
    await _execute(client, admin)
    assert db("SELECT status FROM withdrawals WHERE id=:i", i=wid)[0][0] == "failed"
    assert _bal(db, uid) == 100  # released
    _assert_balance_invariant(db, uid)


@pytest.mark.asyncio
async def test_bank_payout_completes_via_stripe_then_returns(client, db, monkeypatch):
    admin = await _admin(client, db, "adm5@w.com")
    t = await _verified(client, db, "bank@w.com")
    uid = _uid(db, "bank@w.com")
    _configure_bank(monkeypatch, db, uid)
    _fund(db, uid, 100)
    wid = (await _withdraw(client, t, 100, method="bank", address=None)).json()["withdrawal_id"]
    await _execute(client, admin)
    ppid = db("SELECT provider_payout_id FROM withdrawals WHERE id=:i", i=wid)[0][0]
    # settle
    settled = await _signed_stripe(
        client,
        {
            "id": "evt_paid",
            "type": "transfer.paid",
            "data": {"object": {"id": ppid, "metadata": {"withdrawal_id": wid}}},
        },
    )
    assert settled.json()["result"] == "completed"
    assert _bal(db, uid) == 0
    # later returned -> funds back
    returned = await _signed_stripe(
        client,
        {
            "id": "evt_ret",
            "type": "payout.returned",
            "data": {"object": {"id": ppid, "metadata": {"withdrawal_id": wid}}},
        },
    )
    assert returned.json()["result"] == "returned"
    assert db("SELECT status FROM withdrawals WHERE id=:i", i=wid)[0][0] == "returned"
    assert _bal(db, uid) == 100
    _assert_balance_invariant(db, uid)


@pytest.mark.asyncio
async def test_reconcile_settles_stuck_processing(client, db, monkeypatch):
    _configure_crypto(monkeypatch)
    admin = await _admin(client, db, "adm6@w.com")
    t = await _verified(client, db, "stuck@w.com")
    uid = _uid(db, "stuck@w.com")
    _fund(db, uid, 100)
    wid = (await _withdraw(client, t, 100)).json()["withdrawal_id"]
    await _execute(client, admin)
    # webhook never arrived; age the row past the reconcile window
    db("UPDATE withdrawals SET updated_at = now() - interval '2 days' WHERE id=:i", i=wid)

    async def settled(_ppid):
        return "settled"

    monkeypatch.setattr(nowp, "get_payout_status", settled)
    r = await client.post(
        "/api/v1/admin/withdrawals/reconcile", headers={"Authorization": f"Bearer {admin}"}
    )
    assert r.json()["reconciled"] == 1
    assert db("SELECT status FROM withdrawals WHERE id=:i", i=wid)[0][0] == "completed"
    assert _pending(db, uid) == 0
    _assert_balance_invariant(db, uid)


# --- admin gating ----------------------------------------------------------- #
@pytest.mark.asyncio
async def test_admin_endpoints_require_admin(client, db):
    assert (await client.post("/api/v1/admin/withdrawals/execute")).status_code == 401
    inv = await _verified(client, db, "notadmin@w.com")
    r = await client.post(
        "/api/v1/admin/withdrawals/execute", headers={"Authorization": f"Bearer {inv}"}
    )
    assert r.status_code == 403
