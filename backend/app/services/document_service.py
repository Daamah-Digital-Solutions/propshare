"""Property documents (Phase: storage/documents).

Owners upload documents for a property they own (offering memorandum, valuation, title
deed, …); they are listed on the public property page and downloadable. Files live in the
storage seam (real bytes — local FS dev / S3 prod); the ``documents`` table (Phase-1)
holds the metadata + storage key. DELETE NOTHING: this replaces the mock PropertyDocuments
list with the real table.

Access: a property document (``user_id`` NULL) is downloadable when its property is public
(active/funded). User-scoped documents (``user_id`` set) are not served by the public
download route. Certificates are generated live (see ``certificate_service``), not stored.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Document, Property
from app.models.base import PropertyStatus
from app.services import property_service
from app.services.integrations import storage

PUBLIC_STATUSES = (PropertyStatus.active, PropertyStatus.funded)

_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "txt": "text/plain",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _safe_filename(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "file").strip().split("/")[-1].split("\\")[-1])
    return base[:120] or "file"


def content_type_for(key_or_name: str) -> str:
    ext = key_or_name.rsplit(".", 1)[-1].lower() if "." in key_or_name else ""
    return _CONTENT_TYPES.get(ext, "application/octet-stream")


async def _get_owned_property(
    session: AsyncSession, owner_id: uuid.UUID, prop_id: uuid.UUID
) -> Property:
    prop = await session.get(Property, prop_id)
    if prop is None:
        raise AppError("PROPERTY_NOT_FOUND", "Property not found.", status_code=404)
    if prop.owner_id != owner_id:
        raise AppError("NOT_PROPERTY_OWNER", "You do not own this property.", status_code=403)
    return prop


def serialize(doc: Document) -> dict:
    return {
        "id": doc.id,
        "property_id": doc.property_id,
        "title": doc.title,
        "type": doc.type,
        "download_url": f"/api/v1/documents/{doc.id}/download",
        "created_at": doc.created_at,
    }


async def create_property_document(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    prop_id: uuid.UUID,
    title: str,
    doc_type: str,
    filename: str,
    data: bytes,
) -> Document:
    await _get_owned_property(session, owner_id, prop_id)
    safe = _safe_filename(filename)
    key = f"documents/{prop_id}/{uuid.uuid4().hex}-{safe}"
    storage.save(key, data, content_type_for(safe))
    doc = Document(property_id=prop_id, user_id=None, title=title, type=doc_type, file_url=key)
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


async def admin_create_property_document(
    session: AsyncSession,
    *,
    prop_id: uuid.UUID,
    title: str,
    doc_type: str,
    filename: str,
    data: bytes,
) -> Document:
    """Admin upload: publish a document for ANY property (no owner check — the /admin panel is
    already admin-gated). Same storage + row shape as the owner path."""
    prop = await session.get(Property, prop_id)
    if prop is None:
        raise AppError("PROPERTY_NOT_FOUND", "Property not found.", status_code=404)
    safe = _safe_filename(filename)
    key = f"documents/{prop_id}/{uuid.uuid4().hex}-{safe}"
    storage.save(key, data, content_type_for(safe))
    doc = Document(property_id=prop_id, user_id=None, title=title, type=doc_type, file_url=key)
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


async def create_user_document(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    title: str,
    doc_type: str,
    filename: str,
    data: bytes,
) -> Document:
    """Store a user-scoped document (e.g. a death certificate for estate verification).
    Not served by the public download route (user_id is set)."""
    safe = _safe_filename(filename)
    key = f"documents/user/{user_id}/{uuid.uuid4().hex}-{safe}"
    storage.save(key, data, content_type_for(safe))
    doc = Document(property_id=None, user_id=user_id, title=title, type=doc_type, file_url=key)
    session.add(doc)
    await session.flush()
    return doc


async def list_property_documents(session: AsyncSession, id_or_slug: str) -> list[Document]:
    # get_public_detail enforces active/funded (404 otherwise) — public listing only.
    prop = await property_service.get_public_detail(session, id_or_slug)
    res = await session.execute(
        select(Document).where(Document.property_id == prop.id).order_by(Document.created_at.desc())
    )
    return list(res.scalars().all())


async def get_for_download(session: AsyncSession, doc_id: uuid.UUID) -> tuple[Document, bytes, str]:
    """Return (doc, bytes, content_type) for a PUBLIC property document. 404/403 otherwise."""
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise AppError("NOT_FOUND", "Document not found.", status_code=404)
    if doc.user_id is not None:
        # user-scoped documents are not served by this public route
        raise AppError("FORBIDDEN", "This document is not publicly downloadable.", status_code=403)
    if doc.property_id is not None:
        prop = await session.get(Property, doc.property_id)
        if prop is None or prop.status not in PUBLIC_STATUSES:
            raise AppError("NOT_FOUND", "Document not found.", status_code=404)
    try:
        data = storage.load(doc.file_url)
    except storage.StorageNotFound as exc:
        raise AppError("NOT_FOUND", "Document file is missing.", status_code=404) from exc
    return doc, data, content_type_for(doc.file_url)
