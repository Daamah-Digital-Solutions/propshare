"""The same payment methods on every property (client feedback 2026-09-27, the Capimax BRX
concept): wallet, card / Apple Pay / Google Pay, crypto, Pronova and Nova Sukuk.

* ``GET /investments/payment-options`` lists every method on every property, and says which
  are live (a rail without provider keys is shown as not available, never dropped).
* An installment plan's down payment by card / crypto / Pronova: the plan's units are held
  while the checkout is open; the webhook starts the plan (down payment booked, units vested,
  wallet untouched); a failed / expired checkout releases the units; a late payment restarts
  the plan if its units are free, else is refunded to the wallet. Pronova takes its discount
  off what is paid now (the down payment and its fee).
* Nova Sukuk: the investor uploads a certificate (PDF); the units are held while staff review
  it; approval confirms the purchase / starts the plan exactly like a paid checkout and pledges
  the units to Nova Finance (not sellable until staff release the pledge); rejection (with a
  reason) releases them.
* Throughout, units conserve (the reconciliation invariant counts plans that have not started).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest

from app.core.config import get_settings
from app.services import (
    installment_service,
    payment_service,
    reconciliation_service,
    secondary_service,
    sukuk_service,
)
from app.services.integrations.payments import CheckoutResult
from app.services.integrations.payments import nowpayments_gateway as nowp
from app.services.integrations.payments import stripe_gateway as stripe

PW = "Passw0rd!23"
PDF = b"%PDF-1.4\n% a Nova certificate\n"


# --- helpers -------------------------------------------------------------------------------
async def _investor(client, db, email: str, balance: int = 0) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "Investor"}
    )
    uid = str(db("SELECT id FROM users WHERE email=:e", e=email)[0][0])
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:u", u=uid)
    db("UPDATE wallets SET balance=:b WHERE user_id=:u", b=balance, u=uid)
    return r.json()["access_token"], uid


def _admin_id(db, email: str = "staff@pm.com") -> str:
    uid = str(uuid.uuid4())
    db("INSERT INTO users (id, email, full_name) VALUES (:i, :e, 'Staff')", i=uid, e=email)
    db("INSERT INTO user_roles (user_id, role) VALUES (:i, 'admin')", i=uid)
    return uid


def _property(db, *, model: str = "installment", units: int = 100) -> str:
    pid = str(uuid.uuid4())
    db(
        "INSERT INTO properties (id,title,location,property_type,model,status,"
        "total_value,unit_price,total_units,available_units,minimum_investment) VALUES "
        "(:id,'Creek Tower','Dubai','residential',:m,'active',:tv,100,:tu,:tu,100)",
        id=pid,
        m=model,
        tv=100 * units,
        tu=units,
    )
    return pid


def _h(token: str, key: str | None = None) -> dict:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key or str(uuid.uuid4())}


def _available(db, pid: str) -> int:
    return int(db("SELECT available_units FROM properties WHERE id=:p", p=pid)[0][0])


def _balance(db, uid: str) -> float:
    return float(db("SELECT balance FROM wallets WHERE user_id=:u", u=uid)[0][0])


def _owned(db, uid: str, pid: str) -> int:
    return int(
        db(
            "SELECT COALESCE(SUM(units),0) FROM ownership_ledger"
            " WHERE user_id=:u AND property_id=:p",
            u=uid,
            p=pid,
        )[0][0]
    )


def _told(db, uid: str, title: str) -> list[str]:
    return [
        r[0]
        for r in db(
            "SELECT message FROM notifications WHERE user_id=:u AND title=:t", u=uid, t=title
        )
    ]


async def _units_conserve(asession) -> None:
    result = await reconciliation_service.run(asession)
    units = next(c for c in result["checks"] if c["name"] == "property_units")
    assert units["drift_count"] == 0, units["samples"]


def _card_rail(monkeypatch) -> list[dict]:
    """Stripe on, without the network; returns the checkouts created."""
    made: list[dict] = []

    async def fake_checkout(**kwargs):
        made.append(kwargs)
        return CheckoutResult(
            provider_payment_id="cs_" + uuid.uuid4().hex[:10],
            checkout_url="https://checkout.stripe.test/pay",
            status="pending",
        )

    monkeypatch.setattr(stripe, "is_configured", lambda: True)
    monkeypatch.setattr(stripe, "create_checkout", fake_checkout)
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)
    return made


async def _stripe_webhook(client, payment_id: str, *, cents: int, paid: bool = True):
    event = (
        {
            "id": "evt_" + uuid.uuid4().hex[:10],
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_x",
                    "client_reference_id": payment_id,
                    "payment_status": "paid",
                    "amount_total": cents,
                    "currency": "usd",
                }
            },
        }
        if paid
        else {
            "id": "evt_" + uuid.uuid4().hex[:10],
            "type": "checkout.session.expired",
            "data": {"object": {"id": "cs_x", "client_reference_id": payment_id}},
        }
    )
    body = json.dumps(event).encode()
    sig = hmac.new(b"whsec_t", b"1700000000." + body, hashlib.sha256).hexdigest()
    return await client.post(
        "/api/v1/payments/webhooks/stripe",
        content=body,
        headers={"stripe-signature": f"t=1700000000,v1={sig}", "content-type": "application/json"},
    )


async def _plan(client, token, pid, *, method: str, amount=1200, duration=12, key=None):
    return await client.post(
        "/api/v1/installments",
        json={"property_id": pid, "amount": amount, "duration_months": duration, "method": method},
        headers=_h(token, key),
    )


def _sukuk_form(pid: str, amount, **extra) -> dict:
    return {"property_id": pid, "amount": str(amount), **{k: str(v) for k, v in extra.items()}}


async def _buy_with_sukuk(client, token, pid, *, amount=1000, data=PDF, key=None, **extra):
    return await client.post(
        "/api/v1/investments/sukuk",
        data=_sukuk_form(pid, amount, **extra),
        files={"file": ("nova-certificate.pdf", data, "application/pdf")},
        headers=_h(token, key),
    )


# --- one list of methods, everywhere ---------------------------------------------------------
@pytest.mark.asyncio
async def test_every_method_is_listed_and_a_missing_rail_is_shown_unavailable(client, monkeypatch):
    r = await client.get("/api/v1/investments/payment-options")  # public: no sign-in
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "wallet",
        "card",
        "apple_pay",
        "google_pay",
        "crypto",
        "pronova",
        "sukuk",
        "pronova_discount_pct",
    }
    # no provider keys in tests: the rails are listed, marked unavailable
    assert body["wallet"] and body["sukuk"]
    assert not any(body[k] for k in ("card", "apple_pay", "google_pay", "crypto", "pronova"))
    assert float(body["pronova_discount_pct"]) == 5.0

    monkeypatch.setattr(stripe, "is_configured", lambda: True)
    monkeypatch.setattr(nowp, "is_configured", lambda: True)
    body = (await client.get("/api/v1/investments/payment-options")).json()
    assert all(body[k] for k in ("card", "apple_pay", "google_pay", "crypto", "pronova"))


# --- installment down payment through a checkout ---------------------------------------------
@pytest.mark.asyncio
async def test_a_card_down_payment_holds_the_units_then_starts_the_plan(
    client, db, asession, monkeypatch
):
    made = _card_rail(monkeypatch)
    token, uid = await _investor(client, db, "card-plan@pm.com", balance=0)
    pid = _property(db)

    r = await _plan(client, token, pid, method="card")  # 12 units, 25% down = $300 + fee
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["status"] == "pending_payment" and plan["payment_method"] == "card"
    assert plan["checkout_url"] == "https://checkout.stripe.test/pay" and plan["payment_id"]
    down = plan["payments"][0]
    assert float(made[0]["amount"]) == pytest.approx(float(down["total_amount"]))
    assert "down payment" in made[0]["product_name"]
    assert _available(db, pid) == 88  # held while the checkout is open
    assert _owned(db, uid, pid) == 0 and _balance(db, uid) == 0
    await _units_conserve(asession)

    r = await _stripe_webhook(
        client, plan["payment_id"], cents=int(float(down["total_amount"]) * 100)
    )
    assert r.status_code == 200, r.text
    row = db(
        "SELECT status, vested_units, reservation_expires_at FROM installment_plans WHERE id=:p",
        p=plan["id"],
    )[0]
    assert row[0] == "active" and row[1] == down["vest_units"] and row[2] is None
    assert (
        db("SELECT status FROM installment_payments WHERE plan_id=:p AND seq=0", p=plan["id"])[0][0]
        == "paid"
    )
    assert _owned(db, uid, pid) == down["vest_units"]
    assert _balance(db, uid) == 0  # paid by card: nothing debited from the wallet
    invested = db("SELECT total_invested FROM wallets WHERE user_id=:u", u=uid)[0][0]
    assert float(invested) == float(down["base_amount"])
    funded, investors = db(
        "SELECT funded_amount, investors_count FROM properties WHERE id=:p", p=pid
    )[0]
    assert float(funded) == float(down["base_amount"]) and investors == 1
    assert any("was paid by card" in m for m in _told(db, uid, "Installment paid"))
    await _units_conserve(asession)

    # the same delivery again (Stripe retry / Resend) changes nothing
    again = await _stripe_webhook(
        client, plan["payment_id"], cents=int(float(down["total_amount"]) * 100)
    )
    assert again.status_code == 200
    assert _owned(db, uid, pid) == down["vest_units"]
    assert db("SELECT investors_count FROM properties WHERE id=:p", p=pid)[0][0] == 1


@pytest.mark.asyncio
async def test_pronova_takes_its_discount_off_the_down_payment(client, db, monkeypatch):
    made = _card_rail(monkeypatch)
    token, _ = await _investor(client, db, "pronova-plan@pm.com")
    pid = _property(db)
    plan = (await _plan(client, token, pid, method="pronova")).json()
    due = float(plan["payments"][0]["total_amount"])
    discount = round(due * 0.05, 2)
    assert float(plan["discount_amount"]) == pytest.approx(discount)
    assert float(made[0]["amount"]) == pytest.approx(due - discount)
    assert "Pronova" in made[0]["product_name"]
    # the schedule keeps the full amounts (the discount is platform-funded)
    assert float(plan["payments"][0]["total_amount"]) == due


@pytest.mark.asyncio
async def test_a_failed_or_unpaid_checkout_releases_the_plan(client, db, asession, monkeypatch):
    _card_rail(monkeypatch)
    token, _ = await _investor(client, db, "unpaid-plan@pm.com")
    pid = _property(db)

    failed = (await _plan(client, token, pid, method="card")).json()
    r = await _stripe_webhook(client, failed["payment_id"], cents=0, paid=False)
    assert r.status_code == 200, r.text
    assert db("SELECT status FROM installment_plans WHERE id=:p", p=failed["id"])[0][0] == (
        "cancelled"
    )
    assert _available(db, pid) == 100
    statuses = {
        r[0] for r in db("SELECT status FROM installment_payments WHERE plan_id=:p", p=failed["id"])
    }
    assert statuses == {"cancelled"}

    lapsed = (await _plan(client, token, pid, method="card")).json()
    assert _available(db, pid) == 88
    db(
        "UPDATE installment_plans SET reservation_expires_at = now() - interval '1 minute' "
        "WHERE id=:p",
        p=lapsed["id"],
    )
    monkeypatch.setattr(get_settings(), "cron_secret", "cron-t", raising=False)
    r = await client.post(
        "/api/v1/investments/maintenance/expire-reservations", headers={"X-Cron-Secret": "cron-t"}
    )
    assert r.status_code == 200 and r.json()["expired_plans"] == 1
    assert db("SELECT status FROM installment_plans WHERE id=:p", p=lapsed["id"])[0][0] == "expired"
    assert _available(db, pid) == 100
    await _units_conserve(asession)


@pytest.mark.asyncio
async def test_a_down_payment_paid_late_restarts_the_plan_or_is_refunded(
    client, db, asession, monkeypatch
):
    _card_rail(monkeypatch)
    token, uid = await _investor(client, db, "late-plan@pm.com")
    pid = _property(db, units=12)
    plan = (await _plan(client, token, pid, method="card")).json()  # all 12 units
    db("UPDATE installment_plans SET reservation_expires_at = now() - interval '1 minute'")
    assert await installment_service.expire_pending_plans(asession) == 1
    await asession.commit()
    down = plan["payments"][0]
    cents = int(float(down["total_amount"]) * 100)

    # the units are still free: the plan starts after all
    r = await _stripe_webhook(client, plan["payment_id"], cents=cents)
    assert r.status_code == 200, r.text
    assert db("SELECT status FROM installment_plans WHERE id=:p", p=plan["id"])[0][0] == "active"
    assert _available(db, pid) == 0 and _owned(db, uid, pid) == down["vest_units"]
    await _units_conserve(asession)

    # another plan expires, someone else buys the units, then its payment arrives: refunded
    pid2 = _property(db, units=12)
    plan2 = (await _plan(client, token, pid2, method="card")).json()
    db(
        "UPDATE installment_plans SET reservation_expires_at = now() - interval '1 minute' "
        "WHERE id=:p",
        p=plan2["id"],
    )
    assert await installment_service.expire_pending_plans(asession) == 1
    await asession.commit()
    db("UPDATE properties SET available_units = 0, status = 'funded' WHERE id=:p", p=pid2)
    cents2 = int(float(plan2["payments"][0]["total_amount"]) * 100)
    r = await _stripe_webhook(client, plan2["payment_id"], cents=cents2)
    assert r.status_code == 200, r.text
    assert db("SELECT status FROM installment_plans WHERE id=:p", p=plan2["id"])[0][0] == "expired"
    assert _balance(db, uid) == pytest.approx(cents2 / 100)
    assert _told(db, uid, "Installment plan refunded")


@pytest.mark.asyncio
async def test_the_wallet_still_starts_a_plan_at_once(client, db):
    token, uid = await _investor(client, db, "wallet-plan@pm.com", balance=100000)
    pid = _property(db)
    r = await _plan(client, token, pid, method="wallet")
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["status"] == "active" and plan["payment_method"] == "wallet"
    assert plan["checkout_url"] is None
    assert _balance(db, uid) == pytest.approx(100000 - float(plan["payments"][0]["total_amount"]))
    assert db("SELECT investors_count FROM properties WHERE id=:p", p=pid)[0][0] == 1


@pytest.mark.asyncio
async def test_a_card_purchase_counts_toward_the_invested_cost_basis(client, db, monkeypatch):
    """Regression: only wallet purchases counted in total_invested, so a buyer who paid by
    card saw the whole value of the units as a gain in the portfolio."""
    _card_rail(monkeypatch)
    token, uid = await _investor(client, db, "card-buy@pm.com")
    pid = _property(db, model="ready-income")
    r = await client.post(
        "/api/v1/investments",
        json={"property_id": pid, "amount": 500, "method": "card"},
        headers=_h(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    cents = int(float(body["total_charged"]) * 100)
    assert (await _stripe_webhook(client, body["payment_id"], cents=cents)).status_code == 200
    assert db("SELECT status FROM investments WHERE id=:i", i=body["investment_id"])[0][0] == (
        "confirmed"
    )
    assert float(db("SELECT total_invested FROM wallets WHERE user_id=:u", u=uid)[0][0]) == 500
    summary = (await client.get("/api/v1/investments/portfolio", headers=_h(token))).json()
    assert float(summary["invested"]) == 500


# --- Nova Sukuk -------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_sukuk_purchase_is_held_then_approved_and_pledged(
    client, db, asession, monkeypatch
):
    token, uid = await _investor(client, db, "sukuk-buy@pm.com")
    staff = _admin_id(db)
    pid = _property(db, model="ready-income")
    monkeypatch.setattr(get_settings(), "support_inbox_email", "ops@pm.com", raising=False)

    r = await _buy_with_sukuk(
        client, token, pid, amount=1000, certificate_no="NOVA-77", issuer="Nova Digital Finance"
    )
    assert r.status_code == 201, r.text
    cert = r.json()
    assert cert["status"] == "pending" and cert["kind"] == "purchase" and cert["units"] == 10
    assert float(cert["amount_due"]) == 1025.0  # 10 units + the 2.5% platform fee
    assert _available(db, pid) == 90 and _owned(db, uid, pid) == 0
    inv = db("SELECT status, payment_method FROM investments WHERE id=:i", i=cert["investment_id"])[
        0
    ]
    assert (inv[0], inv[1]) == ("pending", "nova_sukuk")
    assert _told(db, uid, "Nova certificate received — under review")
    assert _told(db, staff, "Nova certificate waiting for review")
    outbox = db("SELECT subject, body FROM email_outbox WHERE to_email='ops@pm.com'")
    assert outbox and "Nova Sukuk" in outbox[0][0] and "/admin/sukuk-review/" in outbox[0][1]
    await _units_conserve(asession)

    # the expiry sweep never touches it: a review takes time
    from app.services import investment_service

    assert await investment_service.expire_reservations(asession) == 0

    await sukuk_service.approve(
        asession,
        certificate_id=uuid.UUID(cert["certificate_id"]),
        admin_id=uuid.UUID(staff),
        note=None,
    )
    await asession.commit()
    inv = db("SELECT status, confirmed_via FROM investments WHERE id=:i", i=cert["investment_id"])[
        0
    ]
    assert (inv[0], inv[1]) == ("confirmed", "sukuk")
    assert _owned(db, uid, pid) == 10 and _available(db, pid) == 90
    # counted in the invested cost basis like a wallet purchase (no phantom gain)
    assert float(db("SELECT total_invested FROM wallets WHERE user_id=:u", u=uid)[0][0]) == 1000
    assert _told(db, uid, "Nova certificate approved")
    await _units_conserve(asession)

    # pledged to Nova Finance: none of the 10 units can be listed
    held = await secondary_service.reserved_units(asession, uuid.UUID(uid), uuid.UUID(pid))
    assert held == 10
    with pytest.raises(Exception) as exc:
        await secondary_service.create_listing(
            asession,
            seller_id=uuid.UUID(uid),
            property_id=uuid.UUID(pid),
            units=1,
            price_per_unit=100,
        )
    assert getattr(exc.value, "code", "") == "INSUFFICIENT_UNITS"
    await asession.rollback()

    await sukuk_service.release_pledge(
        asession,
        certificate_id=uuid.UUID(cert["certificate_id"]),
        admin_id=uuid.UUID(staff),
        note="NF-123",
    )
    await asession.commit()
    assert await secondary_service.reserved_units(asession, uuid.UUID(uid), uuid.UUID(pid)) == 0
    assert _told(db, uid, "Nova pledge released")

    mine = (await client.get("/api/v1/investments/sukuk", headers=_h(token))).json()
    assert [(m["status"], m["property_title"]) for m in mine] == [("released", "Creek Tower")]


@pytest.mark.asyncio
async def test_a_rejected_certificate_releases_the_units_and_says_why(client, db, asession):
    token, uid = await _investor(client, db, "sukuk-reject@pm.com")
    staff = _admin_id(db)
    pid = _property(db, model="ready-income")
    cert = (await _buy_with_sukuk(client, token, pid, amount=500)).json()
    assert _available(db, pid) == 95

    with pytest.raises(Exception) as exc:
        await sukuk_service.reject(
            asession,
            certificate_id=uuid.UUID(cert["certificate_id"]),
            admin_id=uuid.UUID(staff),
            reason="",
        )
    assert getattr(exc.value, "code", "") == "REASON_REQUIRED"
    await asession.rollback()

    await sukuk_service.reject(
        asession,
        certificate_id=uuid.UUID(cert["certificate_id"]),
        admin_id=uuid.UUID(staff),
        reason="The certificate is not signed by Nova.",
    )
    await asession.commit()
    assert _available(db, pid) == 100
    assert db("SELECT status FROM investments WHERE id=:i", i=cert["investment_id"])[0][0] == (
        "cancelled"
    )
    told = _told(db, uid, "Nova certificate not accepted")
    assert told and "not signed by Nova" in told[0]
    mine = (await client.get("/api/v1/investments/sukuk", headers=_h(token))).json()
    assert mine[0]["status"] == "rejected" and "not signed" in mine[0]["review_note"]
    # a decided certificate cannot be decided again
    with pytest.raises(Exception) as exc:
        await sukuk_service.approve(
            asession,
            certificate_id=uuid.UUID(cert["certificate_id"]),
            admin_id=uuid.UUID(staff),
            note=None,
        )
    assert getattr(exc.value, "code", "") == "INVALID_TRANSITION"
    await _units_conserve(asession)


@pytest.mark.asyncio
async def test_what_cannot_be_a_certificate_is_refused_before_anything_is_held(client, db):
    token, _ = await _investor(client, db, "sukuk-bad@pm.com")
    pid = _property(db, model="ready-income")
    not_pdf = await _buy_with_sukuk(client, token, pid, data=b"just an image")
    assert not_pdf.status_code == 422 and not_pdf.json()["error"]["code"] == "CERTIFICATE_NOT_PDF"
    expired = await _buy_with_sukuk(client, token, pid, valid_until="2020-01-01")
    assert expired.status_code == 422 and expired.json()["error"]["code"] == "CERTIFICATE_EXPIRED"
    bad_value = await _buy_with_sukuk(client, token, pid, certificate_value="lots")
    assert bad_value.status_code == 422
    too_big = await _buy_with_sukuk(
        client, token, pid, data=PDF + b"0" * sukuk_service.MAX_CERTIFICATE_BYTES
    )
    assert too_big.status_code == 422 and too_big.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert _available(db, pid) == 100
    assert db("SELECT count(*) FROM sukuk_certificates")[0][0] == 0


@pytest.mark.asyncio
async def test_a_repeated_sukuk_request_holds_the_units_once(client, db):
    token, _ = await _investor(client, db, "sukuk-twice@pm.com")
    pid = _property(db, model="ready-income")
    first = await _buy_with_sukuk(client, token, pid, amount=300, key="same-key")
    again = await _buy_with_sukuk(client, token, pid, amount=300, key="same-key")
    assert first.status_code == 201 and again.status_code == 201
    assert first.json()["certificate_id"] == again.json()["certificate_id"]
    assert _available(db, pid) == 97
    assert db("SELECT count(*) FROM sukuk_certificates")[0][0] == 1


@pytest.mark.asyncio
async def test_a_sukuk_down_payment_starts_the_plan_on_approval(client, db, asession):
    token, uid = await _investor(client, db, "sukuk-plan@pm.com", balance=0)
    staff = _admin_id(db)
    pid = _property(db)
    r = await client.post(
        "/api/v1/installments/sukuk",
        data={"property_id": pid, "amount": "1200", "duration_months": "12"},
        files={"file": ("nova.pdf", PDF, "application/pdf")},
        headers=_h(token),
    )
    assert r.status_code == 201, r.text
    cert = r.json()
    assert cert["kind"] == "installment" and cert["status"] == "pending"
    plan_id = cert["plan_id"]
    plan = db(
        "SELECT status, payment_method, units_total FROM installment_plans WHERE id=:p", p=plan_id
    )[0]
    assert (plan[0], plan[1], plan[2]) == ("pending_review", "sukuk", 12)
    down_total, down_units = db(
        "SELECT total_amount, vest_units FROM installment_payments WHERE plan_id=:p AND seq=0",
        p=plan_id,
    )[0]
    assert float(cert["amount_due"]) == float(down_total) and cert["units"] == down_units
    assert _available(db, pid) == 88
    await _units_conserve(asession)

    await sukuk_service.approve(
        asession,
        certificate_id=uuid.UUID(cert["certificate_id"]),
        admin_id=uuid.UUID(staff),
        note="ok",
    )
    await asession.commit()
    assert db("SELECT status FROM installment_plans WHERE id=:p", p=plan_id)[0][0] == "active"
    assert _owned(db, uid, pid) == down_units and _balance(db, uid) == 0
    assert any("with your Nova Sukuk certificate" in m for m in _told(db, uid, "Installment paid"))
    # while the plan runs its vested units are held already: the pledge is not counted twice
    held = await secondary_service.reserved_units(asession, uuid.UUID(uid), uuid.UUID(pid))
    assert held == down_units
    await _units_conserve(asession)


@pytest.mark.asyncio
async def test_a_rejected_sukuk_plan_gives_its_units_back(client, db, asession):
    token, _ = await _investor(client, db, "sukuk-plan-no@pm.com")
    staff = _admin_id(db)
    pid = _property(db)
    cert = (
        await client.post(
            "/api/v1/installments/sukuk",
            data={"property_id": pid, "amount": "1200", "duration_months": "12"},
            files={"file": ("nova.pdf", PDF, "application/pdf")},
            headers=_h(token),
        )
    ).json()
    await sukuk_service.reject(
        asession,
        certificate_id=uuid.UUID(cert["certificate_id"]),
        admin_id=uuid.UUID(staff),
        reason="Expired financing approval.",
    )
    await asession.commit()
    assert db("SELECT status FROM installment_plans WHERE id=:p", p=cert["plan_id"])[0][0] == (
        "cancelled"
    )
    assert _available(db, pid) == 100
    await _units_conserve(asession)


@pytest.mark.asyncio
async def test_the_review_pages_are_for_admins_only(client):
    for path in ("/admin/sukuk-review", "/admin/sukuk-certificate?cert=" + str(uuid.uuid4())):
        r = await client.get(path, follow_redirects=False)
        assert r.status_code in (302, 303, 307) and "/admin/login" in r.headers["location"]


def test_purchase_options_follow_the_providers(monkeypatch):
    monkeypatch.setattr(stripe, "is_configured", lambda: True)
    monkeypatch.setattr(nowp, "is_configured", lambda: False)
    opts = payment_service.purchase_options()
    assert opts["card"] and opts["apple_pay"] and opts["google_pay"] and opts["pronova"]
    assert not opts["crypto"] and opts["wallet"] and opts["sukuk"]


# --- review findings -------------------------------------------------------------------------
async def _sukuk_plan(client, token, pid) -> dict:
    r = await client.post(
        "/api/v1/installments/sukuk",
        data={"property_id": pid, "amount": "1200", "duration_months": "12"},
        files={"file": ("nova.pdf", PDF, "application/pdf")},
        headers=_h(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_a_plan_approved_late_runs_its_schedule_from_the_start(client, db, asession):
    """A Nova review that takes weeks must not start the plan with installments already due
    (charged at once, or marked missed right after the approval)."""
    import datetime as dt

    token, uid = await _investor(client, db, "late-review@pm.com", balance=5000)
    staff = _admin_id(db)
    pid = _property(db)
    cert = await _sukuk_plan(client, token, pid)
    # the request sat with the team for 40 days
    db(
        "UPDATE installment_payments SET due_date = due_date - 40 WHERE plan_id=:p",
        p=cert["plan_id"],
    )
    # meanwhile the monthly run never charges (nor locks) a plan that has not started
    await installment_service.run_due(asession)
    await asession.commit()
    first = db(
        "SELECT status FROM installment_payments WHERE plan_id=:p AND seq=1", p=cert["plan_id"]
    )[0][0]
    assert first == "scheduled"

    await sukuk_service.approve(
        asession,
        certificate_id=uuid.UUID(cert["certificate_id"]),
        admin_id=uuid.UUID(staff),
        note=None,
    )
    await asession.commit()
    today = dt.datetime.now(dt.UTC).date()
    due = dict(
        db(
            "SELECT seq, due_date FROM installment_payments WHERE plan_id=:p AND seq IN (0, 1)",
            p=cert["plan_id"],
        )
    )
    assert due[0] == today and due[1] == installment_service._add_months(today, 1)
    result = await installment_service.run_due(asession)
    await asession.commit()
    assert result["paid"] == 0 and result["overdue"] == 0
    assert _balance(db, uid) == 5000  # nothing charged at approval


@pytest.mark.asyncio
async def test_a_plan_that_never_started_does_not_lock_the_listing(
    client, db, asession, monkeypatch
):
    from app.services import listing_service

    _card_rail(monkeypatch)
    token, _ = await _investor(client, db, "abandoned@pm.com")
    pid = _property(db)
    plan = (await _plan(client, token, pid, method="card")).json()
    assert await listing_service.count_positions(asession, uuid.UUID(pid)) == 1  # held meanwhile
    await _stripe_webhook(client, plan["payment_id"], cents=0, paid=False)
    assert await listing_service.count_positions(asession, uuid.UUID(pid)) == 0


@pytest.mark.asyncio
async def test_a_down_payment_without_its_plan_goes_to_the_wallet(client, db, monkeypatch):
    _card_rail(monkeypatch)
    token, uid = await _investor(client, db, "orphan@pm.com")
    pay_id = str(uuid.uuid4())
    db(
        "INSERT INTO payments (id, user_id, provider, provider_payment_id, amount, currency,"
        " status,"
        " purpose, payment_method) VALUES (:i, :u, 'stripe', 'cs_orphan', 260, 'USD', 'pending',"
        " 'installment', 'card')",
        i=pay_id,
        u=uid,
    )
    r = await _stripe_webhook(client, pay_id, cents=26000)
    assert r.status_code == 200, r.text
    assert _balance(db, uid) == 260
    assert _told(db, uid, "Installment plan refunded")


@pytest.mark.asyncio
async def test_pledged_units_are_shown_as_pledged_not_as_listed(client, db, asession):
    token, uid = await _investor(client, db, "pledge-view@pm.com")
    staff = _admin_id(db)
    pid = _property(db, model="ready-income")
    cert = (await _buy_with_sukuk(client, token, pid, amount=1000)).json()
    await sukuk_service.approve(
        asession,
        certificate_id=uuid.UUID(cert["certificate_id"]),
        admin_id=uuid.UUID(staff),
        note=None,
    )
    await asession.commit()
    holdings = (await client.get("/api/v1/secondary/holdings", headers=_h(token))).json()["items"]
    mine = next(h for h in holdings if h["property_id"] == pid)
    assert (mine["units"], mine["pledged_units"], mine["listed_units"], mine["sellable_units"]) == (
        10,
        10,
        0,
        0,
    )


@pytest.mark.asyncio
async def test_odd_file_names_and_values_are_refused_or_stored_safely(client, db):
    token, _ = await _investor(client, db, "odd-upload@pm.com")
    pid = _property(db, model="ready-income")
    r = await client.post(
        "/api/v1/investments/sukuk",
        data=_sukuk_form(pid, 300),
        files={"file": ("my..cert..pdf", PDF, "application/pdf")},
        headers=_h(token),
    )
    assert r.status_code == 201, r.text
    key, name = db("SELECT file_key, file_name FROM sukuk_certificates")[0]
    assert ".." not in key and ".." not in name
    for value in ("NaN", "Infinity", "1e20"):
        bad = await _buy_with_sukuk(client, token, pid, certificate_value=value)
        assert bad.status_code == 422, (value, bad.text)
