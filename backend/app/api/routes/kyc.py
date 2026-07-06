"""KYC routes (Phase 2) — automatic verification via Sumsub.

- GET  /kyc/me            own status (live).
- POST /kyc/me/start      create applicant + return a WebSDK token (503 if Sumsub
                          isn't configured — honest degradation).
- POST /kyc/webhook/sumsub  the AUTOMATION CORE: signature-verified + idempotent;
                          flips status with no human step.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request

from app.api.deps import AdminOrCronDep, PrincipalDep, SessionDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.kyc import KycStartOut, KycStatusOut
from app.services import kyc_service
from app.services.integrations import kyc_sumsub

router = APIRouter(prefix="/api/v1/kyc", tags=["kyc"])


@router.get("/me", response_model=KycStatusOut)
async def my_kyc(principal: PrincipalDep, session: SessionDep):
    kyc = await kyc_service.get_my_kyc(session, principal.user_id)
    return KycStatusOut(
        status=str(kyc.status),
        manual_review_required=kyc.manual_review_required,
        provider=kyc.provider,
        submitted_at=kyc.submitted_at,
        verified_at=kyc.verified_at,
        rejection_reason=kyc.rejection_reason,
    )


@router.post("/me/start", response_model=KycStartOut)
async def start_kyc(principal: PrincipalDep, session: SessionDep):
    result = await kyc_service.start_verification(session, principal.user_id)
    return KycStartOut(**result)


@router.post("/maintenance/sync")
async def sync_kyc(caller: AdminOrCronDep, session: SessionDep) -> dict:
    """Reconcile applicants still under review against Sumsub's live decision — the safety
    net for a missed/duplicated ``applicantReviewed`` webhook. Cron target (admin OR a valid
    ``X-Cron-Secret``); idempotent; also runs on demand. No-op if Sumsub isn't configured."""
    return await kyc_service.sync_pending_applicants(session)


@router.post("/webhook/sumsub")
async def sumsub_webhook(request: Request, session: SessionDep) -> dict:
    body = await request.body()
    secret = get_settings().sumsub_webhook_secret
    if not secret:
        # Can't verify without the webhook secret — degrade honestly.
        raise AppError("KYC_NOT_CONFIGURED", "KYC webhook is not configured.", status_code=503)

    digest = request.headers.get("x-payload-digest", "")
    if not kyc_sumsub.verify_payload(secret, body, digest):
        raise AppError("WEBHOOK_SIGNATURE_INVALID", "Invalid webhook signature.", status_code=401)

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError("BAD_PAYLOAD", "Webhook body is not valid JSON.", status_code=400) from exc

    # The verified digest is a deterministic per-delivery key → idempotency.
    return await kyc_service.process_webhook(session, payload=payload, event_key=digest.lower())
