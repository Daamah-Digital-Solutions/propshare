"""DB-backed test for the KYC reconcile/sync cron (kyc_service.sync_pending_applicants).

Safety net for a missed/duplicated Sumsub webhook: polling the applicant's LIVE status
flips a still-submitted applicant to verified on GREEN, leaves an under-review applicant
untouched, and is a no-op when Sumsub isn't configured (honest degradation)."""

from __future__ import annotations

import pytest

from app.services import kyc_service
from app.services.integrations import kyc_sumsub

PW = "Passw0rd!23"


async def _register_submitted(client, db, email: str, applicant_id: str) -> str:
    """Register a user, then push their KYC row into the 'submitted' (under-review) state
    with a Sumsub applicant id — as if a start_verification happened but the webhook was
    never delivered."""
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "S"}
    )
    uid = db("SELECT id FROM users WHERE email=:e", e=email)[0][0]
    db(
        "UPDATE kyc_verifications SET provider='sumsub', provider_applicant_id=:a, "
        "status='submitted', submitted_at=now() WHERE user_id=:i",
        a=applicant_id,
        i=uid,
    )
    return uid


@pytest.mark.asyncio
async def test_sync_verifies_completed_green(client, db, asession, monkeypatch):
    uid = await _register_submitted(client, db, "sync-green@ex.com", "appl-green")

    async def _status(applicant_id: str) -> dict:
        assert applicant_id == "appl-green"
        return {"reviewStatus": "completed", "reviewResult": {"reviewAnswer": "GREEN"}}

    monkeypatch.setattr(kyc_sumsub, "is_configured", lambda: True)
    monkeypatch.setattr(kyc_sumsub, "get_applicant_status", _status)

    result = await kyc_service.sync_pending_applicants(asession)
    await asession.commit()

    assert result["configured"] is True
    assert result["checked"] == 1
    assert result["verified"] == 1
    assert db("SELECT status FROM kyc_verifications WHERE user_id=:i", i=uid)[0][0] == "verified"
    assert db("SELECT verified_at FROM kyc_verifications WHERE user_id=:i", i=uid)[0][0] is not None


@pytest.mark.asyncio
async def test_sync_leaves_under_review_untouched(client, db, asession, monkeypatch):
    uid = await _register_submitted(client, db, "sync-pending@ex.com", "appl-pending")

    async def _status(applicant_id: str) -> dict:
        return {"reviewStatus": "pending", "reviewResult": {}}

    monkeypatch.setattr(kyc_sumsub, "is_configured", lambda: True)
    monkeypatch.setattr(kyc_sumsub, "get_applicant_status", _status)

    result = await kyc_service.sync_pending_applicants(asession)
    await asession.commit()

    assert result["pending"] == 1
    assert result["verified"] == 0
    assert db("SELECT status FROM kyc_verifications WHERE user_id=:i", i=uid)[0][0] == "submitted"


@pytest.mark.asyncio
async def test_sync_noop_when_unconfigured(client, db, asession):
    # Sumsub secrets are cleared by the autouse fixture -> is_configured() is False.
    await _register_submitted(client, db, "sync-off@ex.com", "appl-off")
    result = await kyc_service.sync_pending_applicants(asession)
    assert result == {
        "configured": False,
        "checked": 0,
        "verified": 0,
        "rejected": 0,
        "pending": 0,
        "errors": 0,
    }
