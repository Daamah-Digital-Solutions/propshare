"""Phase 4 — DB-free unit tests for the payment-provider signature verification
and decision mapping (the automation core that needs no DB/network)."""

from __future__ import annotations

import hashlib
import hmac
import json

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
