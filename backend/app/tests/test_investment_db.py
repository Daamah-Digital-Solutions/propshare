"""Phase 5 — DB-backed investment-engine tests (the money gates).

Covers the acceptance bar: wallet-funded atomic purchase, KYC gate, Idempotency-Key
requirement + replay, server-authoritative fees, oversell protection (incl. the
concurrent double-buy-of-the-last-units race and the DB CHECK backstop), atomicity
rollback on insufficient funds, the direct-pay reserve -> webhook-confirm flow,
reservation expiry, late-webhook reconciliation (re-acquire or refund), and the
invariants (units_sold + reserved + available == total; balance == SUM(ledger)).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.services import investment_service
from app.services.integrations.payments import CheckoutResult
from app.services.integrations.payments import stripe_gateway as stripe

PW = "Passw0rd!23"


# --- arrange helpers -------------------------------------------------------- #
async def _verified_user(client, db, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Inv"}
    )
    token = r.json()["access_token"]
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)
    return token


def _uid(db, email: str) -> str:
    return db("SELECT id FROM users WHERE email=:e", e=email)[0][0]


def _seed_property(
    db,
    *,
    unit_price=100,
    total_units=100,
    available=None,
    total_value=None,
    minimum=100,
    status="active",
) -> str:
    pid = str(uuid.uuid4())
    av = total_units if available is None else available
    tv = total_value if total_value is not None else unit_price * total_units
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,total_value,"
        "unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Marina Bay','Dubai','residential','ready-income',:st,:tv,:up,:tu,:av,:mi)",
        id=pid,
        st=status,
        tv=tv,
        up=unit_price,
        tu=total_units,
        av=av,
        mi=minimum,
    )
    return pid


def _fund_wallet(db, uid: str, amount) -> None:
    # Seed the balance via a real ledger row so balance == SUM(ledger) holds from the start.
    db(
        "INSERT INTO transactions (user_id, type, amount, status) "
        "VALUES (:u,'deposit',:a,'completed')",
        u=uid,
        a=amount,
    )
    db("UPDATE wallets SET balance=:a WHERE user_id=:u", a=amount, u=uid)


async def _invest(client, token, pid, amount, method="wallet", key="auto"):
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = str(uuid.uuid4()) if key == "auto" else key
    return await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": amount, "method": method},
        headers=headers,
    )


def _configure_stripe(monkeypatch):
    async def fake_checkout(**kwargs):
        return CheckoutResult(
            provider_payment_id="cs_" + uuid.uuid4().hex[:8],
            checkout_url="https://pay.test/checkout",
            status="pending",
        )

    monkeypatch.setattr(stripe, "is_configured", lambda: True)
    monkeypatch.setattr(stripe, "create_checkout", fake_checkout)
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)


def _stripe_event(payment_id: str, *, cents: int, event_id, paid=True, expired=False):
    if expired:
        return {
            "id": event_id,
            "type": "checkout.session.expired",
            "data": {"object": {"id": "cs_x", "client_reference_id": payment_id}},
        }
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_x",
                "client_reference_id": payment_id,
                "payment_status": "paid" if paid else "unpaid",
                "amount_total": cents,
                "currency": "usd",
            }
        },
    }


async def _post_stripe(client, event: dict):
    body = json.dumps(event).encode()
    ts = "1700000000"
    sig = hmac.new(b"whsec_t", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return await client.post(
        "/api/v1/payments/webhooks/stripe",
        content=body,
        headers={"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"},
    )


def _payment_id_for(db, inv_id: str) -> str:
    return str(db("SELECT id FROM payments WHERE related_investment_id=:i", i=inv_id)[0][0])


# --- invariants ------------------------------------------------------------- #
def _assert_balance_invariant(db, uid: str):
    bal = db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0]
    led = db("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=:i", i=uid)[0][0]
    assert bal == led, f"balance {bal} != ledger {led}"


def _assert_unit_invariant(db, pid: str):
    total, avail = db("SELECT total_units, available_units FROM properties WHERE id=:i", i=pid)[0]
    confirmed = db(
        "SELECT COALESCE(SUM(units),0) FROM ownership_ledger WHERE property_id=:i", i=pid
    )[0][0]
    reserved = db(
        "SELECT COALESCE(SUM(units),0) FROM investments WHERE property_id=:i AND status='pending'",
        i=pid,
    )[0][0]
    assert (
        confirmed + reserved + avail == total
    ), f"confirmed {confirmed} + reserved {reserved} + avail {avail} != total {total}"


# --- gating / validation ---------------------------------------------------- #
@pytest.mark.asyncio
async def test_invest_requires_kyc(client, db):
    r = await client.post(
        "/api/v1/auth/register", json={"email": "nokyc@i.com", "password": PW, "full_name": "N"}
    )
    token = r.json()["access_token"]
    pid = _seed_property(db)
    res = await _invest(client, token, pid, 1000, "wallet")
    assert res.status_code == 403 and res.json()["error"]["code"] == "KYC_REQUIRED"


@pytest.mark.asyncio
async def test_invest_requires_idempotency_key(client, db):
    token = await _verified_user(client, db, "key@i.com")
    pid = _seed_property(db)
    res = await _invest(client, token, pid, 1000, "wallet", key=None)
    assert res.status_code == 400 and res.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


@pytest.mark.asyncio
async def test_amount_below_one_unit_rejected(client, db):
    token = await _verified_user(client, db, "low@i.com")
    pid = _seed_property(db, unit_price=100, minimum=100)
    res = await _invest(client, token, pid, 50, "wallet")
    assert res.status_code == 422 and res.json()["error"]["code"] == "AMOUNT_TOO_LOW"


@pytest.mark.asyncio
async def test_below_minimum_investment_rejected(client, db):
    token = await _verified_user(client, db, "min@i.com")
    pid = _seed_property(db, unit_price=100, minimum=500)
    _fund_wallet(db, _uid(db, "min@i.com"), 10000)
    res = await _invest(client, token, pid, 300, "wallet")  # 3 units = 300 < 500 minimum
    assert res.status_code == 422 and res.json()["error"]["code"] == "AMOUNT_TOO_LOW"


@pytest.mark.asyncio
async def test_invest_blocked_when_property_not_open(client, db):
    token = await _verified_user(client, db, "closed@i.com")
    _fund_wallet(db, _uid(db, "closed@i.com"), 10000)
    pid = _seed_property(db, status="funded")
    res = await _invest(client, token, pid, 1000, "wallet")
    assert res.status_code == 409 and res.json()["error"]["code"] == "PROPERTY_NOT_OPEN"


# --- wallet-funded (atomic) ------------------------------------------------- #
@pytest.mark.asyncio
async def test_wallet_funded_invest_happy_path(client, db):
    token = await _verified_user(client, db, "happy@i.com")
    uid = _uid(db, "happy@i.com")
    _fund_wallet(db, uid, 10000)
    pid = _seed_property(db, unit_price=100, total_units=100, total_value=10000, minimum=100)

    res = await _invest(client, token, pid, 1000, "wallet")
    assert res.status_code == 200, res.text
    body = res.json()
    # server-authoritative math: 10 units * 100 = 1000 subtotal; 2.5% platform fee = 25
    assert body["status"] == "confirmed"
    assert body["units"] == 10
    assert body["amount"] == "1000.00"
    assert body["platform_fee"] == "25.00"
    assert body["total_charged"] == "1025.00"
    assert body["management_fee_rate"] == "1.0"
    assert body["checkout_url"] is None

    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 10000 - 1025
    assert db("SELECT total_invested FROM wallets WHERE user_id=:i", i=uid)[0][0] == 1000
    avail = db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0]
    assert avail == 90
    assert db("SELECT funded_amount FROM properties WHERE id=:i", i=pid)[0][0] == 1000
    assert db("SELECT investors_count FROM properties WHERE id=:i", i=pid)[0][0] == 1
    assert db("SELECT funding_progress FROM properties WHERE id=:i", i=pid)[0][0] == 10
    # itemized ledger: an investment row (-1000) and a fee row (-25)
    assert (
        db("SELECT count(*) FROM transactions WHERE type='investment' AND amount=-1000")[0][0] == 1
    )
    assert db("SELECT count(*) FROM transactions WHERE type='fee' AND amount=-25")[0][0] == 1
    assert db("SELECT units FROM ownership_ledger WHERE property_id=:i", i=pid)[0][0] == 10
    _assert_balance_invariant(db, uid)
    _assert_unit_invariant(db, pid)


@pytest.mark.asyncio
async def test_wallet_insufficient_funds_rolls_back(client, db):
    token = await _verified_user(client, db, "broke@i.com")
    uid = _uid(db, "broke@i.com")
    _fund_wallet(db, uid, 50)  # not enough for a 1000 + fee purchase
    pid = _seed_property(db, unit_price=100, total_units=100)

    res = await _invest(client, token, pid, 1000, "wallet")
    assert res.status_code == 422 and res.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
    # atomicity: nothing moved — no units consumed, no investment row, balance intact
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 100
    assert db("SELECT count(*) FROM investments WHERE property_id=:i", i=pid)[0][0] == 0
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 50
    assert db("SELECT count(*) FROM ownership_ledger WHERE property_id=:i", i=pid)[0][0] == 0
    _assert_balance_invariant(db, uid)


@pytest.mark.asyncio
async def test_idempotency_replay_returns_same_investment(client, db):
    token = await _verified_user(client, db, "idem@i.com")
    uid = _uid(db, "idem@i.com")
    _fund_wallet(db, uid, 10000)
    pid = _seed_property(db, unit_price=100)
    r1 = await _invest(client, token, pid, 1000, "wallet", key="dup-1")
    r2 = await _invest(client, token, pid, 1000, "wallet", key="dup-1")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["investment_id"] == r2.json()["investment_id"]
    assert db("SELECT count(*) FROM investments WHERE idempotency_key='dup-1'")[0][0] == 1
    # debited exactly once
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uid)[0][0] == 10000 - 1025
    _assert_balance_invariant(db, uid)
    _assert_unit_invariant(db, pid)


# --- oversell protection ---------------------------------------------------- #
@pytest.mark.asyncio
async def test_oversell_rejected_when_not_enough_units(client, db):
    token = await _verified_user(client, db, "over@i.com")
    _fund_wallet(db, _uid(db, "over@i.com"), 100000)
    pid = _seed_property(db, unit_price=100, total_units=5, available=5)
    res = await _invest(client, token, pid, 1000, "wallet")  # wants 10 units, only 5 left
    assert res.status_code == 409 and res.json()["error"]["code"] == "INSUFFICIENT_UNITS"
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 5


@pytest.mark.asyncio
async def test_concurrent_double_buy_of_last_units(client, db):
    """Two buyers race for the same last 10 units — exactly one wins (FOR UPDATE)."""
    ta = await _verified_user(client, db, "racea@i.com")
    tb = await _verified_user(client, db, "raceb@i.com")
    _fund_wallet(db, _uid(db, "racea@i.com"), 5000)
    _fund_wallet(db, _uid(db, "raceb@i.com"), 5000)
    pid = _seed_property(db, unit_price=100, total_units=10, available=10, total_value=1000)

    ra, rb = await asyncio.gather(
        _invest(client, ta, pid, 1000, "wallet"),
        _invest(client, tb, pid, 1000, "wallet"),
        return_exceptions=False,
    )
    codes = sorted([ra.status_code, rb.status_code])
    assert codes == [200, 409], f"{ra.status_code}/{ra.text} | {rb.status_code}/{rb.text}"
    loser = ra if ra.status_code == 409 else rb
    # The winner takes the last units and flips the property to `funded`, so the
    # loser is turned away with either code — both mean "you can't buy these units".
    assert loser.json()["error"]["code"] in {"INSUFFICIENT_UNITS", "PROPERTY_NOT_OPEN"}
    # exactly 10 units sold, property funded, no oversell
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 0
    assert db("SELECT status FROM properties WHERE id=:i", i=pid)[0][0] == "funded"
    assert (
        db("SELECT COALESCE(SUM(units),0) FROM ownership_ledger WHERE property_id=:i", i=pid)[0][0]
        == 10
    )
    _assert_unit_invariant(db, pid)


@pytest.mark.asyncio
async def test_available_units_check_constraint_backstop(db):
    """Even bypassing the service, the DB refuses a negative available_units."""
    pid = _seed_property(db, unit_price=100, total_units=10, available=0)
    with pytest.raises(IntegrityError):
        db("UPDATE properties SET available_units = -1 WHERE id=:i", i=pid)


# --- direct-pay: reserve -> webhook confirm --------------------------------- #
@pytest.mark.asyncio
async def test_direct_pay_reserves_then_webhook_confirms(client, db, monkeypatch):
    _configure_stripe(monkeypatch)
    token = await _verified_user(client, db, "card@i.com")
    pid = _seed_property(db, unit_price=100, total_units=100, total_value=10000)

    res = await _invest(client, token, pid, 1000, "card")
    assert res.status_code == 200, res.text
    body = res.json()
    inv_id = body["investment_id"]
    assert body["status"] == "pending"
    assert body["checkout_url"] == "https://pay.test/checkout"
    # units reserved, but money NOT booked yet
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 90
    assert db("SELECT funded_amount FROM properties WHERE id=:i", i=pid)[0][0] == 0
    assert db("SELECT count(*) FROM ownership_ledger WHERE property_id=:i", i=pid)[0][0] == 0
    pay_id = _payment_id_for(db, inv_id)

    # webhook confirms (captured = total charge 1025.00)
    r = await _post_stripe(client, _stripe_event(pay_id, cents=102500, event_id="evt_inv1"))
    assert r.json()["result"] == "confirmed"
    assert db("SELECT status FROM investments WHERE id=:i", i=inv_id)[0][0] == "confirmed"
    assert db("SELECT funded_amount FROM properties WHERE id=:i", i=pid)[0][0] == 1000
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 90
    assert db("SELECT units FROM ownership_ledger WHERE property_id=:i", i=pid)[0][0] == 10
    # confirm is idempotent: replaying the same event does nothing new
    r2 = await _post_stripe(client, _stripe_event(pay_id, cents=102500, event_id="evt_inv1"))
    assert r2.json()["status"] == "duplicate"
    assert db("SELECT count(*) FROM ownership_ledger WHERE property_id=:i", i=pid)[0][0] == 1
    _assert_unit_invariant(db, pid)


@pytest.mark.asyncio
async def test_pronova_charges_discounted_total_but_funds_in_full(client, db, monkeypatch):
    """Pronova (D5): SETTLES VIA STRIPE CARD at (subtotal + fee) x (1 - 5%), yet the buyer
    receives the FULL units and the property books the FULL subtotal — the 5% is a platform-
    funded promo subsidy, recorded on the investment snapshot. Distinct method from 'card'."""
    _configure_stripe(monkeypatch)
    token = await _verified_user(client, db, "pronova@i.com")
    pid = _seed_property(db, unit_price=100, total_units=100, total_value=10000)

    res = await _invest(client, token, pid, 1000, "pronova")
    assert res.status_code == 200, res.text
    body = res.json()
    inv_id = body["investment_id"]
    # subtotal + platform fee are FULL; only the CHARGE is discounted 5% (1025.00 -> 973.75).
    assert body["amount"] == "1000.00"
    assert body["platform_fee"] == "25.00"
    assert body["total_charged"] == "973.75"
    assert body["checkout_url"] == "https://pay.test/checkout"
    # the subsidy is recorded on the investment snapshot (auditable)
    snap = db("SELECT fee_settings_snapshot FROM investments WHERE id=:i", i=inv_id)[0][0]
    assert snap["pronova_discount_pct"] == "5.0"
    assert snap["pronova_discount_amount"] == "51.25"
    # Stripe is asked to charge EXACTLY the discounted total
    assert (
        db("SELECT amount::text FROM payments WHERE related_investment_id=:i", i=inv_id)[0][0]
        == "973.75"
    )
    # units reserved; money not booked until the webhook confirms
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 90
    assert db("SELECT funded_amount FROM properties WHERE id=:i", i=pid)[0][0] == 0

    pay_id = _payment_id_for(db, inv_id)
    # webhook confirms with the discounted capture (97375 cents)
    r = await _post_stripe(client, _stripe_event(pay_id, cents=97375, event_id="evt_pronova"))
    assert r.json()["result"] == "confirmed"
    # property funds in FULL (subtotal 1000), full units issued, confirmed via 'pronova'
    assert db("SELECT funded_amount FROM properties WHERE id=:i", i=pid)[0][0] == 1000
    assert db("SELECT units FROM ownership_ledger WHERE property_id=:i", i=pid)[0][0] == 10
    assert db("SELECT confirmed_via FROM investments WHERE id=:i", i=inv_id)[0][0] == "pronova"
    _assert_unit_invariant(db, pid)


@pytest.mark.asyncio
async def test_failed_webhook_releases_reservation(client, db, monkeypatch):
    _configure_stripe(monkeypatch)
    token = await _verified_user(client, db, "fail@i.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    res = await _invest(client, token, pid, 1000, "card")
    inv_id = res.json()["investment_id"]
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 90
    pay_id = _payment_id_for(db, inv_id)

    r = await _post_stripe(client, _stripe_event(pay_id, cents=0, event_id="evt_exp", expired=True))
    assert r.json()["result"] == "failed"
    # units restored, reservation cancelled
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 100
    assert db("SELECT status FROM investments WHERE id=:i", i=inv_id)[0][0] == "cancelled"
    _assert_unit_invariant(db, pid)


# --- reservation expiry + late-webhook reconciliation ----------------------- #
@pytest.mark.asyncio
async def test_reservation_expiry_releases_units(client, db, asession, monkeypatch):
    _configure_stripe(monkeypatch)
    token = await _verified_user(client, db, "exp@i.com")
    pid = _seed_property(db, unit_price=100, total_units=100)
    res = await _invest(client, token, pid, 1000, "card")
    inv_id = res.json()["investment_id"]
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 90

    # force the reservation window into the past, then run the sweep
    db(
        "UPDATE investments SET reservation_expires_at = now() - interval '1 hour' WHERE id=:i",
        i=inv_id,
    )
    count = await investment_service.expire_reservations(asession)
    await asession.commit()
    assert count == 1
    assert db("SELECT status FROM investments WHERE id=:i", i=inv_id)[0][0] == "expired"
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 100
    _assert_unit_invariant(db, pid)


@pytest.mark.asyncio
async def test_late_webhook_after_expiry_reconciles_when_units_free(
    client, db, asession, monkeypatch
):
    _configure_stripe(monkeypatch)
    token = await _verified_user(client, db, "lateok@i.com")
    pid = _seed_property(db, unit_price=100, total_units=20, total_value=2000)
    res = await _invest(client, token, pid, 1000, "card")
    inv_id = res.json()["investment_id"]
    pay_id = _payment_id_for(db, inv_id)

    db(
        "UPDATE investments SET reservation_expires_at = now() - interval '1 hour' WHERE id=:i",
        i=inv_id,
    )
    await investment_service.expire_reservations(asession)
    await asession.commit()
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 20

    # late payment arrives; units still free -> re-acquire + confirm
    r = await _post_stripe(client, _stripe_event(pay_id, cents=102500, event_id="evt_late_ok"))
    assert r.json()["result"] == "reconciled_confirmed"
    assert db("SELECT status FROM investments WHERE id=:i", i=inv_id)[0][0] == "confirmed"
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 10
    assert db("SELECT units FROM ownership_ledger WHERE property_id=:i", i=pid)[0][0] == 10
    _assert_unit_invariant(db, pid)


@pytest.mark.asyncio
async def test_late_webhook_after_expiry_refunds_when_sold_out(client, db, asession, monkeypatch):
    _configure_stripe(monkeypatch)
    ta = await _verified_user(client, db, "latea@i.com")
    tb = await _verified_user(client, db, "lateb@i.com")
    uida = _uid(db, "latea@i.com")
    _fund_wallet(db, _uid(db, "lateb@i.com"), 5000)
    pid = _seed_property(db, unit_price=100, total_units=10, available=10, total_value=1000)

    # A reserves all 10 via card
    res = await _invest(client, ta, pid, 1000, "card")
    inv_id = res.json()["investment_id"]
    pay_id = _payment_id_for(db, inv_id)
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 0

    # A's reservation expires -> units released
    db(
        "UPDATE investments SET reservation_expires_at = now() - interval '1 hour' WHERE id=:i",
        i=inv_id,
    )
    await investment_service.expire_reservations(asession)
    await asession.commit()
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 10

    # B buys all 10 with wallet -> sold out
    rb = await _invest(client, tb, pid, 1000, "wallet")
    assert rb.status_code == 200
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 0

    # A's late webhook -> units gone -> refund the captured amount to A's wallet
    r = await _post_stripe(client, _stripe_event(pay_id, cents=102500, event_id="evt_late_refund"))
    assert r.json()["result"] == "refunded"
    assert db("SELECT balance FROM wallets WHERE user_id=:i", i=uida)[0][0] == 1025
    assert db("SELECT failure_reason FROM investments WHERE id=:i", i=inv_id)[0][0] == (
        "units_unavailable_refunded"
    )
    assert (
        db("SELECT count(*) FROM transactions WHERE user_id=:i AND type='deposit'", i=uida)[0][0]
        == 1
    )
    _assert_balance_invariant(db, uida)
    _assert_unit_invariant(db, pid)


# --- provider gating + reads ------------------------------------------------ #
@pytest.mark.asyncio
async def test_direct_pay_503_when_provider_unconfigured(client, db):
    token = await _verified_user(client, db, "noprov@i.com")
    pid = _seed_property(db, unit_price=100)
    res = await _invest(client, token, pid, 1000, "card")
    assert res.status_code == 503 and res.json()["error"]["code"] == "PAYMENTS_NOT_CONFIGURED"
    # nothing reserved on a 503
    assert db("SELECT available_units FROM properties WHERE id=:i", i=pid)[0][0] == 100
    assert db("SELECT count(*) FROM investments WHERE property_id=:i", i=pid)[0][0] == 0


@pytest.mark.asyncio
async def test_list_and_get_my_investments(client, db):
    token = await _verified_user(client, db, "list@i.com")
    _fund_wallet(db, _uid(db, "list@i.com"), 10000)
    pid = _seed_property(db, unit_price=100)
    created = (await _invest(client, token, pid, 1000, "wallet")).json()
    lst = await client.get("/api/v1/investments", headers={"Authorization": f"Bearer {token}"})
    assert lst.status_code == 200 and lst.json()["total"] == 1
    one = await client.get(
        f"/api/v1/investments/{created['investment_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert one.status_code == 200 and one.json()["units"] == 10


@pytest.mark.asyncio
async def test_investments_require_auth(client):
    assert (await client.get("/api/v1/investments")).status_code == 401
    assert (await client.post("/api/v1/investments", json={})).status_code == 401
