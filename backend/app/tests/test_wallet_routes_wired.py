"""Phase 4 — wallet/payment routes are wired + protected (DB-free)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

EXPECTED_PATHS = {
    "/api/v1/wallet/me",
    "/api/v1/wallet/deposit",
    "/api/v1/wallet/transactions",
    "/api/v1/payments/{payment_id}",
    "/api/v1/payments/webhooks/stripe",
    "/api/v1/payments/webhooks/nowpayments",
}


def test_payment_paths_in_openapi() -> None:
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
    missing = EXPECTED_PATHS - set(spec["paths"].keys())
    assert not missing, f"missing OpenAPI paths: {sorted(missing)}"


def test_wallet_requires_auth() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/wallet/me").status_code == 401
        assert client.get("/api/v1/wallet/transactions").status_code == 401
        assert (
            client.post("/api/v1/wallet/deposit", json={"amount": 10, "method": "card"}).status_code
            == 401
        )


def test_webhooks_503_when_providers_unconfigured() -> None:
    # No Stripe/NOWPayments secrets in the test env -> honest 503, no DB touched.
    with TestClient(app) as client:
        s = client.post("/api/v1/payments/webhooks/stripe", content=b"{}")
        n = client.post("/api/v1/payments/webhooks/nowpayments", content=b"{}")
    assert s.status_code == 503 and s.json()["error"]["code"] == "PAYMENTS_NOT_CONFIGURED"
    assert n.status_code == 503 and n.json()["error"]["code"] == "PAYMENTS_NOT_CONFIGURED"
