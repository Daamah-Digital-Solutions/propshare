"""KYC service (Phase 2) — automatic, instant verification via Sumsub.

Flow:
  start_verification -> create/return a Sumsub applicant, mark status 'submitted',
                        return a WebSDK access token for the SPA to launch.
  process_webhook    -> the AUTOMATION CORE: idempotent + signature-gated (the
                        route verifies the signature). Maps Sumsub's decision and
                        flips kyc_verifications.status with NO human step.
  admin_decide       -> the exception path only (provider-flagged manual review).
"""

from __future__ import annotations

import datetime as dt
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import KycVerification
from app.models.base import KycStatus
from app.models.compliance import KycWebhookEvent
from app.services import notification_service
from app.services.integrations import kyc_sumsub


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


async def get_my_kyc(session: AsyncSession, user_id: uuid.UUID) -> KycVerification:
    res = await session.execute(select(KycVerification).where(KycVerification.user_id == user_id))
    row = res.scalar_one_or_none()
    if row is None:
        raise AppError("NOT_FOUND", "KYC record not found", status_code=404)
    return row


async def start_verification(session: AsyncSession, user_id: uuid.UUID) -> dict:
    """Create the Sumsub applicant (if needed), mark submitted, return an SDK token.

    Raises 503 KYC_NOT_CONFIGURED (honest degradation) when Sumsub isn't set up.
    """
    kyc = await get_my_kyc(session, user_id)
    if str(kyc.status) == "verified":
        raise AppError("KYC_ALREADY_VERIFIED", "Identity already verified.", status_code=409)

    external_user_id = str(user_id)
    if not kyc.provider_applicant_id:
        applicant_id = await kyc_sumsub.create_applicant(external_user_id)
        kyc.provider = "sumsub"
        kyc.provider_applicant_id = applicant_id

    token = await kyc_sumsub.create_access_token(external_user_id)

    if str(kyc.status) in ("pending", "rejected"):
        kyc.status = KycStatus.submitted
        kyc.submitted_at = _utcnow()
        kyc.manual_review_required = False
        kyc.rejection_reason = None

    await notification_service.notify(
        session,
        user_id=user_id,
        type="kyc",
        title="Verification started",
        message="Complete the steps in the verification window. Most checks are instant.",
    )
    await write_audit(
        session,
        action="kyc.start",
        entity_type="kyc_verification",
        entity_id=str(kyc.id),
        actor_id=user_id,
    )
    return {"sdk_token": token, "applicant_id": kyc.provider_applicant_id, "provider": "sumsub"}


async def process_webhook(session: AsyncSession, *, payload: dict, event_key: str) -> dict:
    """Idempotently apply a Sumsub decision. The route verifies the signature
    BEFORE calling this. ``event_key`` is the verified payload digest — replays
    share it, so they are processed exactly once."""
    # Idempotency: skip if we've already processed this exact delivery.
    seen = await session.execute(
        select(KycWebhookEvent.id).where(KycWebhookEvent.event_key == event_key)
    )
    if seen.first() is not None:
        return {"status": "duplicate"}

    applicant_id = payload.get("applicantId")
    session.add(
        KycWebhookEvent(
            event_key=event_key,
            provider="sumsub",
            applicant_id=applicant_id,
            type=payload.get("type"),
        )
    )

    # Locate the user's KYC row (by Sumsub applicant id, else externalUserId).
    kyc = await _find_kyc(session, payload)
    if kyc is None:
        await write_audit(
            session,
            action="kyc.webhook.unmatched",
            entity_type="kyc_verification",
            entity_id=applicant_id,
            after={"type": payload.get("type")},
        )
        return {"status": "ignored_unknown_applicant"}

    outcome = kyc_sumsub.map_review_result(payload)
    await _apply_outcome(session, kyc, outcome, source="webhook")
    return {"status": "processed", "result": str(kyc.status)}


async def _apply_outcome(
    session: AsyncSession,
    kyc: KycVerification,
    outcome: kyc_sumsub.ReviewOutcome,
    *,
    source: str,
) -> None:
    """Apply a mapped Sumsub decision to a KYC row — SHARED by the webhook and the
    reconcile/sync cron so both flip status identically: verify (+ materialize any pending
    family/estate/gift allocations), reject (+ reason), or leave under review. Notifies the
    user and audits. ``source`` tags the audit action (``kyc.webhook`` | ``kyc.sync``)."""
    before = {"status": str(kyc.status), "manual_review_required": kyc.manual_review_required}
    kyc.last_review_answer = outcome.answer
    kyc.manual_review_required = outcome.manual_review
    if outcome.status == "verified":
        kyc.status = KycStatus.verified
        kyc.verified_at = _utcnow()
        kyc.rejection_reason = None
        await _materialize_family(session, kyc.user_id)
    elif outcome.status == "rejected":
        kyc.status = KycStatus.rejected
        kyc.rejection_reason = outcome.reason
    else:
        # submitted / under review (incl. manual-review hold) — no terminal change
        if str(kyc.status) not in ("verified", "rejected"):
            kyc.status = KycStatus.submitted

    await _notify_outcome(session, kyc.user_id, outcome)
    await write_audit(
        session,
        action=f"kyc.{source}",
        entity_type="kyc_verification",
        entity_id=str(kyc.id),
        before=before,
        after={
            "status": str(kyc.status),
            "manual_review_required": kyc.manual_review_required,
            "answer": outcome.answer,
        },
    )


async def sync_pending_applicants(session: AsyncSession, *, limit: int = 500) -> dict:
    """Reconcile applicants still under review against Sumsub's LIVE decision — a safety net
    for a missed or duplicated ``applicantReviewed`` webhook (the webhook stays the primary
    path). For each non-terminal row it polls ``GET /applicants/{id}/status`` and, only when
    the review is COMPLETED, applies the exact transition the webhook would (GREEN → verified
    + materialize pending allocations; RED → rejected). Idempotent: verified/rejected rows are
    never re-queried, and an under-review applicant is left untouched.

    Cron-safe. No-op (``configured: False``) when Sumsub isn't set up (honest degradation).
    A per-applicant provider/network error is counted and skipped — one bad row never aborts
    the batch (each row's own read happens before any write, so the session stays clean)."""
    if not kyc_sumsub.is_configured():
        return {
            "configured": False,
            "checked": 0,
            "verified": 0,
            "rejected": 0,
            "pending": 0,
            "errors": 0,
        }
    rows = (
        (
            await session.execute(
                select(KycVerification)
                .where(
                    KycVerification.provider == "sumsub",
                    KycVerification.provider_applicant_id.isnot(None),
                    KycVerification.status.in_([KycStatus.pending, KycStatus.submitted]),
                )
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    verified = rejected = pending = errors = 0
    for kyc in rows:
        try:
            status = await kyc_sumsub.get_applicant_status(kyc.provider_applicant_id)
        except httpx.HTTPError:
            errors += 1
            continue
        if str(status.get("reviewStatus")) != "completed":
            pending += 1
            continue
        outcome = kyc_sumsub.map_review_result(
            {
                "type": "applicantReviewed",
                "applicantId": kyc.provider_applicant_id,
                "reviewResult": status.get("reviewResult") or {},
            }
        )
        if outcome.status == "verified":
            await _apply_outcome(session, kyc, outcome, source="sync")
            verified += 1
        elif outcome.status == "rejected":
            await _apply_outcome(session, kyc, outcome, source="sync")
            rejected += 1
        else:
            pending += 1
    return {
        "configured": True,
        "checked": len(rows),
        "verified": verified,
        "rejected": rejected,
        "pending": pending,
        "errors": errors,
    }


async def _find_kyc(session: AsyncSession, payload: dict) -> KycVerification | None:
    applicant_id = payload.get("applicantId")
    if applicant_id:
        res = await session.execute(
            select(KycVerification).where(KycVerification.provider_applicant_id == applicant_id)
        )
        row = res.scalar_one_or_none()
        if row is not None:
            return row
    external = payload.get("externalUserId")
    if external:
        try:
            uid = uuid.UUID(str(external))
        except ValueError:
            return None
        res = await session.execute(select(KycVerification).where(KycVerification.user_id == uid))
        return res.scalar_one_or_none()
    return None


async def _notify_outcome(
    session: AsyncSession, user_id: uuid.UUID, outcome: kyc_sumsub.ReviewOutcome
) -> None:
    # A final decision (verified/rejected) emails (security category); "under review" is
    # a status update — in-app only.
    email_category: str | None = "security"
    if outcome.status == "verified":
        title, message = "Identity verified", "Your identity has been verified. You're all set."
    elif outcome.status == "rejected":
        title, message = (
            "Verification unsuccessful",
            outcome.reason or "Please review and resubmit.",
        )
    elif outcome.manual_review:
        title, message = "Verification under review", "Your documents are being reviewed."
        email_category = None
    else:
        return
    await notification_service.notify(
        session,
        user_id=user_id,
        type="kyc",
        title=title,
        message=message,
        email_category=email_category,
    )


async def _materialize_family(session: AsyncSession, user_id: uuid.UUID) -> None:
    """On KYC-verify, convert any pending family allocations for this user into real
    ledger moves (Phase 10) — plus any pending ESTATE inheritances (Group 4) and pending
    GIFTS (Group 5). Lazy import avoids a module-load cycle."""
    from app.services import estate_service, family_service, gift_service

    await family_service.materialize_for_user(session, user_id=user_id)
    await estate_service.materialize_for_user(session, user_id=user_id)
    await gift_service.materialize_for_user(session, user_id=user_id)


# Admin exception path -------------------------------------------------------- #
async def admin_decide(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    approve: bool,
    actor_id: uuid.UUID | None,
    reason: str | None = None,
) -> KycVerification:
    kyc = await get_my_kyc(session, user_id)
    before = {"status": str(kyc.status)}
    if approve:
        kyc.status = KycStatus.verified
        kyc.verified_at = _utcnow()
        kyc.rejection_reason = None
        await _materialize_family(session, user_id)
    else:
        kyc.status = KycStatus.rejected
        kyc.rejection_reason = reason or "Rejected by reviewer"
    kyc.manual_review_required = False
    await _notify_outcome(
        session,
        user_id,
        kyc_sumsub.ReviewOutcome(
            str(kyc.status), False, kyc.rejection_reason, kyc.last_review_answer
        ),
    )
    await write_audit(
        session,
        action="kyc.admin_decide",
        entity_type="kyc_verification",
        entity_id=str(kyc.id),
        actor_id=actor_id,
        before=before,
        after={"status": str(kyc.status)},
    )
    return kyc
