"""Estate / inheritance routes (Group 4; certificate, documents and claims: 0035).

The caller's own beneficiary register (free allocation, sum ≤ 100):
- GET/POST/PATCH/DELETE /api/v1/estate/beneficiaries
- POST   /api/v1/estate/beneficiaries/{id}/documents            a copy of the person's ID
- GET    /api/v1/estate/beneficiaries/{id}/documents/{doc_id}   that file (owner only)
- DELETE /api/v1/estate/beneficiaries/{id}/documents/{doc_id}
- GET    /api/v1/estate/beneficiaries/{id}/certificate          the person's certificate (PDF)

Claims (client, 2026-10-07):
- POST /api/v1/estate/claims                 PUBLIC: a claim with the certificate and the
                                             claimant's identity document (rate-limited)
- GET  /api/v1/estate/claims/mine            the caller's claims and their status
- POST /api/v1/estate/claims/{id}/documents  the claimant adds a document staff asked for

- POST /api/v1/admin/estate/verify-death     ADMIN-ONLY: record a verified death (death
  certificate via the Group-2 storage seam) and execute the register at once. Idempotent.

Nothing moves on a claimant's word: staff review a claim in the admin panel and approve it
there (``admin_estate``); the transfer goes to the claimant's own verified account.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response
from slowapi.util import get_remote_address

from app.api.deps import AdminDep, PrincipalDep, SessionDep, current_principal
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ratelimit import ESTATE_CLAIM_LIMIT, limiter
from app.schemas.estate import (
    EstateBeneficiaryIn,
    EstateBeneficiaryOut,
    EstateBeneficiaryUpdateIn,
    EstateClaimOut,
    EstateExecutionOut,
)
from app.services import document_service, estate_service

router = APIRouter(prefix="/api/v1", tags=["estate"])

OwnerScoped = PrincipalDep  # estate is the caller's OWN — any authenticated holder


async def _read(file: UploadFile) -> bytes:
    """An upload's bytes, never more than one byte over the limit (the service refuses it)."""
    return await file.read(estate_service.MAX_UPLOAD_BYTES + 1)


@router.get("/estate/beneficiaries", response_model=list[EstateBeneficiaryOut])
async def list_beneficiaries(principal: OwnerScoped, session: SessionDep):
    rows = await estate_service.list_beneficiaries(session, principal.user_id)
    locked = await estate_service.is_closed(session, principal.user_id)
    return [EstateBeneficiaryOut(**estate_service.serialize(b, locked=locked)) for b in rows]


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


@router.post(
    "/estate/beneficiaries/{beneficiary_id}/documents",
    response_model=EstateBeneficiaryOut,
    status_code=201,
)
async def add_beneficiary_document(
    beneficiary_id: uuid.UUID,
    principal: OwnerScoped,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
):
    """Keep a copy of the person's identity document (a photo or a PDF) with their record."""
    b = await estate_service.add_id_document(
        session,
        principal.user_id,
        beneficiary_id,
        filename=file.filename,
        data=await _read(file),
    )
    return EstateBeneficiaryOut(**estate_service.serialize(b))


@router.get("/estate/beneficiaries/{beneficiary_id}/documents/{doc_id}")
async def get_beneficiary_document(
    beneficiary_id: uuid.UUID, doc_id: str, principal: OwnerScoped, session: SessionDep
):
    """One of the copies the holder uploaded. The holder alone can fetch it."""
    doc, data = await estate_service.get_id_document(
        session, principal.user_id, beneficiary_id, doc_id
    )
    return Response(
        content=data,
        media_type=doc.get("content_type") or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{doc.get("filename") or "document"}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.delete(
    "/estate/beneficiaries/{beneficiary_id}/documents/{doc_id}",
    response_model=EstateBeneficiaryOut,
)
async def remove_beneficiary_document(
    beneficiary_id: uuid.UUID, doc_id: str, principal: OwnerScoped, session: SessionDep
):
    b = await estate_service.remove_id_document(session, principal.user_id, beneficiary_id, doc_id)
    return EstateBeneficiaryOut(**estate_service.serialize(b))


@router.get("/estate/beneficiaries/{beneficiary_id}/certificate")
async def beneficiary_certificate(
    beneficiary_id: uuid.UUID, principal: OwnerScoped, session: SessionDep
):
    """The certificate of one person in the caller's register: what the register says about
    them today, with the number a claim is made with. Generated on demand, always current."""
    filename, pdf = await estate_service.build_certificate(
        session, principal.user_id, beneficiary_id
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


# --- claims -------------------------------------------------------------------- #
@router.post("/estate/claims", response_model=EstateClaimOut, status_code=201)
@limiter.limit(ESTATE_CLAIM_LIMIT)
async def submit_claim(
    request: Request,
    session: SessionDep,
    fields: Annotated[str, Form()],
    certificate: Annotated[UploadFile, File()],
    identity: Annotated[list[UploadFile], File()],
    evidence: Annotated[list[UploadFile] | None, File()] = None,
):
    """PUBLIC. A claim on a holder's assets: the form's fields as JSON, the beneficiary
    certificate, the claimant's identity document (one or two sides) and, when they have it,
    the official document supporting the claim (for a death: the death certificate).

    The answer is the claim's reference. It never says whether the certificate matched."""
    try:
        parsed = json.loads(fields or "{}")
    except json.JSONDecodeError as exc:
        raise AppError("INVALID_FIELDS", "fields must be valid JSON.", status_code=422) from exc
    if not isinstance(parsed, dict):
        raise AppError("INVALID_FIELDS", "fields must be a JSON object.", status_code=422)
    user_id = (
        (await current_principal(request)).user_id if request.headers.get("Authorization") else None
    )
    incoming = [("certificate", certificate)]
    incoming += [("identity", f) for f in identity if f.filename]
    incoming += [("evidence", f) for f in (evidence or []) if f.filename]
    if len(incoming) > estate_service.MAX_CLAIM_DOCUMENTS:
        raise AppError(
            "TOO_MANY_FILES",
            f"At most {estate_service.MAX_CLAIM_DOCUMENTS} files.",
            status_code=422,
        )
    files: list[tuple[str, str | None, bytes]] = []
    total = 0
    for kind, upload in incoming:
        data = await _read(upload)
        total += len(data)
        if total > get_settings().storage_max_upload_bytes:
            raise AppError(
                "FILE_TOO_LARGE",
                f"The files together exceed {get_settings().storage_max_upload_mb} MB.",
                status_code=413,
            )
        files.append((kind, upload.filename, data))
    claim = await estate_service.submit_claim(
        session, fields=parsed, files=files, user_id=user_id, ip=get_remote_address(request)
    )
    return EstateClaimOut(**estate_service.serialize_claim(claim))


@router.get("/estate/claims/mine", response_model=list[EstateClaimOut])
async def my_claims(principal: PrincipalDep, session: SessionDep):
    """The caller's own claims (sent while signed in, or with their verified address)."""
    rows = await estate_service.list_my_claims(session, principal.user_id)
    return [EstateClaimOut(**estate_service.serialize_claim(c)) for c in rows]


@router.post("/estate/claims/{claim_id}/documents", response_model=EstateClaimOut)
async def add_claim_document(
    claim_id: uuid.UUID,
    principal: PrincipalDep,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()] = "evidence",
):
    """The claimant adds a document to their open claim (what staff asked for)."""
    claim = await estate_service.add_claim_document(
        session,
        user_id=principal.user_id,
        claim_id=claim_id,
        kind=kind,
        filename=file.filename,
        data=await _read(file),
    )
    return EstateClaimOut(**estate_service.serialize_claim(claim))


# --- admin API (kept as it was) --------------------------------------------------- #
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
