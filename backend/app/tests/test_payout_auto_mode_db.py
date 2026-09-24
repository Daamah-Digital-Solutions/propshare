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
  * Stripe's Connect endpoint is verified with its own secret, and nothing it reports about
    an investor's own payout ever moves money in our ledger.
"""

from __future__ import annotations

import decimal
import hashlib
import hmac
import json
import uuid

import pytest

from app.core.config import get_settings
from app.core.errors import AppError
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
        # like the real gateway: a Stripe transfer is final once accepted
        return PayoutResult(
            provider_payout_id="tr_" + str(kw["withdrawal_id"])[:8], status="settled"
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

    # bank -> automatic: approved on request, then submitted by the background task, and a
    # Stripe transfer is final as soon as Stripe accepts it
    r = await _withdraw(client, tok, 100, "bank")
    assert r.status_code == 200, r.text
    status, provider, payout_id = _row(db, r.json()["withdrawal_id"])
    assert provider == "stripe"
    assert status == "completed", "the request itself should have submitted the payout"
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


# --- Instant Payouts (money in minutes, US debit cards) ---------------------- #
def _instant_on(db, *, fee_pct="1.0", max_amount="9999"):
    _setting(db, "manual_payouts_enabled", "true")
    _setting(db, "payout_auto_methods", "bank")
    _setting(db, "payout_instant_enabled", "true")
    _setting(db, "payout_instant_fee_pct", fee_pct)
    _setting(db, "payout_instant_max", max_amount)


def _instant_card(monkeypatch, *, eligible=True, available="10000"):
    """A connected account with (or without) a debit card Stripe will push to instantly."""
    calls: dict = {}

    async def fake_destination(account_id):
        return "card_x" if eligible else None

    async def fake_available(account_id, currency):
        import decimal as _d

        return _d.Decimal(available)

    async def fake_instant(**kw):
        calls.update(kw)
        return PayoutResult(provider_payout_id="po_instant", status="processing")

    monkeypatch.setattr(stripe, "instant_destination", fake_destination)
    monkeypatch.setattr(stripe, "instant_available", fake_available)
    monkeypatch.setattr(stripe, "create_instant_payout", fake_instant)
    return calls


@pytest.mark.asyncio
async def test_instant_deducts_fee_and_pushes_to_the_card(client, db, monkeypatch):
    _instant_on(db)
    tok = await _verified(client, db, "fast@w.com")
    uid = _uid(db, "fast@w.com")
    _fund(db, uid, 1000)
    _stripe_ready(monkeypatch, db, uid)
    calls = _instant_card(monkeypatch)

    r = await _withdraw(client, tok, 200, "bank", speed="instant")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["speed"], body["fee"], body["net_amount"]) == ("instant", "2.00", "198.00")

    # the transfer and the instant payout both carry the NET amount
    assert calls["amount"] == decimal.Decimal("198.00")
    assert calls["destination"] == "card_x"
    speed, fee = db("SELECT speed, fee FROM withdrawals WHERE id=:i", i=body["withdrawal_id"])[0]
    assert (speed, float(fee)) == ("instant", 2.0)
    # the wallet was debited the full amount once; the fee is ours, not a second ledger row
    bal, pend = db("SELECT balance, pending_balance FROM wallets WHERE user_id=:u", u=uid)[0]
    assert (float(bal), float(pend)) == (800.0, 0.0)  # completed: the hold is cleared
    assert float(db("SELECT SUM(amount) FROM transactions WHERE user_id=:u", u=uid)[0][0]) == 800.0
    title, message = db(
        "SELECT title, message FROM notifications WHERE user_id=:u ORDER BY created_at DESC "
        "LIMIT 1",
        u=uid,
    )[0]
    assert title == "Withdrawal sent" and "30 minutes" in message and "$198.00" in message


@pytest.mark.asyncio
async def test_instant_leg_failure_downgrades_instead_of_losing_the_money(client, db, monkeypatch):
    """The transfer already made the money the investor's, so a card problem must only cost
    them the speed."""
    _instant_on(db)
    tok = await _verified(client, db, "down@w.com")
    uid = _uid(db, "down@w.com")
    _fund(db, uid, 1000)
    _stripe_ready(monkeypatch, db, uid)
    _instant_card(monkeypatch)  # eligible at request time

    seen = {"n": 0}

    async def gone_after_first_check(account_id):
        # eligible when the request validates it, gone by the time we push
        seen["n"] += 1
        return "card_x" if seen["n"] == 1 else None

    monkeypatch.setattr(stripe, "instant_destination", gone_after_first_check)

    r = await _withdraw(client, tok, 200, "bank", speed="instant")
    assert r.status_code == 200, r.text
    wid = r.json()["withdrawal_id"]
    status, speed, reason = db(
        "SELECT status, speed, failure_reason FROM withdrawals WHERE id=:i", i=wid
    )[0]
    assert status == "completed"  # the transfer made it theirs; only the speed changed
    assert speed == "standard"
    assert "standard schedule" in reason
    bal, pend = db("SELECT balance, pending_balance FROM wallets WHERE user_id=:u", u=uid)[0]
    assert (float(bal), float(pend)) == (800.0, 0.0)  # nothing returned, nothing lost


@pytest.mark.asyncio
async def test_instant_refused_without_an_eligible_card(client, db, monkeypatch):
    _instant_on(db)
    tok = await _verified(client, db, "nocard@w.com")
    uid = _uid(db, "nocard@w.com")
    _fund(db, uid, 1000)
    _stripe_ready(monkeypatch, db, uid)
    _instant_card(monkeypatch, eligible=False)

    r = await _withdraw(client, tok, 200, "bank", speed="instant")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INSTANT_NOT_AVAILABLE"
    assert r.json()["error"]["details"]["reason"] == "NO_ELIGIBLE_CARD"
    # refused BEFORE any hold
    assert db("SELECT COUNT(*) FROM withdrawals WHERE user_id=:u", u=uid)[0][0] == 0
    assert float(db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0]) == 1000.0


@pytest.mark.asyncio
async def test_instant_over_stripes_per_payout_cap(client, db, monkeypatch):
    _instant_on(db, max_amount="9999")
    tok = await _verified(client, db, "cap@w.com")
    uid = _uid(db, "cap@w.com")
    _fund(db, uid, 20000)
    _setting(db, "withdrawal_auto_approve_limit", "50000")
    _stripe_ready(monkeypatch, db, uid)
    _instant_card(monkeypatch)

    r = await _withdraw(client, tok, 12000, "bank", speed="instant")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INSTANT_LIMIT_EXCEEDED"
    # the same amount goes through fine at standard speed
    r2 = await _withdraw(client, tok, 12000, "bank")
    assert r2.status_code == 200, r2.text
    assert r2.json()["fee"] == "0.00"


@pytest.mark.asyncio
async def test_instant_refused_when_switched_off_or_rail_is_manual(client, db, monkeypatch):
    _setting(db, "manual_payouts_enabled", "true")
    _setting(db, "payout_auto_methods", "")  # bank is manual
    _setting(db, "payout_instant_enabled", "true")
    tok = await _verified(client, db, "off@w.com")
    uid = _uid(db, "off@w.com")
    _fund(db, uid, 1000)
    db(
        "INSERT INTO user_bank_accounts (user_id, bank_name, account_holder, iban, is_default) "
        "VALUES (:u,'B','H','IBAN9',true)",
        u=uid,
    )
    r = await _withdraw(client, tok, 100, "bank", speed="instant")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INSTANT_NOT_AVAILABLE"


@pytest.mark.asyncio
async def test_payout_config_publishes_instant_readiness(client, db, monkeypatch):
    _instant_on(db, fee_pct="1.5", max_amount="9999")
    tok = await _verified(client, db, "ready@w.com")
    uid = _uid(db, "ready@w.com")
    _stripe_ready(monkeypatch, db, uid)
    _instant_card(monkeypatch)

    r = await client.get(
        "/api/v1/wallet/payout-config", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 200, r.text
    inst = r.json()["instant"]
    assert inst["available"] is True
    assert (inst["fee_pct"], inst["max_amount"], inst["reason"]) == ("1.5", "9999", None)


@pytest.mark.asyncio
async def test_instant_fee_rounds_up_to_the_cent(client, db, monkeypatch):
    """Stripe bills the platform its own percentage; our fee may never round down below it."""
    from app.services.withdrawal_service import instant_fee_for

    assert instant_fee_for(decimal.Decimal("10.01"), decimal.Decimal("1.0")) == decimal.Decimal(
        "0.11"
    )
    assert instant_fee_for(decimal.Decimal("100"), decimal.Decimal("1.5")) == decimal.Decimal(
        "1.50"
    )


# --- Stripe's "Connected accounts" webhook endpoint -------------------------- #
def _connect_secret(monkeypatch):
    """Production shape: the Connect endpoint has its own secret, unlike the deposits one."""
    monkeypatch.setattr(
        get_settings(), "stripe_connect_webhook_secret", "whsec_connect", raising=False
    )


async def _connect_event(client, event: dict, secret: str = "whsec_connect"):
    body = json.dumps(event).encode()
    ts = "1700000000"
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return await client.post(
        "/api/v1/payments/webhooks/stripe-payouts",
        content=body,
        headers={"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"},
    )


def _last_title(db, uid):
    return db(
        "SELECT title FROM notifications WHERE user_id=:u ORDER BY created_at DESC LIMIT 1", u=uid
    )[0][0]


@pytest.mark.asyncio
async def test_failed_card_payout_leaves_the_money_where_stripe_put_it(client, db, monkeypatch):
    """The instant payout leaves the investor's Stripe account after our transfer. When the card
    refuses it, Stripe returns the funds to THEIR Stripe balance, so crediting the wallet would
    pay them twice: the withdrawal only drops to the standard schedule."""
    _instant_on(db)
    tok = await _verified(client, db, "cardfail@w.com")
    uid = _uid(db, "cardfail@w.com")
    _fund(db, uid, 1000)
    _stripe_ready(monkeypatch, db, uid)
    _instant_card(monkeypatch)
    _connect_secret(monkeypatch)
    wid = (await _withdraw(client, tok, 200, "bank", speed="instant")).json()["withdrawal_id"]
    assert _row(db, wid)[0] == "completed"

    event = {
        "id": "evt_card_failed",
        "type": "payout.failed",
        "account": "acct_x",
        "data": {
            "object": {
                "id": "po_instant",
                "metadata": {"withdrawal_id": wid},
                "failure_code": "could_not_process",
            }
        },
    }
    r = await _connect_event(client, event)
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "processed", "result": "instant_failed"}
    status, speed, reason = db(
        "SELECT status, speed, failure_reason FROM withdrawals WHERE id=:i", i=wid
    )[0]
    assert (status, speed) == ("completed", "standard")
    assert "standard schedule" in reason
    bal, pend = db("SELECT balance, pending_balance FROM wallets WHERE user_id=:u", u=uid)[0]
    assert (float(bal), float(pend)) == (800.0, 0.0)  # nothing credited back
    assert _last_title(db, uid) == "Instant payout did not go through"


@pytest.mark.asyncio
async def test_a_payout_only_matches_the_investors_own_stripe_account(client, db, monkeypatch):
    _instant_on(db)
    tok = await _verified(client, db, "own@w.com")
    uid = _uid(db, "own@w.com")
    _fund(db, uid, 1000)
    _stripe_ready(monkeypatch, db, uid)
    _instant_card(monkeypatch)
    _connect_secret(monkeypatch)
    wid = (await _withdraw(client, tok, 200, "bank", speed="instant")).json()["withdrawal_id"]

    event = {  # some other Stripe account naming this withdrawal in its metadata
        "id": "evt_foreign",
        "type": "payout.failed",
        "account": "acct_someone_else",
        "data": {"object": {"id": "po_x", "metadata": {"withdrawal_id": wid}}},
    }
    r = await _connect_event(client, event)
    assert r.json()["status"] == "ignored_unknown_withdrawal"
    assert db("SELECT speed FROM withdrawals WHERE id=:i", i=wid)[0][0] == "instant"


@pytest.mark.asyncio
@pytest.mark.parametrize("etype", ["payout.paid", "payout.failed"])
async def test_a_row_still_processing_completes_on_its_card_payout(
    client, db, monkeypatch, etype
):
    """Withdrawals submitted before a transfer counted as final can still be 'processing'.
    Whatever their card payout did, the transfer had already paid them: never a refund."""
    _instant_on(db)
    tok = await _verified(client, db, "legacy@w.com")
    uid = _uid(db, "legacy@w.com")
    _fund(db, uid, 1000)
    _stripe_ready(monkeypatch, db, uid)
    _instant_card(monkeypatch)
    _connect_secret(monkeypatch)

    async def old_style(**kw):
        return PayoutResult(provider_payout_id="tr_old", status="processing")

    monkeypatch.setattr(stripe, "create_payout", old_style)
    wid = (await _withdraw(client, tok, 200, "bank", speed="instant")).json()["withdrawal_id"]
    assert _row(db, wid)[0] == "processing"

    event = {
        "id": f"evt_{etype}",
        "type": etype,
        "account": "acct_x",
        "data": {"object": {"id": "po_instant", "metadata": {"withdrawal_id": wid}}},
    }
    assert (await _connect_event(client, event)).json()["result"] == "completed"
    assert _row(db, wid)[0] == "completed"
    bal, pend = db("SELECT balance, pending_balance FROM wallets WHERE user_id=:u", u=uid)[0]
    assert (float(bal), float(pend)) == (800.0, 0.0)
    speed = db("SELECT speed FROM withdrawals WHERE id=:i", i=wid)[0][0]
    assert speed == ("instant" if etype == "payout.paid" else "standard")


@pytest.mark.asyncio
async def test_finished_onboarding_arrives_on_the_connect_endpoint(client, db, monkeypatch):
    """account.updated comes from connected accounts, signed with the Connect secret; a
    signature made with any other secret is refused."""
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_main", raising=False)
    _connect_secret(monkeypatch)
    await _verified(client, db, "onb@w.com")
    uid = _uid(db, "onb@w.com")
    db(
        "INSERT INTO connect_accounts (user_id, stripe_account_id, payouts_enabled, "
        "details_submitted, status) VALUES (:u,'acct_new',false,false,'pending')",
        u=uid,
    )

    async def live(account_id):
        assert account_id == "acct_new"
        return {"payouts_enabled": True, "details_submitted": True}

    monkeypatch.setattr(stripe, "get_account_status", live)
    event = {
        "id": "evt_acct",
        "type": "account.updated",
        "account": "acct_new",
        "data": {"object": {"id": "acct_new"}},
    }
    assert (await _connect_event(client, event, secret="whsec_wrong")).status_code == 401
    r = await _connect_event(client, event)
    assert r.json() == {"status": "account_updated"}
    row = db("SELECT payouts_enabled, status FROM connect_accounts WHERE user_id=:u", u=uid)[0]
    assert row == (True, "verified")


@pytest.mark.asyncio
async def test_connect_status_asks_stripe_until_the_bank_is_linked(client, db, monkeypatch):
    """The investor lands back on the wallet straight from Stripe, usually before the webhook.
    The status read asks Stripe itself; a Stripe error keeps the stored state instead of
    failing the page, and once linked it stops asking."""
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_main", raising=False)
    tok = await _verified(client, db, "back@w.com")
    uid = _uid(db, "back@w.com")
    db(
        "INSERT INTO connect_accounts (user_id, stripe_account_id, payouts_enabled, "
        "details_submitted, status) VALUES (:u,'acct_back',false,false,'pending')",
        u=uid,
    )
    auth = {"Authorization": f"Bearer {tok}"}

    async def down(account_id):
        raise AppError("PAYOUT_PROVIDER_ERROR", "Stripe error (500).", status_code=502)

    monkeypatch.setattr(stripe, "get_account_status", down)
    r = await client.get("/api/v1/wallet/connect/status", headers=auth)
    assert r.status_code == 200 and r.json()["payouts_enabled"] is False

    calls = []

    async def linked(account_id):
        calls.append(account_id)
        return {"payouts_enabled": True, "details_submitted": True}

    monkeypatch.setattr(stripe, "get_account_status", linked)
    r = await client.get("/api/v1/wallet/connect/status", headers=auth)
    assert (r.json()["payouts_enabled"], r.json()["status"]) == (True, "verified")
    assert db("SELECT payouts_enabled FROM connect_accounts WHERE user_id=:u", u=uid)[0][0]
    await client.get("/api/v1/wallet/connect/status", headers=auth)
    assert calls == ["acct_back"]  # linked: no more calls to Stripe


@pytest.mark.asyncio
async def test_onboarding_returns_to_the_wallet_tab(client, db, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test", raising=False)
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_main", raising=False)
    tok = await _verified(client, db, "link@w.com")
    seen: dict = {}

    async def new_account(email):
        return "acct_link"

    async def account_link(account_id, *, refresh_url, return_url):
        seen.update(refresh_url=refresh_url, return_url=return_url)
        return "https://connect.stripe.com/setup/e/acct_link/x"

    monkeypatch.setattr(stripe, "create_connected_account", new_account)
    monkeypatch.setattr(stripe, "create_account_link", account_link)
    r = await client.post(
        "/api/v1/wallet/connect/onboard", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 200, r.text
    assert seen["return_url"].endswith("/dashboard?tab=wallet&connect=done")
    assert seen["refresh_url"].endswith("/dashboard?tab=wallet&connect=refresh")
