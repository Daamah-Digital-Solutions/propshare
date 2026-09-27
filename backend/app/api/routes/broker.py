"""Broker routes (Phase 11) — referrals, commissions and leads.

All endpoints require the admin-approved ``broker`` active role (DB re-checked at action
time). Brokers fetch their shareable code, their dashboard stats, their referred-client
list and their commission ledger, and keep their "Listings & Referrals" table: clients they
invite (the invitation carries their share link; linking still happens only at sign-up) and
properties / projects they introduce for listing (reviewed by staff). Commission accrual
itself happens server-side inside the Phase-5/Phase-6 money flows — there is no endpoint
that mints a commission, and no money attaches to a lead.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import Principal, SessionDep, require_active_role_db
from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.broker import (
    BrokerDashboardOut,
    BrokerLeadListOut,
    BrokerLeadOut,
    ClientInviteIn,
    CommissionItemOut,
    CommissionListOut,
    ReferralCodeOut,
    ReferralItemOut,
    ReferralListOut,
)
from app.services import broker_lead_service, broker_service

router = APIRouter(prefix="/api/v1/broker", tags=["broker"])

BrokerRoleDep = Annotated[Principal, Depends(require_active_role_db("broker"))]


@router.get("/referral-code", response_model=ReferralCodeOut)
async def referral_code(session: SessionDep, principal: BrokerRoleDep):
    code = await broker_service.get_or_create_code(session, principal.user_id)
    base = get_settings().app_base_url.rstrip("/")
    return ReferralCodeOut(code=code.code, share_link=f"{base}/auth?ref={code.code}")


@router.get("/dashboard", response_model=BrokerDashboardOut)
async def dashboard(session: SessionDep, principal: BrokerRoleDep):
    return BrokerDashboardOut(**await broker_service.dashboard(session, principal.user_id))


@router.get("/referrals", response_model=ReferralListOut)
async def referrals(session: SessionDep, principal: BrokerRoleDep):
    rows = await broker_service.list_referrals(session, principal.user_id)
    return ReferralListOut(items=[ReferralItemOut(**r) for r in rows], total=len(rows))


@router.get("/commissions", response_model=CommissionListOut)
async def commissions(
    session: SessionDep, principal: BrokerRoleDep, limit: int = 50, offset: int = 0
):
    items, total = await broker_service.list_commissions(
        session, principal.user_id, limit=limit, offset=offset
    )
    return CommissionListOut(items=[CommissionItemOut(**i) for i in items], total=total)


# --- Listings & Referrals ----------------------------------------------------------------- #
@router.get("/leads", response_model=BrokerLeadListOut)
async def my_leads(session: SessionDep, principal: BrokerRoleDep):
    rows = await broker_lead_service.list_for_broker(session, principal.user_id)
    return BrokerLeadListOut(
        items=[BrokerLeadOut(**broker_lead_service.serialize(r)) for r in rows], total=len(rows)
    )


@router.post("/leads/client", response_model=BrokerLeadOut, status_code=201)
async def invite_client(body: ClientInviteIn, session: SessionDep, principal: BrokerRoleDep):
    """Invite a client by email: they receive the broker's share link and join the broker's
    clients if they sign up through it."""
    lead = await broker_lead_service.invite_client(
        session,
        broker_id=principal.user_id,
        name=body.name,
        email=str(body.email),
        phone=body.phone,
        notes=body.notes,
    )
    return BrokerLeadOut(**broker_lead_service.serialize(lead))


@router.post("/leads/listing", response_model=BrokerLeadOut, status_code=201)
async def introduce_listing(
    session: SessionDep,
    principal: BrokerRoleDep,
    kind: Annotated[str, Form()],
    fields: Annotated[str, Form()] = "{}",
    files: Annotated[list[UploadFile] | None, File()] = None,
):
    """Introduce a property (ready) or a project (off-plan) with its owner / developer contact
    and documents. Staff review it; it never becomes a listing by itself."""
    try:
        parsed = json.loads(fields or "{}")
    except json.JSONDecodeError as exc:
        raise AppError("INVALID_FIELDS", "fields must be valid JSON.", status_code=422) from exc
    if not isinstance(parsed, dict):
        raise AppError("INVALID_FIELDS", "fields must be a JSON object.", status_code=422)
    incoming = [f for f in (files or []) if f.filename]
    if len(incoming) > broker_lead_service.MAX_LEAD_FILES:
        raise AppError(
            "TOO_MANY_FILES",
            f"At most {broker_lead_service.MAX_LEAD_FILES} documents.",
            status_code=422,
        )
    file_tuples: list[tuple[str, bytes, str | None]] = []
    for f in incoming:
        data = await f.read()
        if not data:
            continue
        if len(data) > broker_lead_service.MAX_LEAD_FILE_BYTES:
            raise AppError("FILE_TOO_LARGE", f"'{f.filename}' exceeds 12 MB.", status_code=422)
        file_tuples.append((f.filename or "document", data, f.content_type))
    lead = await broker_lead_service.submit_listing_lead(
        session, broker_id=principal.user_id, kind=kind, fields=parsed, files=file_tuples
    )
    return BrokerLeadOut(**broker_lead_service.serialize(lead))


@router.post("/leads/{lead_id}/cancel", response_model=BrokerLeadOut)
async def withdraw_lead(lead_id: uuid.UUID, session: SessionDep, principal: BrokerRoleDep):
    lead = await broker_lead_service.cancel(session, broker_id=principal.user_id, lead_id=lead_id)
    return BrokerLeadOut(**broker_lead_service.serialize(lead))
