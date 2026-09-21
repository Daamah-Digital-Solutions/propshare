"""Per-method payout mode (owner request: automatic bank payouts via Stripe, crypto still manual).

What must hold:
  * ``payout_auto_methods='bank'`` makes bank withdrawals automatic **while the global
    ``manual_payouts_enabled`` stays true**, so crypto keeps waiting for an admin.
  * An automatic, under-the-limit withdrawal is submitted to the provider by the request
    itself (background task) — the customer does not wait for the executor cron.
  * Over the auto-approve limit still goes to review, even on the automatic rail.
  * A method listed as automatic whose provider is NOT configured falls back to manual
    instead of 503-ing the customer.
  * ``GET /wallet/payout-config`` reports what the wallet UI must render.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.config import get_settings
from app.services.integrations.payments import PayoutResult
from app.services.integrations.payments import stripe_gateway as stripe

PW = "Passw0rd!23"


async def _verified(client, db, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "W"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    return r.json()["access_token"]


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


def _setting(db, key: str, value: str) -> None:
    db(
        "INSERT INTO platform_settings (key, value) VALUES (:k,:v) "
        "ON CONFLICT (key) DO UPDATE SET value=:v",
        k=key,
        v=value,
    )


def _stripe_ready(monkeypatch, db, uid: str):
    """Live-ish Stripe Connect: keys set, the user finished onboarding, transfers mocked."""
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


def _crypto_unconfigured(monkeypatch):
    s = get_settings()
    for attr in ("nowpayments_api_key", "nowpayments_email", "nowpayments_password"):
        monkeypatch.setattr(s, attr, "", raising=False)


async def _withdraw(client, token, amount, method, **body_extra):
    body = {"amount": amount, "method": method, **body_extra}
    return await client.post(
        "/api/v1/wallet/withdrawals",
        json=body,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
    )


def _row(db, wid: str):
    return db(
        "SELECT status, provider, provider_payout_id FROM withdrawals WHERE id=:i", i=wid
    )[0]


# --- the owner's shape: bank automatic, crypto manual ----------------------- #
@pytest.mark.asyncio
async def test_bank_auto_while_crypto_stays_manual(client, db, monkeypatch):
    _setting(db, "manual_payouts_enabled", "true")  # global default untouched
    _setting(db, "payout_auto_methods", "bank")
    _crypto_unconfigured(monkeypatch)
    tok = await _verified(client, db, "mix@w.com")
    uid = _uid(db, "mix@w.com")
    _fund(db, uid, 1000)
    _stripe_ready(monkeypatch, db, uid)

    # bank -> automatic: approved on request, then submitted by the background task
    r = await _withdraw(client, tok, 100, "bank")
    assert r.status_code == 200, r.text
    status, provider, payout_id = _row(db, r.json()["withdrawal_id"])
    assert provider == "stripe"
    assert status == "processing", "the request itself should have submitted the payout"
    assert payout_id and payout_id.startswith("tr_")

    # crypto -> still the admin queue, and NOT a 503 even though NOWPayments is unconfigured
    db(
        "INSERT INTO user_crypto_wallets (user_id, network, address, is_default) "
        "VALUES (:u,'USDT-TRC20','Taddr',true)",
        u=uid,
    )
    r2 = await _withdraw(client, tok, 50, "crypto")
    assert r2.status_code == 200, r2.text
    status2, provider2, payout_id2 = _row(db, r2.json()["withdrawal_id"])
    assert (status2, provider2, payout_id2) == ("pending_review", "manual", None)


@pytest.mark.asyncio
async def test_auto_bank_over_limit_still_reviewed(client, db, monkeypatch):
    _setting(db, "manual_payouts_enabled", "true")
    _setting(db, "payout_auto_methods", "bank")
    _setting(db, "withdrawal_auto_approve_limit", "200")
    tok = await _verified(client, db, "big@w.com")
    uid = _uid(db, "big@w.com")
    _fund(db, uid, 1000)
    _stripe_ready(monkeypatch, db, uid)

    r = await _withdraw(client, tok, 500, "bank")
    assert r.status_code == 200, r.text
    status, provider, payout_id = _row(db, r.json()["withdrawal_id"])
    assert (status, provider, payout_id) == ("pending_review", "stripe", None)
    # the customer is told it is under review, not that it was sent
    assert db(
        "SELECT title FROM notifications WHERE user_id=:u ORDER BY created_at DESC LIMIT 1", u=uid
    )[0][0] == "Withdrawal under review"


@pytest.mark.asyncio
async def test_auto_bank_requires_finished_stripe_onboarding(client, db, monkeypatch):
    """No Connect account -> an honest 409, never a silent manual fallback that the UI
    would describe as instant."""
    _setting(db, "manual_payouts_enabled", "true")
    _setting(db, "payout_auto_methods", "bank")
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_t", raising=False)
    tok = await _verified(client, db, "nolink@w.com")
    _fund(db, _uid(db, "nolink@w.com"), 500)

    r = await _withdraw(client, tok, 100, "bank")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONNECT_NOT_READY"


@pytest.mark.asyncio
async def test_listed_but_unconfigured_provider_falls_back_to_manual(client, db, monkeypatch):
    """Turning a rail on before its provider exists must not break withdrawals."""
    _setting(db, "manual_payouts_enabled", "true")
    _setting(db, "payout_auto_methods", "bank,crypto")
    _crypto_unconfigured(monkeypatch)
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "", raising=False)  # Stripe not configured either
    monkeypatch.setattr(s, "stripe_webhook_secret", "", raising=False)
    tok = await _verified(client, db, "fallback@w.com")
    uid = _uid(db, "fallback@w.com")
    _fund(db, uid, 500)
    db(
        "INSERT INTO user_bank_accounts (user_id, bank_name, account_holder, iban, is_default) "
        "VALUES (:u,'B','H','IBAN123',true)",
        u=uid,
    )

    r = await _withdraw(client, tok, 100, "bank")
    assert r.status_code == 200, r.text
    status, provider, _ = _row(db, r.json()["withdrawal_id"])
    assert (status, provider) == ("pending_review", "manual")


# --- what the wallet UI reads ---------------------------------------------- #
@pytest.mark.asyncio
async def test_payout_config_reports_each_method(client, db, monkeypatch):
    _setting(db, "manual_payouts_enabled", "true")
    _setting(db, "payout_auto_methods", "bank")
    _setting(db, "withdrawal_auto_approve_limit", "5000")
    _crypto_unconfigured(monkeypatch)
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_t", raising=False)
    tok = await _verified(client, db, "cfg@w.com")

    r = await client.get(
        "/api/v1/wallet/payout-config", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["auto_approve_limit"] == "5000"
    assert body["methods"]["bank"] == {
        "mode": "auto",
        "connect_required": True,
        "requested_auto": True,
        "provider_configured": True,
    }
    assert body["methods"]["crypto"]["mode"] == "manual"
    assert body["methods"]["crypto"]["connect_required"] is False


@pytest.mark.asyncio
async def test_payout_config_requires_auth(client, db):
    assert (await client.get("/api/v1/wallet/payout-config")).status_code == 401


# --- settings guard --------------------------------------------------------- #
@pytest.mark.asyncio
async def test_unknown_method_rejected_by_settings_validation(client, db):
    from app.core.errors import AppError
    from app.services.settings_service import validate_setting

    validate_setting("payout_auto_methods", "bank,crypto")
    validate_setting("payout_auto_methods", "")
    with pytest.raises(AppError):
        validate_setting("payout_auto_methods", "paypal")


# --- the platform's own Stripe balance can be short --------------------------- #
@pytest.mark.asyncio
async def test_stripe_balance_shortfall_queues_for_admin_instead_of_failing(
    client, db, monkeypatch
):
    """Deposits taken by bank/crypto never reach the Stripe balance, so a transfer can be
    refused with balance_insufficient. The customer must not see a failed withdrawal: the
    hold stays and an admin settles it."""
    from app.core.errors import AppError

    _setting(db, "manual_payouts_enabled", "true")
    _setting(db, "payout_auto_methods", "bank")
    tok = await _verified(client, db, "short@w.com")
    uid = _uid(db, "short@w.com")
    _fund(db, uid, 500)
    _stripe_ready(monkeypatch, db, uid)

    async def broke(**kw):
        raise AppError(
            "PAYOUT_PROVIDER_ERROR",
            "Stripe error (400).",
            status_code=502,
            details={"body": '{"error":{"code":"balance_insufficient"}}'},
        )

    monkeypatch.setattr(stripe, "create_payout", broke)

    r = await _withdraw(client, tok, 100, "bank")
    assert r.status_code == 200, r.text
    wid = r.json()["withdrawal_id"]
    status, provider, payout_id = _row(db, wid)
    assert (status, provider, payout_id) == ("pending_review", "stripe", None)
    # the hold is intact: spendable down, pending up, nothing lost
    bal, pend = db("SELECT balance, pending_balance FROM wallets WHERE user_id=:u", u=uid)[0]
    assert (float(bal), float(pend)) == (400.0, 100.0)
    assert db(
        "SELECT action FROM audit_log WHERE entity_id=:i ORDER BY created_at DESC LIMIT 1", i=wid
    )[0][0] == "withdrawal.submit_deferred"


@pytest.mark.asyncio
async def test_other_provider_errors_still_return_the_money(client, db, monkeypatch):
    from app.core.errors import AppError

    _setting(db, "manual_payouts_enabled", "true")
    _setting(db, "payout_auto_methods", "bank")
    tok = await _verified(client, db, "err@w.com")
    uid = _uid(db, "err@w.com")
    _fund(db, uid, 500)
    _stripe_ready(monkeypatch, db, uid)

    async def boom(**kw):
        raise AppError("PAYOUT_PROVIDER_ERROR", "Stripe error (500).", status_code=502)

    monkeypatch.setattr(stripe, "create_payout", boom)
    r = await _withdraw(client, tok, 100, "bank")
    wid = r.json()["withdrawal_id"]
    assert _row(db, wid)[0] == "failed"
    bal, pend = db("SELECT balance, pending_balance FROM wallets WHERE user_id=:u", u=uid)[0]
    assert (float(bal), float(pend)) == (500.0, 0.0)  # released back
