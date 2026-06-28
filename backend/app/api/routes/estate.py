"""Estate / inheritance routes (Group 4).

- GET/POST/PATCH/DELETE /api/v1/estate/beneficiaries   the caller's own beneficiary register
  (free allocation, sum ≤ 100; non-user beneficiaries are PENDING until they register+KYC).
- POST /api/v1/admin/estate/verify-death               ADMIN-ONLY: record a verified death
  (death-certificate document via the Group-2 storage seam) → execute beneficiary transfers
  atomically. Idempotent (one estate event per deceased; re-confirm = no-op).

Death verification is manual-admin only — never client-asserted, never auto-inactivity.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from app.api.deps import AdminDep, PrincipalDep, SessionDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.estate import (
    EstateBeneficiaryIn,
    EstateBeneficiaryOut,
    EstateBeneficiaryUpdateIn,
    EstateExecutionOut,
)
from app.services import document_service, estate_service

router = APIRouter(prefix="/api/v1", tags=["estate"])

OwnerScoped = PrincipalDep  # estate is the caller's OWN — any authenticated holder


@router.get("/estate/beneficiaries", response_model=list[EstateBeneficiaryOut])
async def list_beneficiaries(principal: OwnerScoped, session: SessionDep):
    rows = await estate_service.list_beneficiaries(session, principal.user_id)
    return [EstateBeneficiaryOut(**estate_service.serialize(b)) for b in rows]


@router.post("/estate/beneficiaries", response_model=EstateBeneficiaryOut, status_code=201)
async def add_beneficiary(body: EstateBeneficiaryIn, principal: OwnerScoped, session: SessionDep):
    b = await estate_service.add_beneficiary(session, principal.user_id, body.model_dump())
    return EstateBeneficiaryOut(**estate_service.serialize(b))


@router.patch("/estate/beneficiaries/{beneficiary_id}", response_model=EstateBeneficiaryOut)
async def update_beneficiary(
    beneficiary_id: uuid.UUID,
    body: EstateBeneficiaryUpdateIn,
    principal: OwnerScoped,
    session: SessionDep,
):
    b = await estate_service.update_beneficiary(
        session, principal.user_id, beneficiary_id, body.model_dump(exclude_unset=True)
    )
    return EstateBeneficiaryOut(**estate_service.serialize(b))


@router.delete("/estate/beneficiaries/{beneficiary_id}", status_code=204)
async def remove_beneficiary(
    beneficiary_id: uuid.UUID, principal: OwnerScoped, session: SessionDep
):
    await estate_service.remove_beneficiary(session, principal.user_id, beneficiary_id)


@router.post("/admin/estate/verify-death", response_model=EstateExecutionOut)
async def verify_death(
    admin: AdminDep,
    session: SessionDep,
    subject_user_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
):
    """ADMIN-ONLY. Store the uploaded death certificate, then execute the deceased's
    beneficiary transfers atomically (idempotent)."""
    data = await file.read()
    if not data:
        raise AppError("EMPTY_FILE", "Death certificate file is empty.", status_code=422)
    if len(data) > get_settings().storage_max_upload_bytes:
        raise AppError(
            "FILE_TOO_LARGE",
            f"File exceeds the {get_settings().storage_max_upload_mb} MB limit.",
            status_code=413,
        )
    cert = await document_service.create_user_document(
        session,
        user_id=subject_user_id,
        title="Death certificate",
        doc_type="death_certificate",
        filename=file.filename or "death-certificate",
        data=data,
    )
    result = await estate_service.verify_death_and_execute(
        session,
        admin_id=admin.user_id,
        subject_user_id=subject_user_id,
        certificate_document_id=cert.id,
    )
    return EstateExecutionOut(**result)
