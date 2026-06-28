"""Document + public-file routes (Phase: storage/documents).

- POST /properties/{prop_id}/documents   owner uploads a property document (multipart).
- GET  /properties/{id_or_slug}/documents PUBLIC list of a property's documents.
- GET  /documents/{doc_id}/download       PUBLIC download of a property document (active/funded).
- GET  /files/{key}                       PUBLIC inline serve for public assets (images/avatars).

Files live in the storage seam (real bytes — local FS dev / S3 prod). Owner writes are
owner-scoped (403 NOT_PROPERTY_OWNER). Investment certificates are generated live by the
investments router, not stored here.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response

from app.api.deps import Principal, SessionDep, require_active_role_db
from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.document import DocumentOut
from app.services import document_service
from app.services.integrations import storage

router = APIRouter(prefix="/api/v1", tags=["documents"])

OwnerDep = Annotated[Principal, Depends(require_active_role_db("owner"))]


async def _read_capped(file: UploadFile) -> bytes:
    data = await file.read()
    if len(data) > get_settings().storage_max_upload_bytes:
        raise AppError(
            "FILE_TOO_LARGE",
            f"File exceeds the {get_settings().storage_max_upload_mb} MB limit.",
            status_code=413,
        )
    if not data:
        raise AppError("EMPTY_FILE", "Uploaded file is empty.", status_code=422)
    return data


@router.post("/properties/{prop_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_property_document(
    prop_id: uuid.UUID,
    principal: OwnerDep,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=200)],
    doc_type: Annotated[str, Form(max_length=60)] = "document",
):
    data = await _read_capped(file)
    doc = await document_service.create_property_document(
        session,
        owner_id=principal.user_id,
        prop_id=prop_id,
        title=title,
        doc_type=doc_type,
        filename=file.filename or "file",
        data=data,
    )
    return DocumentOut(**document_service.serialize(doc))


@router.get("/properties/{id_or_slug}/documents", response_model=list[DocumentOut])
async def list_property_documents(id_or_slug: str, session: SessionDep):
    docs = await document_service.list_property_documents(session, id_or_slug)
    return [DocumentOut(**document_service.serialize(d)) for d in docs]


@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: uuid.UUID, session: SessionDep):
    doc, data, content_type = await document_service.get_for_download(session, doc_id)
    filename = doc.file_url.rsplit("/", 1)[-1]
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/files/{key:path}")
async def serve_public_file(key: str):
    if not key.startswith(storage.PUBLIC_PREFIXES):
        raise AppError("NOT_FOUND", "File not found.", status_code=404)
    try:
        data = storage.load(key)
    except (storage.StorageNotFound, storage.StorageKeyError) as exc:
        raise AppError("NOT_FOUND", "File not found.", status_code=404) from exc
    return Response(content=data, media_type=document_service.content_type_for(key))
