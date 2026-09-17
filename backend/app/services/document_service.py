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

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Document, Property
from app.models.base import PropertyStatus
from app.services import property_service
from app.services.integrations import storage

PUBLIC_STATUSES = (PropertyStatus.active, PropertyStatus.funded)

# Single source of truth for document categories (the admin panel + the SPA mirror it).
DOC_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("spv", "SPV Documents"),
    ("valuation", "Valuation Reports"),
    ("financial", "Financial & Investment Studies"),
    ("agreement", "Agreements"),
    ("legal", "Legal Documents"),
    ("insurance", "Insurance Certificates"),
    ("audit", "Audit Reports"),  # label renamed (Step 3); key kept for stored rows
    ("other", "Other Documents"),
)
DOC_CATEGORY_VALUES = frozenset(v for v, _ in DOC_CATEGORIES)

_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
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


# Leading bytes a file of this extension must start with (the extension alone is spoofable).
_MAGIC = {
    "pdf": (b"%PDF",),
    "png": (b"\x89PNG",),
    "jpg": (b"\xff\xd8",),
    "jpeg": (b"\xff\xd8",),
    "webp": (b"RIFF",),
    "docx": (b"PK",),
    "xlsx": (b"PK",),
}


def validate_doc_type(doc_type: str | None) -> str:
    value = (doc_type or "other").strip().lower()
    if value not in DOC_CATEGORY_VALUES:
        raise AppError(
            "INVALID_CATEGORY",
            f"Document category must be one of {sorted(DOC_CATEGORY_VALUES)}.",
            status_code=422,
        )
    return value


def validate_file(filename: str, data: bytes) -> str:
    """Allow-list by extension + magic bytes, size cap, non-empty. Returns the safe name."""
    if not data:
        raise AppError("EMPTY_FILE", "Uploaded file is empty.", status_code=422)
    if len(data) > get_settings().storage_max_upload_bytes:
        raise AppError(
            "FILE_TOO_LARGE",
            f"File exceeds the {get_settings().storage_max_upload_mb} MB limit.",
            status_code=413,
        )
    safe = _safe_filename(filename)
    ext = safe.rsplit(".", 1)[-1].lower() if "." in safe else ""
    if ext not in _CONTENT_TYPES:
        raise AppError(
            "UNSUPPORTED_FILE_TYPE",
            f"Allowed file types: {', '.join(sorted(_CONTENT_TYPES))}.",
            status_code=415,
        )
    magics = _MAGIC.get(ext)
    if magics and not any(data.startswith(m) for m in magics):
        raise AppError(
            "UNSUPPORTED_FILE_TYPE", f"The file is not a valid .{ext} file.", status_code=415
        )
    return safe


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
    doc_type = validate_doc_type(doc_type)
    safe = validate_file(filename, data)
    key = f"documents/{prop_id}/{uuid.uuid4().hex}-{safe}"
    storage.save(key, data, content_type_for(safe))
    doc = Document(property_id=prop_id, user_id=None, title=title, type=doc_type, file_url=key)
    session.add(doc)
    # flush (not commit): the caller owns the transaction — the API request session commits
    # at teardown and the admin panel's session_scope() commits on exit. Committing here
    # closed that outer transaction and made the panel's refresh()/exit blow up with 500.
    await session.flush()
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
    doc_type = validate_doc_type(doc_type)
    safe = validate_file(filename, data)
    key = f"documents/{prop_id}/{uuid.uuid4().hex}-{safe}"
    storage.save(key, data, content_type_for(safe))
    doc = Document(property_id=prop_id, user_id=None, title=title, type=doc_type, file_url=key)
    session.add(doc)
    # flush (not commit): the caller owns the transaction — the API request session commits
    # at teardown and the admin panel's session_scope() commits on exit. Committing here
    # closed that outer transaction and made the panel's refresh()/exit blow up with 500.
    await session.flush()
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


async def list_property_documents(
    session: AsyncSession, id_or_slug: str, *, preview_token: str | None = None
) -> list[Document]:
    # active/funded only (404 otherwise) unless a valid preview token for THIS
    # property is supplied (admin preview-before-publish).
    prop = await property_service.get_public_detail(
        session, id_or_slug, preview_token=preview_token
    )
    res = await session.execute(
        select(Document).where(Document.property_id == prop.id).order_by(Document.created_at.desc())
    )
    return list(res.scalars().all())


async def get_for_download(
    session: AsyncSession, doc_id: uuid.UUID, *, preview_token: str | None = None
) -> tuple[Document, bytes, str]:
    """(doc, bytes, content_type) for a PUBLIC property document, or a previewed draft
    with a valid token. 404/403 otherwise."""
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise AppError("NOT_FOUND", "Document not found.", status_code=404)
    if doc.user_id is not None:
        # user-scoped documents are not served by this public route
        raise AppError("FORBIDDEN", "This document is not publicly downloadable.", status_code=403)
    if doc.property_id is not None:
        prop = await session.get(Property, doc.property_id)
        if prop is None or (
            prop.status not in PUBLIC_STATUSES
            and not property_service.verify_preview_token(preview_token, prop.id)
        ):
            raise AppError("NOT_FOUND", "Document not found.", status_code=404)
    try:
        data = storage.load(doc.file_url)
    except storage.StorageNotFound as exc:
        raise AppError("NOT_FOUND", "Document file is missing.", status_code=404) from exc
    return doc, data, content_type_for(doc.file_url)


# --- admin maintenance: delete / replace (storage kept in sync, audited) --------------- #
async def delete_document(
    session: AsyncSession, *, doc_id: uuid.UUID, actor_id: uuid.UUID | None
) -> None:
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise AppError("NOT_FOUND", "Document not found.", status_code=404)
    key, prop_id, title = doc.file_url, doc.property_id, doc.title
    await session.delete(doc)
    await session.flush()
    storage.delete(key)
    await write_audit(
        session,
        action="document.deleted",
        entity_type="document",
        entity_id=str(doc_id),
        actor_id=actor_id,
        before={"property_id": str(prop_id) if prop_id else None, "title": title, "key": key},
    )


async def replace_document_file(
    session: AsyncSession,
    *,
    doc_id: uuid.UUID,
    filename: str,
    data: bytes,
    actor_id: uuid.UUID | None,
) -> Document:
    """Swap the file behind an existing document row (title/category unchanged)."""
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise AppError("NOT_FOUND", "Document not found.", status_code=404)
    safe = validate_file(filename, data)
    old_key = doc.file_url
    key = f"documents/{doc.property_id or 'user'}/{uuid.uuid4().hex}-{safe}"
    storage.save(key, data, content_type_for(safe))
    doc.file_url = key
    await session.flush()
    storage.delete(old_key)
    await write_audit(
        session,
        action="document.replaced",
        entity_type="document",
        entity_id=str(doc.id),
        actor_id=actor_id,
        before={"key": old_key},
        after={"key": key},
    )
    return doc
