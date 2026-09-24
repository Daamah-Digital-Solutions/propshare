"""Group 3 — DB-backed tests for saved payment methods (PCI-safe tokenization).

Acceptance: add stores only TOKENS + safe metadata (no card data, no token exposed in the
API); the card is read from the finished SetupIntent at Stripe, never named by the browser
(someone else's setup → 403, an unfinished one → 409); first method is default; set-default
switches; delete detaches + reassigns default; idempotent re-add; foreign delete → 404; honest
503 when Stripe or a same-mode publishable key is missing; auth required.

Stripe is unconfigured locally, so the gateway seam is monkeypatched to simulate Stripe
(the service logic + data model are what we assert).
"""

from __future__ import annotations

import pytest

import app.services.integrations.payments.stripe_gateway as gw

PW = "Passw0rd!23"


async def _user(client, db, email: str) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "U"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    return r.json()["access_token"], str(uid)


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


# SetupIntents Stripe knows about: id -> {customer, status, payment_method}
INTENTS: dict[str, dict] = {}
# cards marked for hosted Checkout to offer again
OFFERED: list[dict] = []


@pytest.fixture
def fake_stripe(monkeypatch):
    """Simulate a configured Stripe by replacing the gateway seam functions."""
    INTENTS.clear()
    OFFERED.clear()

    async def create_customer(*, email):
        return f"cus_{email.split('@')[0]}"

    async def create_setup_intent(*, customer_id):
        return {"id": "seti_1", "client_secret": "seti_1_secret_abc"}

    async def retrieve_setup_intent(setup_intent_id):
        return {"id": setup_intent_id, **INTENTS[setup_intent_id]}

    async def retrieve_payment_method(payment_method_id):
        return {
            "id": payment_method_id,
            "type": "card",
            "brand": "visa",
            "last4": "4242",
            "exp_month": 12,
            "exp_year": 2030,
        }

    async def detach_payment_method(payment_method_id):
        return None

    async def offer_again_at_checkout(payment_method_id, *, name=None, email=None):
        OFFERED.append({"pm": payment_method_id, "name": name, "email": email})

    monkeypatch.setattr(gw, "create_customer", create_customer)
    monkeypatch.setattr(gw, "create_setup_intent", create_setup_intent)
    monkeypatch.setattr(gw, "retrieve_setup_intent", retrieve_setup_intent)
    monkeypatch.setattr(gw, "retrieve_payment_method", retrieve_payment_method)
    monkeypatch.setattr(gw, "detach_payment_method", detach_payment_method)
    monkeypatch.setattr(gw, "offer_again_at_checkout", offer_again_at_checkout)
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "stripe_publishable_key", "pk_test_123", raising=False)
    yield


async def _add(client, tok, pm: str, *, status="succeeded", customer=None):
    """The investor finishes Stripe's card form: a SetupIntent on their customer produced pm."""
    setup = await client.post("/api/v1/wallet/payment-methods/setup-intent", headers=_h(tok))
    me = (await client.get("/api/v1/auth/me", headers=_h(tok))).json()["email"]
    seti = f"seti_{pm.replace('_', '')}x{len(INTENTS):04d}"
    INTENTS[seti] = {
        "customer": customer or f"cus_{me.split('@')[0]}",
        "status": status,
        "payment_method": pm,
    }
    assert setup.status_code == 200, setup.text
    return await _submit(client, tok, seti)


async def _submit(client, tok, seti: str):
    return await client.post(
        "/api/v1/wallet/payment-methods", json={"setup_intent_id": seti}, headers=_h(tok)
    )


# --- happy path ------------------------------------------------------------- #
async def test_add_stores_tokenized_metadata_only(client, db, fake_stripe):
    tok, uid = await _user(client, db, "pm-a@x.com")
    r = await _add(client, tok, "pm_card_1")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["brand"] == "visa" and body["last4"] == "4242"
    assert body["is_default"] is True  # first method
    # PCI: the Stripe token is NOT exposed in the API response
    assert "pm_card_1" not in r.text
    assert "provider_payment_method_id" not in body

    # stored as tokens only — the row keeps the token, never card data
    row = db(
        "SELECT provider_payment_method_id, brand, last4 FROM saved_payment_methods "
        "WHERE user_id=:u",
        u=uid,
    )
    assert row[0][0] == "pm_card_1" and row[0][1] == "visa"

    listed = await client.get("/api/v1/wallet/payment-methods", headers=_h(tok))
    assert [m["last4"] for m in listed.json()] == ["4242"]


async def test_setup_intent_returns_client_secret(client, db, fake_stripe):
    tok, _uid = await _user(client, db, "pm-si@x.com")
    r = await client.post("/api/v1/wallet/payment-methods/setup-intent", headers=_h(tok))
    assert r.status_code == 200, r.text
    assert r.json()["client_secret"] == "seti_1_secret_abc"
    assert r.json()["publishable_key"] == "pk_test_123"


async def test_default_and_set_default(client, db, fake_stripe):
    tok, _uid = await _user(client, db, "pm-def@x.com")
    a = (await _add(client, tok, "pm_a")).json()
    b = (await _add(client, tok, "pm_b")).json()
    assert a["is_default"] is True and b["is_default"] is False  # second isn't default

    sw = await client.post(f"/api/v1/wallet/payment-methods/{b['id']}/default", headers=_h(tok))
    assert sw.status_code == 200 and sw.json()["is_default"] is True
    listed = {
        m["id"]: m["is_default"]
        for m in (await client.get("/api/v1/wallet/payment-methods", headers=_h(tok))).json()
    }
    assert listed[b["id"]] is True and listed[a["id"]] is False


async def test_delete_detaches_and_reassigns_default(client, db, fake_stripe):
    tok, uid = await _user(client, db, "pm-del@x.com")
    a = (await _add(client, tok, "pm_a")).json()
    b = (await _add(client, tok, "pm_b")).json()
    # delete the default (a) -> remaining (b) becomes default
    d = await client.delete(f"/api/v1/wallet/payment-methods/{a['id']}", headers=_h(tok))
    assert d.status_code == 204
    rows = (await client.get("/api/v1/wallet/payment-methods", headers=_h(tok))).json()
    assert len(rows) == 1 and rows[0]["id"] == b["id"] and rows[0]["is_default"] is True


async def test_add_is_idempotent(client, db, fake_stripe):
    tok, uid = await _user(client, db, "pm-idem@x.com")
    first = await _add(client, tok, "pm_same")
    second = await _add(client, tok, "pm_same")
    assert first.json()["id"] == second.json()["id"]
    assert len(db("SELECT 1 FROM saved_payment_methods WHERE user_id=:u", u=uid)) == 1


# --- scoping / security ----------------------------------------------------- #
async def test_cross_user_add_forbidden(client, db, fake_stripe):
    tok_a, _ua = await _user(client, db, "pm-x@x.com")
    tok_b, _ub = await _user(client, db, "pm-y@x.com")
    await _add(client, tok_a, "pm_shared")
    a_setup = next(iter(INTENTS))
    await client.post("/api/v1/wallet/payment-methods/setup-intent", headers=_h(tok_b))
    r = await _submit(client, tok_b, a_setup)  # B names A's finished setup
    assert r.status_code == 403
    # and a card B saves cannot be one already recorded for A
    r2 = await _add(client, tok_b, "pm_shared")
    assert r2.status_code == 403


async def test_unfinished_setup_is_not_saved(client, db, fake_stripe):
    tok, uid = await _user(client, db, "pm-half@x.com")
    r = await _add(client, tok, "pm_half", status="requires_payment_method")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CARD_SETUP_INCOMPLETE"
    assert db("SELECT count(*) FROM saved_payment_methods WHERE user_id=:u", u=uid)[0][0] == 0


async def test_no_card_setup_yet_is_404_and_ids_are_validated(client, db, fake_stripe):
    tok, _uid = await _user(client, db, "pm-none@x.com")
    assert (await _submit(client, tok, "seti_neverstarted1")).status_code == 404
    assert (await _submit(client, tok, "pm_notasetup")).status_code == 422
    assert (await _submit(client, tok, "seti_../../customers")).status_code == 422


async def test_setup_needs_a_publishable_key_of_the_same_mode(client, db, fake_stripe, monkeypatch):
    """A test key cannot open a live card setup (and vice versa): say so before touching Stripe."""
    from app.core.config import get_settings

    s = get_settings()
    tok, uid = await _user(client, db, "pm-mode@x.com")
    for secret, publishable in [("rk_live_x", "pk_test_123"), ("sk_test_x", "pk_live_1"), ("", "")]:
        monkeypatch.setattr(s, "stripe_secret_key", secret, raising=False)
        monkeypatch.setattr(s, "stripe_publishable_key", publishable, raising=False)
        r = await client.post("/api/v1/wallet/payment-methods/setup-intent", headers=_h(tok))
        assert r.status_code == 503, (secret, publishable)
    assert db("SELECT count(*) FROM payment_customers WHERE user_id=:u", u=uid)[0][0] == 0
    monkeypatch.setattr(s, "stripe_secret_key", "rk_live_x", raising=False)
    monkeypatch.setattr(s, "stripe_publishable_key", "pk_live_1", raising=False)
    r = await client.post("/api/v1/wallet/payment-methods/setup-intent", headers=_h(tok))
    assert r.status_code == 200 and r.json()["publishable_key"] == "pk_live_1"


async def test_foreign_delete_404(client, db, fake_stripe):
    tok_a, _ua = await _user(client, db, "pm-fa@x.com")
    tok_b, _ub = await _user(client, db, "pm-fb@x.com")
    a = (await _add(client, tok_a, "pm_fa")).json()
    r = await client.delete(f"/api/v1/wallet/payment-methods/{a['id']}", headers=_h(tok_b))
    assert r.status_code == 404


# --- unconfigured / auth ---------------------------------------------------- #
async def test_503_when_stripe_unconfigured(client, db):
    # no fake_stripe -> Stripe is unconfigured (autouse fixture clears the keys)
    tok, _uid = await _user(client, db, "pm-503@x.com")
    assert (
        await client.post("/api/v1/wallet/payment-methods/setup-intent", headers=_h(tok))
    ).status_code == 503
    assert (await _submit(client, tok, "seti_abcdef1")).status_code == 404  # nothing started


async def test_requires_auth(client, db):
    assert (await client.get("/api/v1/wallet/payment-methods")).status_code == 401
    assert (
        await client.post("/api/v1/wallet/payment-methods", json={"setup_intent_id": "seti_x1"})
    ).status_code == 401


# --- the saved card is there to pay with ------------------------------------ #
async def test_saved_card_is_offered_again_at_checkout(client, db, fake_stripe):
    """Checkout only lists saved cards marked allow_redisplay=always, and prefills them only
    with a billing name and email: both come from the account when the card form had none."""
    tok, _uid = await _user(client, db, "pm-offer@x.com")
    r = await _add(client, tok, "pm_offer")
    assert r.status_code == 201, r.text
    assert OFFERED == [{"pm": "pm_offer", "name": "U", "email": "pm-offer@x.com"}]


async def test_offering_the_card_again_never_blocks_the_save(client, db, fake_stripe, monkeypatch):
    from app.core.errors import AppError

    async def refused(payment_method_id, *, name=None, email=None):
        raise AppError("PAYOUT_PROVIDER_ERROR", "Stripe error (403).", status_code=502)

    monkeypatch.setattr(gw, "offer_again_at_checkout", refused)
    tok, uid = await _user(client, db, "pm-noffer@x.com")
    assert (await _add(client, tok, "pm_noffer")).status_code == 201
    assert db("SELECT count(*) FROM saved_payment_methods WHERE user_id=:u", u=uid)[0][0] == 1


async def test_card_checkout_lists_saved_cards_once_there_is_one(
    client, db, fake_stripe, monkeypatch
):
    from app.services.integrations.payments import CheckoutResult

    seen: list = []

    async def fake_checkout(**kwargs):
        seen.append(kwargs.get("customer_id"))
        return CheckoutResult(
            provider_payment_id="cs_x", checkout_url="https://pay.t", status="pending"
        )

    monkeypatch.setattr(gw, "is_configured", lambda: True)
    monkeypatch.setattr(gw, "create_checkout", fake_checkout)
    tok, uid = await _user(client, db, "pm-pay@x.com")
    db("UPDATE kyc_verifications SET status='verified' WHERE user_id=:i", i=uid)

    async def deposit(key):
        r = await client.post(
            "/api/v1/wallet/deposit",
            json={"amount": 50, "method": "card"},
            headers={**_h(tok), "Idempotency-Key": key},
        )
        assert r.status_code == 200, r.text

    await deposit("dep-1")  # nothing saved yet: plain checkout
    await _add(client, tok, "pm_pay")
    await deposit("dep-2")  # now Checkout gets the customer and lists the card
    assert seen == [None, "cus_pm-pay"]


# --- resilience -------------------------------------------------------------- #
def _missing_customer():
    from app.core.errors import AppError

    return AppError(
        "PAYOUT_PROVIDER_ERROR",
        "Stripe error (400).",
        status_code=502,
        details={"code": "resource_missing", "param": "customer"},
    )


async def test_customer_from_switched_keys_is_replaced(client, db, fake_stripe, monkeypatch):
    """Keys moved from test to live (or to another account): the stored customer does not exist
    for the new key, so the investor gets a new one instead of a card form that never opens."""
    tok, uid = await _user(client, db, "pm-switch@x.com")
    db(
        "INSERT INTO payment_customers (user_id, provider, customer_id) "
        "VALUES (:u,'stripe','cus_old')",
        u=uid,
    )

    async def create_customer(*, email):
        return "cus_new"

    async def create_setup_intent(*, customer_id):
        if customer_id == "cus_old":
            raise _missing_customer()
        return {"id": "seti_2", "client_secret": "seti_2_secret_x"}

    monkeypatch.setattr(gw, "create_customer", create_customer)
    monkeypatch.setattr(gw, "create_setup_intent", create_setup_intent)
    r = await client.post("/api/v1/wallet/payment-methods/setup-intent", headers=_h(tok))
    assert r.status_code == 200, r.text
    assert r.json()["client_secret"] == "seti_2_secret_x"
    assert (
        db("SELECT customer_id FROM payment_customers WHERE user_id=:u", u=uid)[0][0] == "cus_new"
    )


async def test_a_failed_setup_keeps_the_customer(client, db, fake_stripe, monkeypatch):
    """A refused setup (e.g. a missing key permission) must not leave a new Stripe customer
    behind on every retry."""
    from app.core.errors import AppError

    made: list = []

    async def create_customer(*, email):
        made.append(email)
        return "cus_once"

    async def refused(*, customer_id):
        raise AppError("PAYOUT_PROVIDER_ERROR", "Stripe error (403).", status_code=502)

    monkeypatch.setattr(gw, "create_customer", create_customer)
    monkeypatch.setattr(gw, "create_setup_intent", refused)
    tok, uid = await _user(client, db, "pm-keep@x.com")
    for _ in range(2):
        r = await client.post("/api/v1/wallet/payment-methods/setup-intent", headers=_h(tok))
        assert r.status_code == 502
    assert made == ["pm-keep@x.com"]
    assert (
        db("SELECT customer_id FROM payment_customers WHERE user_id=:u", u=uid)[0][0] == "cus_once"
    )


async def test_same_setup_saved_twice_at_once_gives_one_card(client, db, fake_stripe, monkeypatch):
    """The other request commits first (simulated while this one waits on Stripe): no 500."""
    tok, uid = await _user(client, db, "pm-race@x.com")
    await client.post("/api/v1/wallet/payment-methods/setup-intent", headers=_h(tok))
    INTENTS["seti_race0001"] = {
        "customer": "cus_pm-race",
        "status": "succeeded",
        "payment_method": "pm_race",
    }

    async def slow_retrieve(payment_method_id):
        db(
            "INSERT INTO saved_payment_methods (user_id, provider, provider_customer_id, "
            "provider_payment_method_id, type, brand, last4, is_default) "
            "VALUES (:u,'stripe','cus_pm-race','pm_race','card','visa','4242',true)",
            u=uid,
        )
        return {"id": payment_method_id, "type": "card", "brand": "visa", "last4": "4242"}

    monkeypatch.setattr(gw, "retrieve_payment_method", slow_retrieve)
    r = await _submit(client, tok, "seti_race0001")
    assert r.status_code == 201, r.text
    assert db("SELECT count(*) FROM saved_payment_methods WHERE user_id=:u", u=uid)[0][0] == 1


async def test_why_card_saving_is_unavailable_is_logged(
    client, db, fake_stripe, monkeypatch, caplog
):
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "rk_live_x", raising=False)
    monkeypatch.setattr(s, "stripe_publishable_key", "pk_test_123", raising=False)
    tok, _uid = await _user(client, db, "pm-why@x.com")
    with caplog.at_level("WARNING"):
        r = await client.post("/api/v1/wallet/payment-methods/setup-intent", headers=_h(tok))
    assert r.status_code == 503
    assert "not the same mode" in caplog.text
    assert "pk_test_123" not in caplog.text and "rk_live_x" not in caplog.text
