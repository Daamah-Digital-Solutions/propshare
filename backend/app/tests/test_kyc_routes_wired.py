"""Phase 2 — KYC routes are wired; webhook is signature-gated and degrades
honestly. No DB needed (auth/signature checks fire before any DB access)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services.integrations import kyc_sumsub

EXPECTED_PATHS = {
    "/api/v1/kyc/me",
    "/api/v1/kyc/me/start",
    "/api/v1/kyc/maintenance/sync",
    "/api/v1/kyc/webhook/sumsub",
    "/api/v1/admin/kyc",
    "/api/v1/admin/kyc/{user_id}/decision",
}


def test_kyc_paths_in_openapi() -> None:
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
    missing = EXPECTED_PATHS - set(spec["paths"].keys())
    assert not missing, f"missing OpenAPI paths: {sorted(missing)}"


def test_kyc_me_requires_auth() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/kyc/me").status_code == 401


def test_admin_kyc_requires_auth() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/kyc").status_code == 401


def test_webhook_503_when_not_configured() -> None:
    # No SUMSUB_WEBHOOK_SECRET in the test env -> honest 503, no DB touched.
    with TestClient(app) as client:
        resp = client.post("/api/v1/kyc/webhook/sumsub", content=b"{}")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "KYC_NOT_CONFIGURED"


def test_webhook_rejects_bad_signature(monkeypatch) -> None:
    # Configure a webhook secret, then send a wrong digest -> 401 before any DB.
    monkeypatch.setattr(get_settings(), "sumsub_webhook_secret", "whsec_test", raising=False)
    body = b'{"applicantId":"x","type":"applicantReviewed"}'
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/kyc/webhook/sumsub",
            content=body,
            headers={"x-payload-digest": "not-the-real-digest"},
        )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"
    # Sanity: the correct digest would have verified (pure check, no DB).
    good = kyc_sumsub.compute_payload_digest("whsec_test", body)
    assert kyc_sumsub.verify_payload("whsec_test", body, good)
