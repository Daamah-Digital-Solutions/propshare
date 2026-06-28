"""Group 3 — DB-backed tests for saved payment methods (PCI-safe tokenization).

Acceptance: add stores only TOKENS + safe metadata (no card data, no token exposed in the
API); first method is default; set-default switches; delete detaches + reassigns default;
idempotent re-add; user-scoped (cross-user add → 403, foreign delete → 404); honest 503
when Stripe is unconfigured; auth required.

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


@pytest.fixture
def fake_stripe(monkeypatch):
    """Simulate a configured Stripe by replacing the gateway seam functions."""

    async def create_customer(*, email):
        return f"cus_{email.split('@')[0]}"

    async def create_setup_intent(*, customer_id):
        return {"id": "seti_1", "client_secret": "seti_1_secret_abc"}

    async def attach_payment_method(*, payment_method_id, customer_id):
        return None

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

    monkeypatch.setattr(gw, "create_customer", create_customer)
    monkeypatch.setattr(gw, "create_setup_intent", create_setup_intent)
    monkeypatch.setattr(gw, "attach_payment_method", attach_payment_method)
    monkeypatch.setattr(gw, "retrieve_payment_method", retrieve_payment_method)
    monkeypatch.setattr(gw, "detach_payment_method", detach_payment_method)
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "stripe_publishable_key", "pk_test_123", raising=False)
    yield


async def _add(client, tok, pm: str):
    return await client.post(
        "/api/v1/wallet/payment-methods", json={"payment_method_id": pm}, headers=_h(tok)
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
    r = await _add(client, tok_b, "pm_shared")  # same token, different user
    assert r.status_code == 403


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
    assert (await _add(client, tok, "pm_x")).status_code == 503


async def test_requires_auth(client, db):
    assert (await client.get("/api/v1/wallet/payment-methods")).status_code == 401
    assert (
        await client.post("/api/v1/wallet/payment-methods", json={"payment_method_id": "pm_x"})
    ).status_code == 401
