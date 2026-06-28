"""DB-backed KYC automation test: a GREEN webhook flips status to verified with
NO human step, and a replayed (identical) delivery is a no-op (idempotent)."""

from __future__ import annotations

import json

import pytest

from app.core.config import get_settings
from app.services.integrations import kyc_sumsub

PW = "Passw0rd!23"


@pytest.mark.asyncio
async def test_green_webhook_verifies_then_replay_is_noop(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "sumsub_webhook_secret", "whsec_test", raising=False)

    await client.post(
        "/api/v1/auth/register", json={"email": "kyc@ex.com", "password": PW, "full_name": "K"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e="kyc@ex.com")[0][0]
    assert db("SELECT status FROM kyc_verifications WHERE user_id=:i", i=uid)[0][0] == "pending"

    # Sumsub "applicantReviewed / GREEN" — matched to our user via externalUserId.
    payload = {
        "type": "applicantReviewed",
        "externalUserId": str(uid),
        "reviewResult": {"reviewAnswer": "GREEN"},
    }
    body = json.dumps(payload).encode()
    digest = kyc_sumsub.compute_payload_digest("whsec_test", body)
    headers = {"x-payload-digest": digest, "content-type": "application/json"}

    first = await client.post("/api/v1/kyc/webhook/sumsub", content=body, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["result"] == "verified"
    assert db("SELECT status FROM kyc_verifications WHERE user_id=:i", i=uid)[0][0] == "verified"
    assert db("SELECT count(*) FROM kyc_webhook_events")[0][0] == 1

    # Replay the EXACT same delivery -> deduped, no second processing, status unchanged.
    second = await client.post("/api/v1/kyc/webhook/sumsub", content=body, headers=headers)
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert db("SELECT count(*) FROM kyc_webhook_events")[0][0] == 1
    assert db("SELECT status FROM kyc_verifications WHERE user_id=:i", i=uid)[0][0] == "verified"


@pytest.mark.asyncio
async def test_unverified_user_starts_pending(client, db):
    """Sanity: a freshly registered user is 'pending' until the webhook verifies."""
    await client.post(
        "/api/v1/auth/register", json={"email": "pend@ex.com", "password": PW, "full_name": "P"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e="pend@ex.com")[0][0]
    assert db("SELECT status FROM kyc_verifications WHERE user_id=:i", i=uid)[0][0] == "pending"
