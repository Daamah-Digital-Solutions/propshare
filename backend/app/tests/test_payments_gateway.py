"""Phase 4 — DB-free unit tests for the payment-provider signature verification
and decision mapping (the automation core that needs no DB/network)."""

from __future__ import annotations

import decimal
import hashlib
import hmac
import json
import uuid

import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.integrations.payments import nowpayments_gateway as nowp
from app.services.integrations.payments import stripe_gateway as stripe


def _stripe_header(secret: str, body: bytes, ts: str = "1700000000") -> str:
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def test_stripe_verifies_and_maps_paid_session(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)
    event = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_1",
                "client_reference_id": "11111111-1111-1111-1111-111111111111",
                "payment_status": "paid",
                "amount_total": 5000,
                "currency": "usd",
            }
        },
    }
    body = json.dumps(event).encode()
    out = stripe.verify_and_parse(body, _stripe_header("whsec_t", body))
    assert out.status == "succeeded"
    assert out.captured_amount == 50  # 5000 cents -> $50
    assert out.order_id == "11111111-1111-1111-1111-111111111111"
    assert out.event_id == "evt_1"


def test_stripe_rejects_forged_signature(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_t", raising=False)
    body = b'{"id":"evt_2","type":"checkout.session.completed","data":{"object":{}}}'
    with pytest.raises(AppError) as exc:
        stripe.verify_and_parse(body, "t=1700000000,v1=deadbeef")
    assert exc.value.code == "WEBHOOK_SIGNATURE_INVALID"
    assert exc.value.status_code == 401


# --- Stripe Connect (money out) ---------------------------------------------- #
def test_each_stripe_endpoint_is_verified_with_its_own_secret(monkeypatch) -> None:
    """Stripe gives the deposits endpoint and the Connect endpoint different secrets."""
    s = get_settings()
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_main", raising=False)
    monkeypatch.setattr(s, "stripe_connect_webhook_secret", "whsec_connect", raising=False)
    event = {
        "id": "evt_c1",
        "type": "account.updated",
        "account": "acct_1",
        "data": {"object": {"id": "acct_1"}},
    }
    body = json.dumps(event).encode()
    out = stripe.parse_payout_event(body, _stripe_header("whsec_connect", body))
    assert (out.kind, out.account_id) == ("account", "acct_1")
    # the deposits endpoint does not take the Connect endpoint's signature
    with pytest.raises(AppError) as exc:
        stripe.verify_and_parse(body, _stripe_header("whsec_connect", body))
    assert exc.value.code == "WEBHOOK_SIGNATURE_INVALID"
    with pytest.raises(AppError) as exc:
        stripe.parse_payout_event(body, _stripe_header("whsec_other", body))
    assert exc.value.status_code == 401


def test_connect_endpoint_takes_the_single_cli_secret(monkeypatch) -> None:
    """`stripe listen` signs everything it forwards with one secret (local development)."""
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_cli", raising=False)
    body = json.dumps(
        {"id": "evt_c2", "type": "account.updated", "data": {"object": {"id": "acct_2"}}}
    ).encode()
    assert stripe.parse_payout_event(body, _stripe_header("whsec_cli", body)).kind == "account"


def test_connect_endpoint_without_any_secret_is_unavailable() -> None:
    body = b'{"id":"evt_c3","type":"account.updated","data":{"object":{}}}'
    with pytest.raises(AppError) as exc:
        stripe.parse_payout_event(body, _stripe_header("whsec_x", body))
    assert exc.value.status_code == 503


def test_payout_events_name_the_connected_account(monkeypatch) -> None:
    monkeypatch.setattr(
        get_settings(), "stripe_connect_webhook_secret", "whsec_connect", raising=False
    )
    event = {
        "id": "evt_p1",
        "type": "payout.failed",
        "account": "acct_9",
        "data": {"object": {"id": "po_1", "metadata": {"withdrawal_id": "w1"}}},
    }
    body = json.dumps(event).encode()
    out = stripe.parse_payout_event(body, _stripe_header("whsec_connect", body))
    assert (out.kind, out.status, out.provider_payout_id) == ("payout", "failed", "po_1")
    assert (out.withdrawal_id, out.account_id) == ("w1", "acct_9")


def test_events_stripe_no_longer_sends_are_not_payout_outcomes(monkeypatch) -> None:
    """transfer.paid / transfer.failed were retired and payout.returned never existed."""
    monkeypatch.setattr(
        get_settings(), "stripe_connect_webhook_secret", "whsec_connect", raising=False
    )
    for etype in ("transfer.paid", "transfer.failed", "payout.returned", "charge.refunded"):
        body = json.dumps({"id": etype, "type": etype, "data": {"object": {"id": "x"}}}).encode()
        out = stripe.parse_payout_event(body, _stripe_header("whsec_connect", body))
        assert out.kind == "ignored", etype


@pytest.mark.asyncio
async def test_a_transfer_is_final_once_stripe_accepts_it(monkeypatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test_x", raising=False)
    monkeypatch.setattr(s, "stripe_webhook_secret", "whsec_main", raising=False)
    sent: dict = {}

    async def fake_post(path, data, **kw):
        sent.update(path=path, data=data, **kw)
        return {"id": "tr_123"}

    monkeypatch.setattr(stripe, "_post", fake_post)
    out = await stripe.create_payout(
        withdrawal_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        account_id="acct_1",
        amount=decimal.Decimal("12.34"),
        currency="USD",
        idempotency_key="k1",
    )
    assert (out.provider_payout_id, out.status) == ("tr_123", "settled")
    assert (sent["path"], sent["idempotency_key"]) == ("transfers", "k1")
    assert (sent["data"]["amount"], sent["data"]["destination"]) == ("1234", "acct_1")


def test_nowpayments_signature_is_sorted_hmac_sha512() -> None:
    secret = "ipn_secret"
    body = b'{"payment_status":"finished","order_id":"x","payment_id":99}'
    expected = hmac.new(
        secret.encode(),
        json.dumps(json.loads(body), sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha512,
    ).hexdigest()
    assert nowp.compute_signature(secret, body) == expected


def test_nowpayments_verifies_finished_and_maps_amount(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "nowpayments_ipn_secret", "ipn_t", raising=False)
    payload = {
        "payment_id": 555,
        "order_id": "22222222-2222-2222-2222-222222222222",
        "payment_status": "finished",
        "price_amount": 75.0,
        "price_currency": "usd",
    }
    body = json.dumps(payload).encode()
    sig = nowp.compute_signature("ipn_t", body)
    out = nowp.verify_and_parse(body, sig)
    assert out.status == "succeeded"
    assert out.captured_amount == 75
    assert out.order_id == "22222222-2222-2222-2222-222222222222"
    assert out.event_id == "555:finished"


def test_nowpayments_rejects_bad_signature(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "nowpayments_ipn_secret", "ipn_t", raising=False)
    body = b'{"payment_id":1,"payment_status":"finished"}'
    with pytest.raises(AppError) as exc:
        nowp.verify_and_parse(body, "wrong")
    assert exc.value.code == "WEBHOOK_SIGNATURE_INVALID"


def test_nowpayments_status_mapping(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "nowpayments_ipn_secret", "ipn_t", raising=False)
    for ps, expected in [
        ("finished", "succeeded"),
        ("failed", "failed"),
        ("expired", "failed"),
        ("partially_paid", "ignored"),
        ("confirming", "pending"),
    ]:
        body = json.dumps({"payment_id": 1, "payment_status": ps}).encode()
        out = nowp.verify_and_parse(body, nowp.compute_signature("ipn_t", body))
        assert out.status == expected, ps
