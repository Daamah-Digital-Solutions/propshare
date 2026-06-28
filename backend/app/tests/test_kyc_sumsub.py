"""Phase 2 — DB-free unit tests for the Sumsub primitives.

Covers the automation core that can be proven without a DB/network:
signature verification, the idempotency-key property, and decision mapping.
The DB-backed flow (status flip, replay dedupe, KYC gate) is exercised against
Postgres via alembic + the integration acceptance run.
"""

from __future__ import annotations

import hashlib
import hmac

from app.services.integrations import kyc_sumsub as ss

SECRET = "whsec_test_secret"


def test_payload_digest_matches_hmac_sha256() -> None:
    body = b'{"type":"applicantReviewed"}'
    expected = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert ss.compute_payload_digest(SECRET, body) == expected


def test_verify_payload_accepts_correct_and_rejects_tampered() -> None:
    body = b'{"applicantId":"abc","type":"applicantReviewed"}'
    good = ss.compute_payload_digest(SECRET, body)
    assert ss.verify_payload(SECRET, body, good) is True
    assert ss.verify_payload(SECRET, body, good.upper()) is True  # case-insensitive
    assert ss.verify_payload(SECRET, body, "deadbeef") is False
    assert ss.verify_payload(SECRET, body + b" ", good) is False  # body changed
    assert ss.verify_payload(SECRET, body, "") is False
    assert ss.verify_payload("", body, good) is False


def test_idempotency_key_property() -> None:
    # Replays (identical body) collide -> processed once; distinct events differ.
    b1 = b'{"applicantId":"a","type":"applicantPending"}'
    b2 = b'{"applicantId":"a","type":"applicantReviewed"}'
    assert ss.compute_payload_digest(SECRET, b1) == ss.compute_payload_digest(SECRET, b1)
    assert ss.compute_payload_digest(SECRET, b1) != ss.compute_payload_digest(SECRET, b2)


def test_sign_request_is_deterministic_hmac() -> None:
    sig = ss.sign_request(SECRET, "1700000000", "POST", "/resources/applicants?levelName=x", b"{}")
    manual = hmac.new(
        SECRET.encode(),
        b"1700000000" + b"POST" + b"/resources/applicants?levelName=x" + b"{}",
        hashlib.sha256,
    ).hexdigest()
    assert sig == manual


def test_map_green_to_verified() -> None:
    out = ss.map_review_result(
        {"type": "applicantReviewed", "reviewResult": {"reviewAnswer": "GREEN"}}
    )
    assert out.status == "verified" and out.manual_review is False


def test_map_red_final_to_rejected_with_reason() -> None:
    out = ss.map_review_result(
        {
            "type": "applicantReviewed",
            "reviewResult": {
                "reviewAnswer": "RED",
                "reviewRejectType": "FINAL",
                "moderationComment": "Document unreadable",
            },
        }
    )
    assert out.status == "rejected"
    assert out.reason == "Document unreadable"


def test_map_red_retry_mentions_resubmit() -> None:
    out = ss.map_review_result(
        {
            "type": "applicantReviewed",
            "reviewResult": {"reviewAnswer": "RED", "reviewRejectType": "RETRY"},
        }
    )
    assert out.status == "rejected"
    assert "resubmit" in (out.reason or "")


def test_map_pending_to_submitted() -> None:
    assert ss.map_review_result({"type": "applicantPending"}).status == "submitted"


def test_map_on_hold_flags_manual_review() -> None:
    out = ss.map_review_result({"type": "applicantOnHold"})
    assert out.status == "submitted" and out.manual_review is True


def test_map_unknown_reviewed_answer_goes_to_manual_review() -> None:
    out = ss.map_review_result(
        {"type": "applicantReviewed", "reviewResult": {"reviewAnswer": "YELLOW"}}
    )
    assert out.manual_review is True
