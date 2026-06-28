"""Sumsub KYC integration (Phase 2).

Provides applicant creation + WebSDK access tokens for the verification flow, and
the webhook primitives (signature verification + decision mapping) that drive the
**automatic** status update. If Sumsub isn't configured yet, callers raise an
honest 503 (same pattern as OAuth) — the build never blocks on credentials.

Signing (outbound REST): HMAC-SHA256(secret, ts + METHOD + path+query + body),
sent as X-App-Token / X-App-Access-Ts / X-App-Access-Sig.
Webhook (inbound): Sumsub sends X-Payload-Digest = HMAC-SHA256(webhook_secret,
rawBody) hex; we recompute and constant-time compare.

The signing/verify/mapping helpers are pure (no DB/FastAPI) and unit-tested.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.errors import AppError


def is_configured() -> bool:
    return get_settings().sumsub_configured


def _require_configured() -> None:
    if not is_configured():
        raise AppError("KYC_NOT_CONFIGURED", "KYC verification is not configured.", status_code=503)


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested without network/DB)
# --------------------------------------------------------------------------- #
def sign_request(secret: str, ts: str, method: str, path_with_query: str, body: bytes) -> str:
    msg = ts.encode() + method.upper().encode() + path_with_query.encode() + body
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def compute_payload_digest(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_payload(secret: str, body: bytes, provided_digest: str) -> bool:
    if not secret or not provided_digest:
        return False
    expected = compute_payload_digest(secret, body)
    return hmac.compare_digest(expected, provided_digest.strip().lower())


@dataclass(frozen=True)
class ReviewOutcome:
    """Mapped decision. ``status`` ∈ pending|submitted|verified|rejected."""

    status: str
    manual_review: bool
    reason: str | None
    answer: str | None


def map_review_result(payload: dict) -> ReviewOutcome:
    typ = payload.get("type", "")
    rr = payload.get("reviewResult") or {}
    answer = rr.get("reviewAnswer")
    reject_type = rr.get("reviewRejectType")

    if typ == "applicantReviewed":
        if answer == "GREEN":
            return ReviewOutcome("verified", False, None, answer)
        if answer == "RED":
            labels = rr.get("rejectLabels") or []
            comment = rr.get("moderationComment") or rr.get("clientComment")
            reason = comment or (", ".join(labels) if labels else "Verification failed")
            if reject_type == "RETRY":
                reason = f"{reason} (you may resubmit)"
            return ReviewOutcome("rejected", False, reason, answer)
        # Unknown answer on a "reviewed" event → route to manual review.
        return ReviewOutcome("submitted", True, None, answer)

    if typ in ("applicantOnHold", "applicantActionOnHold"):
        return ReviewOutcome("submitted", True, None, answer)

    if typ in ("applicantPending", "applicantCreated", "applicantActionPending"):
        return ReviewOutcome("submitted", False, None, answer)

    # Any other event type leaves the applicant "submitted" (under review).
    return ReviewOutcome("submitted", False, None, answer)


# --------------------------------------------------------------------------- #
# Outbound REST (network) — require configuration
# --------------------------------------------------------------------------- #
async def _request(method: str, path_with_query: str, body: bytes = b"") -> httpx.Response:
    _require_configured()
    s = get_settings()
    ts = str(int(time.time()))
    headers = {
        "X-App-Token": s.sumsub_app_token,
        "X-App-Access-Ts": ts,
        "X-App-Access-Sig": sign_request(s.sumsub_secret_key, ts, method, path_with_query, body),
        "Accept": "application/json",
    }
    if body:
        headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(base_url=s.sumsub_base_url, timeout=15) as client:
        resp = await client.request(method, path_with_query, content=body, headers=headers)
        resp.raise_for_status()
        return resp


async def create_applicant(external_user_id: str) -> str:
    """Create (or return) a Sumsub applicant for our user; returns the applicant id."""
    s = get_settings()
    level = s.sumsub_level_name
    body = f'{{"externalUserId":"{external_user_id}"}}'.encode()
    resp = await _request("POST", f"/resources/applicants?levelName={level}", body)
    return str(resp.json()["id"])


async def create_access_token(external_user_id: str) -> str:
    """Mint a short-lived WebSDK access token for the applicant."""
    s = get_settings()
    level = s.sumsub_level_name
    path = f"/resources/accessTokens?userId={external_user_id}&levelName={level}&ttlInSecs=600"
    resp = await _request("POST", path)
    return str(resp.json()["token"])
