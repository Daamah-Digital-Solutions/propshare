"""Estate / inheritance (Group 4) — the beneficiary register, the beneficiary's certificate,
claims, and the transfer staff execute after verifying one.

Owner decisions (legal risk accepted — see DECISIONS.md / plan/phase-estate-design.md):
  * Allocation is FREE (holder-set %, sum ≤ 100) — NOT enforced to Sharia fara'id.
  * A transfer happens ONLY after staff record a verified event — never client-asserted,
    never auto-inactivity.

Client (2026-10-07) — the procedure a claim follows:
  * The holder records a person with a copy of their identity document, can change the
    record at any time, and downloads a certificate for them (``build_certificate``).
  * After the holder's death that person submits a claim on a public page with the
    certificate and their own identity document (``submit_claim``). Staff compare the two
    with the register, and on approval the claimant's share moves to the claimant's OWN
    verified account (``claim_approve``). Nobody is ever given the holder's account.

Execution reuses the Phase-8/Phase-10 atomic-transfer pattern: lock the property `FOR
UPDATE`, split the holder's AVAILABLE units (net − reserved, so listings/LP-exits are
respected) across beneficiaries by free % via the exact Hamilton apportionment (an
``_unalloc`` bucket keeps any unallocated remainder with the estate), move units on the
append-only ``ownership_ledger`` (fee_rate stamped — Decision-2 carries), and record an
``estate_transfers`` row. One ``estate_events`` row per holder (UNIQUE), guarded by status,
so the split is made exactly once.

Who receives at once depends on how the event was recorded:
  * from a claim: only the claimant. Every other beneficiary's share is written
    ``awaiting_claim`` and moves when their own claim is approved.
  * from the admin API (``verify_death_and_execute``, kept as it was): every beneficiary
    whose email is a verified account; the others are ``pending`` and move when they
    register and verify (mirrors Phase-10).
"""

from __future__ import annotations

import datetime as dt
import re
import secrets
import uuid
from collections.abc import Hashable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    EstateBeneficiary,
    EstateClaim,
    EstateEvent,
    EstateTransfer,
    KycVerification,
    Property,
    UserRole,
    Wallet,
)
from app.models.identity import User
from app.models.investments import OwnershipLedger
from app.services import (
    estate_certificate,
    notification_service,
    secondary_service,
    settings_service,
)
from app.services.distribution_service import hamilton
from app.services.integrations import storage
from app.services.statement_service import english

# What the holder's form offers; the certificate and the staff page print these labels.
ROLES = {
    "beneficiary": "Beneficiary",
    "heir": "Heir",
    "authorized": "Authorized Person",
    "legal": "Legal Representative",
}
SCOPES = {
    "ownership": "Ownership Rights",
    "passive_income": "Passive Income",
    "rental_returns": "Rental Returns",
    "wallet": "Wallet Balance",
    "portfolio": "Full Portfolio",
}
TRIGGERS = {
    "death": "On verified death",
    "inactivity_1y": "After 12 months inactivity",
    "authorized": "Authorized transfer event",
    "manual": "Manual / on request",
}

# A copy of an identity document, or a document sent with a claim: a photo or a PDF.
_UPLOAD_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ID_DOCUMENTS = 4

CLAIM_REASONS = {
    "death": "Death of the account holder",
    "incapacity": "The account holder can no longer manage the account",
    "other": "Another reason",
}
CLAIM_DOC_KINDS = {
    "certificate": "Beneficiary certificate",
    "identity": "Claimant's identity document",
    "evidence": "Official supporting document",
    "other": "Other document",
}
CLAIM_STATUSES = {
    "submitted": "Received",
    "in_review": "In review",
    "needs_info": "Waiting for the claimant",
    "approved": "Approved",
    "rejected": "Rejected",
}
OPEN_CLAIM_STATUSES = ("submitted", "in_review", "needs_info")
MAX_CLAIM_DOCUMENTS = 10
CLAIMS_PER_EMAIL_PER_DAY = 5
# a share written at the event for a beneficiary who has not received it yet
_WAITING = ("pending", "awaiting_claim")

_plain = notification_service.plain_text
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _clean(value: object, limit: int) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] or None


def _site(path: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}{path}"


def _code(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"


def normalize_certificate_no(value: object) -> str | None:
    """A certificate number as typed (any case, spaces, with or without dashes) in the form
    it is stored in: ``CPB-XXXX-XXXX``."""
    text = re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()
    if not text:
        return None
    if re.fullmatch(r"CPB[0-9A-F]{8}", text):
        return f"CPB-{text[3:7]}-{text[7:]}"
    return str(value).strip().upper()[:40]


async def _holding(session: AsyncSession, user_id: uuid.UUID, property_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(OwnershipLedger.units), 0)).where(
            OwnershipLedger.user_id == user_id, OwnershipLedger.property_id == property_id
        )
    )
    return int(total or 0)


async def _kyc_status(session: AsyncSession, user_id: uuid.UUID) -> str:
    status = await session.scalar(
        select(KycVerification.status).where(KycVerification.user_id == user_id)
    )
    return str(status) if status is not None else "none"


async def _user_kyc_verified(session: AsyncSession, user_id: uuid.UUID) -> bool:
    return await _kyc_status(session, user_id) == "verified"


def checked_upload(filename: str | None, data: bytes) -> tuple[str, str]:
    """(safe file name, content type) of an uploaded copy: a JPG, PNG, WebP or PDF, by its
    extension AND by its first bytes; never empty, never over the limit."""
    from app.services.document_service import _safe_filename

    if not data:
        raise AppError("EMPTY_FILE", "The file is empty.", status_code=422)
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError(
            "FILE_TOO_LARGE",
            f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            status_code=413,
        )
    safe = _safe_filename(filename or "document")
    ext = safe.rsplit(".", 1)[-1].lower() if "." in safe else ""
    looks_right = {
        "pdf": data.startswith(b"%PDF"),
        "png": data.startswith(b"\x89PNG"),
        "jpg": data.startswith(b"\xff\xd8"),
        "jpeg": data.startswith(b"\xff\xd8"),
        "webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }
    if ext not in _UPLOAD_TYPES or not looks_right[ext]:
        raise AppError(
            "UNSUPPORTED_FILE_TYPE",
            "Upload a photo (JPG, PNG or WebP) or a PDF.",
            status_code=415,
        )
    return safe, _UPLOAD_TYPES[ext]


# --- beneficiary register (owner/holder-scoped) ----------------------------- #
def _meta(raw: object) -> dict:
    """The form's extra fields, kept to what the form has: nothing else is stored."""
    raw = raw if isinstance(raw, dict) else {}
    given = raw.get("scope")
    scope_in = given if isinstance(given, list) else []
    scope = list(dict.fromkeys(s for s in scope_in if s in SCOPES))
    return {
        "role": raw.get("role") if raw.get("role") in ROLES else "beneficiary",
        "idType": _clean(raw.get("idType"), 40) or "Passport",
        "idNumber": _clean(raw.get("idNumber"), 80) or "",
        "scope": scope or ["ownership"],
        "trigger": raw.get("trigger") if raw.get("trigger") in TRIGGERS else "death",
    }


def serialize(b: EstateBeneficiary, *, locked: bool = False) -> dict:
    return {
        "id": b.id,
        "full_name": b.full_name,
        "relationship": b.relationship,
        "email": b.email,
        "phone": b.phone,
        "allocation_pct": b.allocation_pct,
        "notes": b.notes,
        "status": b.status,
        "is_user": b.beneficiary_user_id is not None,
        "meta": b.meta or {},
        "created_at": b.created_at,
        "updated_at": b.updated_at,
        "certificate_no": b.certificate_no,
        "version": b.version,
        # the copies by name only: storage keys never leave the server
        "documents": [
            {
                "id": d.get("id"),
                "filename": d.get("filename") or "document",
                "content_type": d.get("content_type") or "application/octet-stream",
                "size": int(d.get("size") or 0),
                "uploaded_at": d.get("uploaded_at"),
            }
            for d in (b.id_documents or [])
        ],
        "locked": locked,
    }


async def is_closed(session: AsyncSession, owner_id: uuid.UUID) -> bool:
    """True once an event was recorded for this holder: the register is what it was that
    day, and can no longer be changed (by whoever holds the account's password)."""
    found = await session.scalar(
        select(EstateEvent.id).where(EstateEvent.subject_user_id == owner_id)
    )
    return found is not None


async def _require_open(session: AsyncSession, owner_id: uuid.UUID) -> None:
    if await is_closed(session, owner_id):
        raise AppError(
            "REGISTER_CLOSED",
            "This register is closed: a transfer event was recorded for this account.",
            status_code=409,
        )


async def list_beneficiaries(session: AsyncSession, owner_id: uuid.UUID) -> list[EstateBeneficiary]:
    res = await session.execute(
        select(EstateBeneficiary)
        .where(EstateBeneficiary.owner_id == owner_id)
        .order_by(EstateBeneficiary.created_at)
    )
    return list(res.scalars().all())


async def _current_sum(
    session: AsyncSession, owner_id: uuid.UUID, *, exclude_id: uuid.UUID | None = None
) -> int:
    q = select(func.coalesce(func.sum(EstateBeneficiary.allocation_pct), 0)).where(
        EstateBeneficiary.owner_id == owner_id
    )
    if exclude_id is not None:
        q = q.where(EstateBeneficiary.id != exclude_id)
    return int(await session.scalar(q) or 0)


async def _resolve_user(session: AsyncSession, email: str | None) -> tuple[uuid.UUID | None, str]:
    """Match a beneficiary email to a KYC'd user (active) or leave pending (Phase-10 model)."""
    if not email:
        return None, "pending"
    user = (
        await session.execute(select(User).where(func.lower(User.email) == email.lower()))
    ).scalar_one_or_none()
    if user is None:
        return None, "pending"
    verified = await _user_kyc_verified(session, user.id)
    return (user.id, "active") if verified else (user.id, "pending")


async def _new_certificate_no(session: AsyncSession) -> str:
    for _ in range(20):
        number = _code("CPB")
        taken = await session.scalar(
            select(EstateBeneficiary.id).where(EstateBeneficiary.certificate_no == number)
        )
        if taken is None:
            return number
    raise AppError("TRY_AGAIN", "Please try again.", status_code=503)


async def add_beneficiary(
    session: AsyncSession, owner_id: uuid.UUID, data: dict
) -> EstateBeneficiary:
    await _require_open(session, owner_id)
    full_name = _clean(data.get("full_name"), 200)
    if not full_name:
        raise AppError("INVALID_BENEFICIARY", "Full name is required.", status_code=422)
    pct = int(data.get("allocation_pct") or 0)
    if pct < 0 or pct > 100:
        raise AppError("INVALID_ALLOCATION", "Allocation must be 0–100%.", status_code=422)
    if await _current_sum(session, owner_id) + pct > 100:
        raise AppError(
            "ALLOCATION_EXCEEDS_100",
            "Total beneficiary allocation cannot exceed 100%.",
            status_code=422,
            details={"current": await _current_sum(session, owner_id), "requested": pct},
        )
    email = _clean(data.get("email"), 200)
    user_id, status = await _resolve_user(session, email)
    b = EstateBeneficiary(
        owner_id=owner_id,
        full_name=full_name,
        relationship=_clean(data.get("relationship"), 80),
        email=email,
        phone=_clean(data.get("phone"), 40),
        allocation_pct=pct,
        notes=_clean(data.get("notes"), 2000),
        meta=_meta(data.get("meta")),
        beneficiary_user_id=user_id,
        status=status,
        certificate_no=await _new_certificate_no(session),
    )
    session.add(b)
    await session.flush()
    await write_audit(
        session,
        action="estate.beneficiary.added",
        entity_type="estate_beneficiary",
        entity_id=str(b.id),
        actor_id=owner_id,
        after={"certificate_no": b.certificate_no, "allocation_pct": pct},
    )
    await session.commit()
    await session.refresh(b)
    return b


async def _get_owned(
    session: AsyncSession, owner_id: uuid.UUID, beneficiary_id: uuid.UUID
) -> EstateBeneficiary:
    b = await session.get(EstateBeneficiary, beneficiary_id)
    if b is None or b.owner_id != owner_id:
        raise AppError("NOT_FOUND", "Beneficiary not found.", status_code=404)
    return b


async def update_beneficiary(
    session: AsyncSession, owner_id: uuid.UUID, beneficiary_id: uuid.UUID, data: dict
) -> EstateBeneficiary:
    """Change a record (client, 2026-10-07: "he can edit this person at any time"). Only the
    fields sent change; an optional field sent empty is cleared. Every change to what the
    certificate prints raises ``version``, so an older copy can be told from the current
    one."""
    await _require_open(session, owner_id)
    b = await _get_owned(session, owner_id, beneficiary_id)
    printed_before = _printed(b)

    if "full_name" in data:
        full_name = _clean(data["full_name"], 200)
        if not full_name:
            raise AppError("INVALID_BENEFICIARY", "Full name is required.", status_code=422)
        b.full_name = full_name
    if data.get("allocation_pct") is not None:
        pct = int(data["allocation_pct"])
        if pct < 0 or pct > 100:
            raise AppError("INVALID_ALLOCATION", "Allocation must be 0–100%.", status_code=422)
        if await _current_sum(session, owner_id, exclude_id=beneficiary_id) + pct > 100:
            raise AppError(
                "ALLOCATION_EXCEEDS_100",
                "Total beneficiary allocation cannot exceed 100%.",
                status_code=422,
            )
        b.allocation_pct = pct
    for field, limit in (("relationship", 80), ("phone", 40), ("notes", 2000)):
        if field in data:
            setattr(b, field, _clean(data[field], limit))
    if data.get("meta") is not None:
        b.meta = _meta(data["meta"])
    if "email" in data:
        b.email = _clean(data["email"], 200)
        b.beneficiary_user_id, b.status = await _resolve_user(session, b.email)

    changed = sorted(k for k, v in _printed(b).items() if printed_before.get(k) != v)
    if changed:
        b.version = (b.version or 1) + 1
    b.updated_at = _utcnow()
    await write_audit(
        session,
        action="estate.beneficiary.updated",
        entity_type="estate_beneficiary",
        entity_id=str(b.id),
        actor_id=owner_id,
        # which fields, never their values (a name or an identity number)
        after={"changed": changed, "version": b.version},
    )
    await session.commit()
    await session.refresh(b)
    return b


def _printed(b: EstateBeneficiary) -> dict:
    """What the certificate prints from a record."""
    meta = b.meta or {}
    return {
        "full_name": b.full_name,
        "relationship": b.relationship,
        "email": b.email,
        "allocation_pct": b.allocation_pct,
        "role": meta.get("role"),
        "id_type": meta.get("idType"),
        "id_number": meta.get("idNumber"),
        "scope": list(meta.get("scope") or []),
        "trigger": meta.get("trigger"),
    }


async def remove_beneficiary(
    session: AsyncSession, owner_id: uuid.UUID, beneficiary_id: uuid.UUID
) -> None:
    await _require_open(session, owner_id)
    b = await _get_owned(session, owner_id, beneficiary_id)
    keys = [d.get("key") for d in (b.id_documents or []) if d.get("key")]
    await write_audit(
        session,
        action="estate.beneficiary.removed",
        entity_type="estate_beneficiary",
        entity_id=str(b.id),
        actor_id=owner_id,
        before={"certificate_no": b.certificate_no, "version": b.version},
    )
    await session.delete(b)
    await session.commit()
    for key in keys:  # after the commit: a file is only removed once its record is gone
        storage.delete(key)


# --- copies of the person's identity document -------------------------------- #
async def add_id_document(
    session: AsyncSession,
    owner_id: uuid.UUID,
    beneficiary_id: uuid.UUID,
    *,
    filename: str | None,
    data: bytes,
) -> EstateBeneficiary:
    """Keep a copy of the person's identity document with their record (client, 2026-10-07).
    Staff compare it with the document a claimant sends."""
    await _require_open(session, owner_id)
    b = await _get_owned(session, owner_id, beneficiary_id)
    docs = list(b.id_documents or [])
    if len(docs) >= MAX_ID_DOCUMENTS:
        raise AppError(
            "TOO_MANY_FILES",
            f"At most {MAX_ID_DOCUMENTS} files per person. Remove one first.",
            status_code=422,
        )
    safe, content_type = checked_upload(filename, data)
    doc_id = uuid.uuid4().hex
    key = f"estate-beneficiaries/{b.id}/{doc_id}-{safe}"
    storage.save(key, data, content_type)
    docs.append(
        {
            "id": doc_id,
            "key": key,
            "filename": safe,
            "content_type": content_type,
            "size": len(data),
            "uploaded_at": _utcnow().isoformat(),
        }
    )
    b.id_documents = docs
    b.updated_at = _utcnow()
    await write_audit(
        session,
        action="estate.beneficiary.document_added",
        entity_type="estate_beneficiary",
        entity_id=str(b.id),
        actor_id=owner_id,
        after={"document": doc_id},
    )
    await session.flush()
    return b


def _find_document(docs: list, doc_id: str) -> dict:
    for d in docs or []:
        if d.get("id") == doc_id:
            return d
    raise AppError("NOT_FOUND", "File not found.", status_code=404)


async def get_id_document(
    session: AsyncSession, owner_id: uuid.UUID, beneficiary_id: uuid.UUID, doc_id: str
) -> tuple[dict, bytes]:
    b = await _get_owned(session, owner_id, beneficiary_id)
    doc = _find_document(b.id_documents, doc_id)
    try:
        return doc, storage.load(doc["key"])
    except storage.StorageNotFound as exc:
        raise AppError("NOT_FOUND", "The file is missing.", status_code=404) from exc


async def remove_id_document(
    session: AsyncSession, owner_id: uuid.UUID, beneficiary_id: uuid.UUID, doc_id: str
) -> EstateBeneficiary:
    await _require_open(session, owner_id)
    b = await _get_owned(session, owner_id, beneficiary_id)
    doc = _find_document(b.id_documents, doc_id)
    b.id_documents = [d for d in (b.id_documents or []) if d.get("id") != doc_id]
    b.updated_at = _utcnow()
    await write_audit(
        session,
        action="estate.beneficiary.document_removed",
        entity_type="estate_beneficiary",
        entity_id=str(b.id),
        actor_id=owner_id,
        before={"document": doc_id},
    )
    await session.flush()
    storage.delete(doc["key"])
    return b


# --- the certificate ---------------------------------------------------------- #
def claim_url(certificate_no: str | None = None) -> str:
    base = _site("/estate-claim")
    return f"{base}?certificate={certificate_no}" if certificate_no else base


async def build_certificate(
    session: AsyncSession,
    owner_id: uuid.UUID,
    beneficiary_id: uuid.UUID,
    *,
    now: dt.datetime | None = None,
) -> tuple[str, bytes]:
    """(file name, PDF) of the certificate for one person in the caller's register: what the
    register says about them today. It is issued in English, like every document of the
    platform, so the name must be written in Latin letters; and it must identify the person,
    so their identity document number must be on the record."""
    b = await _get_owned(session, owner_id, beneficiary_id)
    meta = _meta(b.meta)
    name = english(b.full_name)
    if not name:
        raise AppError(
            "CERTIFICATE_LATIN_NAME",
            "The certificate is issued in English. Edit this person and write their full "
            "name in Latin letters, exactly as in their passport or identity card.",
            status_code=422,
        )
    id_number = english(meta["idNumber"])
    if not id_number:
        raise AppError(
            "CERTIFICATE_NEEDS_ID",
            "Add this person's identity document number first (Edit), so the certificate "
            "identifies them.",
            status_code=422,
        )
    owner = await session.get(User, owner_id)
    holder = (english(owner.full_name) if owner else None) or (owner.email if owner else "-")
    role = ROLES[meta["role"]]
    pct = b.allocation_pct
    share = f"with an allocation of {pct}%," if pct > 0 else "with no share allocated,"
    scope = meta["scope"]
    coverage = SCOPES["portfolio"] if "portfolio" in scope else ", ".join(SCOPES[s] for s in scope)
    pdf = estate_certificate.render(
        beneficiary=name,
        holder=holder,
        role=role,
        designation=f"as {role.lower()}, {share}",
        relationship=english(b.relationship) or "-",
        id_type=english(meta["idType"]) or "-",
        id_number=id_number,
        allocation=f"{pct}%" if pct > 0 else "No share allocated",
        coverage=coverage,
        condition=TRIGGERS[meta["trigger"]],
        email=english(b.email) or "-",
        certificate_no=b.certificate_no,
        issued=(now or _utcnow()).strftime("%b %d, %Y"),
        version=b.version or 1,
        claim_url=claim_url(b.certificate_no),
    )
    await write_audit(
        session,
        action="estate.certificate.issued",
        entity_type="estate_beneficiary",
        entity_id=str(b.id),
        actor_id=owner_id,
        after={"certificate_no": b.certificate_no, "version": b.version},
    )
    return f"beneficiary-certificate-{b.certificate_no}.pdf", pdf


# --- recording the event and moving the shares ------------------------------- #
def _apportion(available: int, bens: list[EstateBeneficiary]) -> dict[str, int]:
    """Each beneficiary's units of ``available`` by the register's percentages. Exact
    (Hamilton); what the holder left unallocated stays with the estate."""
    total = sum(b.allocation_pct for b in bens)
    weights: list[tuple[Hashable, int]] = [(str(b.id), b.allocation_pct) for b in bens]
    if total < 100:
        weights.append(("_unalloc", 100 - total))
    return {str(k): int(v) for k, v in hamilton(available, weights).items()}


async def _held_properties(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await session.execute(
        select(OwnershipLedger.property_id)
        .where(OwnershipLedger.user_id == user_id)
        .group_by(OwnershipLedger.property_id)
        .having(func.coalesce(func.sum(OwnershipLedger.units), 0) > 0)
    )
    return [r[0] for r in rows.all()]


async def preview_split(session: AsyncSession, subject_user_id: uuid.UUID) -> list[dict]:
    """What recording the event now would give each beneficiary, property by property: the
    holder's units, those held back by listings or other reservations, and the split of the
    rest. Read-only (the execution computes it again under the property's lock)."""
    bens = [b for b in await list_beneficiaries(session, subject_user_id) if b.allocation_pct > 0]
    out = []
    for pid in await _held_properties(session, subject_user_id):
        prop = await session.get(Property, pid)
        net = await _holding(session, subject_user_id, pid)
        reserved = await secondary_service.reserved_units(session, subject_user_id, pid)
        available = max(0, net - reserved)
        out.append(
            {
                "property_id": pid,
                "title": prop.title if prop else str(pid),
                "net": net,
                "reserved": reserved,
                "available": available,
                "shares": _apportion(available, bens) if bens and available > 0 else {},
            }
        )
    return out


def _move(
    session: AsyncSession,
    *,
    from_user: uuid.UUID,
    to_user: uuid.UUID,
    prop: Property,
    units: int,
    fee_rate,
    ref_id: uuid.UUID,
) -> None:
    """The two ledger rows of one share: out of the holder's account, into the
    beneficiary's. Both point at their estate transfer (ref_id)."""
    session.add(
        OwnershipLedger(
            user_id=from_user,
            property_id=prop.id,
            investment_id=None,
            units=-units,
            unit_price=prop.unit_price,
            reason="estate_transfer_out",
            ref_id=ref_id,
        )
    )
    session.add(
        OwnershipLedger(
            user_id=to_user,
            property_id=prop.id,
            investment_id=None,
            units=units,
            unit_price=prop.unit_price,
            reason="estate_transfer_in",
            fee_rate=fee_rate,
            ref_id=ref_id,
        )
    )


async def _tell_received(
    session: AsyncSession, user_id: uuid.UUID, holder_id: uuid.UUID, lines: list[tuple[str, int]]
) -> None:
    """The beneficiary is told what reached their account (feed and email)."""
    if not lines:
        return
    holder = await session.get(User, holder_id)
    holder_name = _plain(holder.full_name if holder else "") or "the account holder"
    what = "; ".join(f"{n} unit{'' if n == 1 else 's'} of {title}" for title, n in lines)
    message = (
        f"As a designated beneficiary of {holder_name}, you received {what}. "
        "They are in your account now."
    )
    await notification_service.notify(
        session,
        user_id=user_id,
        type="estate",
        title="Assets were transferred to your account",
        message=message,
        email_category="investment_updates",
        force_email=True,
        email_body=(
            f"{message}\n\nSee them in your dashboard: {_site('/dashboard?tab=investments')}"
        ),
    )


async def _execute(
    session: AsyncSession,
    *,
    admin_id: uuid.UUID | None,
    subject_user_id: uuid.UUID,
    certificate_document_id: uuid.UUID | None = None,
    claim: EstateClaim | None = None,
    only: uuid.UUID | None = None,
) -> dict:
    """Record the event for a holder and split their available units, once. ``only`` (a
    claim): that beneficiary alone receives now, the others await their own claim. Without
    it (the admin API): every beneficiary with a verified account receives now. The caller
    commits."""
    event = (
        await session.execute(
            select(EstateEvent)
            .where(EstateEvent.subject_user_id == subject_user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if event is not None and event.status == "executed":
        return {"event": event, "replayed": True, "moves": []}
    if event is None:
        event = EstateEvent(
            subject_user_id=subject_user_id,
            status="verified",
            death_certificate_document_id=certificate_document_id,
            verified_by=admin_id,
            verified_at=_utcnow(),
            claim_id=claim.id if claim is not None else None,
            reason=claim.reason if claim is not None else "death",
            date_of_death=claim.date_of_death if claim is not None else None,
        )
        session.add(event)
        await session.flush()

    bens = [b for b in await list_beneficiaries(session, subject_user_id) if b.allocation_pct > 0]
    moves: list[dict] = []
    received: dict[uuid.UUID, list[tuple[str, int]]] = {}
    if bens:
        mgmt_rate = await settings_service.get_management_fee_pct(session)
        for pid in await _held_properties(session, subject_user_id):
            prop = (
                await session.execute(select(Property).where(Property.id == pid).with_for_update())
            ).scalar_one()
            net = await _holding(session, subject_user_id, pid)
            reserved = await secondary_service.reserved_units(session, subject_user_id, pid)
            available = net - reserved
            if available <= 0:
                continue
            split = _apportion(available, bens)
            for b in bens:
                units = split.get(str(b.id), 0)
                if units <= 0:
                    continue
                if only is not None:
                    now_real = b.id == only and b.beneficiary_user_id is not None
                    waiting = "awaiting_claim"
                else:
                    now_real = b.beneficiary_user_id is not None and b.status == "active"
                    waiting = "pending"
                transfer_id = uuid.uuid4()
                if now_real and b.beneficiary_user_id is not None:
                    _move(
                        session,
                        from_user=subject_user_id,
                        to_user=b.beneficiary_user_id,
                        prop=prop,
                        units=units,
                        fee_rate=mgmt_rate,
                        ref_id=transfer_id,
                    )
                    received.setdefault(b.beneficiary_user_id, []).append((prop.title, units))
                # a share that does not move now stays in the holder's ledger until it does
                status = "completed" if now_real else waiting
                session.add(
                    EstateTransfer(
                        id=transfer_id,
                        estate_event_id=event.id,
                        beneficiary_id=b.id,
                        property_id=pid,
                        units=units,
                        status=status,
                        materialized_at=_utcnow() if now_real else None,
                    )
                )
                moves.append(
                    {
                        "beneficiary_id": str(b.id),
                        "beneficiary": b.full_name,
                        "property": prop.title,
                        "units": units,
                        "status": status,
                    }
                )

    event.status = "executed"
    event.executed_at = _utcnow()
    await write_audit(
        session,
        action="estate.executed",
        entity_type="estate_event",
        entity_id=str(event.id),
        actor_id=admin_id,
        after={
            "subject": str(subject_user_id),
            "transfers": len(moves),
            "claim": str(claim.id) if claim is not None else None,
        },
    )
    for user_id, lines in received.items():
        await _tell_received(session, user_id, subject_user_id, lines)
    return {"event": event, "replayed": False, "moves": moves}


async def verify_death_and_execute(
    session: AsyncSession,
    *,
    admin_id: uuid.UUID | None,
    subject_user_id: uuid.UUID,
    certificate_document_id: uuid.UUID,
) -> dict:
    """Admin API: record a verified death (certificate already stored) and execute the
    register at once for every beneficiary with a verified account. Idempotent: a second
    confirm on an already-executed event is a no-op."""
    result = await _execute(
        session,
        admin_id=admin_id,
        subject_user_id=subject_user_id,
        certificate_document_id=certificate_document_id,
    )
    await session.commit()
    await session.refresh(result["event"])
    return {
        "estate_event_id": str(result["event"].id),
        "executed": True,
        "replayed": result["replayed"],
        "transfers": len(result["moves"]),
    }


async def _release(
    session: AsyncSession,
    b: EstateBeneficiary,
    *,
    to_user: uuid.UUID,
    statuses: tuple[str, ...],
) -> list[dict]:
    """Move a beneficiary's shares that were written at the event and not moved yet."""
    waiting = (
        (
            await session.execute(
                select(EstateTransfer)
                .where(
                    EstateTransfer.beneficiary_id == b.id,
                    EstateTransfer.status.in_(statuses),
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if not waiting:
        return []
    mgmt_rate = await settings_service.get_management_fee_pct(session)
    moves: list[dict] = []
    received: list[tuple[str, int]] = []
    holder_id: uuid.UUID | None = None
    for tr in waiting:
        event = await session.get(EstateEvent, tr.estate_event_id)
        if event is None or tr.property_id is None:
            continue
        holder_id = event.subject_user_id
        prop = (
            await session.execute(
                select(Property).where(Property.id == tr.property_id).with_for_update()
            )
        ).scalar_one()
        if await _holding(session, holder_id, tr.property_id) < tr.units:
            # defensive: the holder's account no longer has these units
            moves.append(
                {
                    "beneficiary_id": str(b.id),
                    "beneficiary": b.full_name,
                    "property": prop.title,
                    "units": tr.units,
                    "status": "missing",
                }
            )
            continue
        _move(
            session,
            from_user=holder_id,
            to_user=to_user,
            prop=prop,
            units=tr.units,
            fee_rate=mgmt_rate,
            ref_id=tr.id,
        )
        tr.status = "completed"
        tr.materialized_at = _utcnow()
        received.append((prop.title, tr.units))
        moves.append(
            {
                "beneficiary_id": str(b.id),
                "beneficiary": b.full_name,
                "property": prop.title,
                "units": tr.units,
                "status": "completed",
            }
        )
    if holder_id is not None:
        await _tell_received(session, to_user, holder_id, received)
    return moves


# --- materialization (pending -> real on beneficiary KYC) ------------------- #
async def materialize_for_user(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    """Link pending estate beneficiaries for this newly-KYC'd user (by email) and convert
    their PENDING estate transfers to real ledger moves. Idempotent. Shares that await a
    claim (``awaiting_claim``) are not touched here: they move when staff approve it."""
    user = await session.get(User, user_id)
    if user is None or not await _user_kyc_verified(session, user_id):
        return 0

    if user.email:
        unlinked = (
            (
                await session.execute(
                    select(EstateBeneficiary).where(
                        func.lower(EstateBeneficiary.email) == user.email.lower(),
                        EstateBeneficiary.beneficiary_user_id.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for b in unlinked:
            b.beneficiary_user_id = user_id

    linked = (
        (
            await session.execute(
                select(EstateBeneficiary).where(EstateBeneficiary.beneficiary_user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    count = 0
    for b in linked:
        b.status = "active"
        moves = await _release(session, b, to_user=user_id, statuses=("pending",))
        count += sum(1 for m in moves if m["status"] == "completed")
    return count


# --- claims: the public form -------------------------------------------------- #
def serialize_claim(claim: EstateClaim) -> dict:
    """What the claimant sees of their own claim. Documents by name only; nothing about the
    holder beyond what the claimant wrote."""
    return {
        "id": str(claim.id),
        "reference": claim.reference,
        "status": claim.status,
        "status_label": CLAIM_STATUSES.get(claim.status, claim.status),
        "reason": claim.reason,
        "holder_name": claim.holder_name,
        "certificate_no": claim.certificate_no,
        # staff's last message, once there is a decision or a question
        "message": claim.admin_note if claim.status != "submitted" else None,
        "documents": [
            {
                "kind": d.get("kind") or "other",
                "filename": d.get("filename") or "document",
            }
            for d in (claim.documents or [])
            if d.get("by") != "staff"
        ],
        "can_add_documents": claim.status in OPEN_CLAIM_STATUSES,
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
        "updated_at": claim.updated_at.isoformat() if claim.updated_at else None,
    }


def _store_claim_document(
    claim: EstateClaim, *, kind: str, filename: str | None, data: bytes, by: str
) -> dict:
    safe, content_type = checked_upload(filename, data)
    doc_id = uuid.uuid4().hex
    key = f"estate-claims/{claim.id}/{doc_id}-{safe}"
    storage.save(key, data, content_type)
    return {
        "id": doc_id,
        "kind": kind,
        "key": key,
        "filename": safe,
        "content_type": content_type,
        "size": len(data),
        "by": by,
        "at": _utcnow().isoformat(),
    }


async def _tell_staff(
    session: AsyncSession, claim: EstateClaim, *, title: str, message: str
) -> None:
    admins = (
        (await session.execute(select(UserRole.user_id).where(UserRole.role == "admin")))
        .scalars()
        .all()
    )
    for admin_id in admins:
        await notification_service.notify(
            session, user_id=admin_id, type="estate", title=title, message=message
        )
    notification_service.email_external(
        session,
        to_email=get_settings().support_inbox_email,
        subject=f"[Estate claim] {claim.reference}: {title}",
        body=(
            f"{message}\n\nReview it in the admin panel: "
            + get_settings().admin_url(f"/admin/estate-claims/{claim.id}")
        ),
        category="estate_claim",
    )


async def _tell_claimant(
    session: AsyncSession, claim: EstateClaim, *, title: str, paragraphs: list[str]
) -> None:
    """The claimant is always written to at the address on the claim (they may have no
    account yet); with an account, the first paragraph also goes to their feed. A claim sent
    as a visitor reaches the feed of the account opened since with that address, once the
    address is verified (the same rule that shows them the claim)."""
    body = "\n\n".join(
        [f"Hello {_plain(claim.claimant_name) or 'there'},", *paragraphs]
        + [f"Your claim reference is {claim.reference}."]
    )
    notification_service.email_external(
        session,
        to_email=claim.claimant_email,
        subject=f"{title} ({claim.reference})",
        body=body,
        category="estate_claim",
    )
    user_id = claim.claimant_user_id
    if user_id is None:
        account = await _account_of(session, claim.claimant_email)
        user_id = account.id if account is not None else None
    if user_id is not None:
        await notification_service.notify(
            session,
            user_id=user_id,
            type="estate",
            title=title,
            message=f"{paragraphs[0]} Reference: {claim.reference}.",
        )


async def _new_reference(session: AsyncSession) -> str:
    for _ in range(20):
        reference = _code("CLM")
        taken = await session.scalar(
            select(EstateClaim.id).where(EstateClaim.reference == reference)
        )
        if taken is None:
            return reference
    raise AppError("TRY_AGAIN", "Please try again.", status_code=503)


async def _user_by_email(session: AsyncSession, email: str | None) -> User | None:
    if not email:
        return None
    return (
        await session.execute(select(User).where(func.lower(User.email) == email.lower()))
    ).scalar_one_or_none()


async def _account_of(session: AsyncSession, email: str | None) -> User | None:
    """The account an address belongs to for certain: registered with it, with the address
    confirmed in it. An address nobody confirmed could have been typed at sign-up by anyone
    who knew it, so it ties neither a claim nor a transfer to that account."""
    user = await _user_by_email(session, email)
    return user if user is not None and user.email_verified else None


async def submit_claim(
    session: AsyncSession,
    *,
    fields: dict,
    files: list[tuple[str, str | None, bytes]],
    user_id: uuid.UUID | None,
    ip: str | None,
) -> EstateClaim:
    """A claim from the public page: who claims, about which holder, why, with the
    beneficiary certificate and the claimant's own identity document. ``files`` are
    ``(kind, file name, bytes)``.

    The answer never says whether the certificate number matched a record: that is for
    staff. The holder, if the number is theirs, is told at once: a living holder is the one
    who can say a claim is false."""
    name = _clean(fields.get("claimant_name"), 200)
    email = (_clean(fields.get("claimant_email"), 200) or "").lower()
    country = _clean(fields.get("claimant_country"), 80)
    holder_name = _clean(fields.get("holder_name"), 200)
    reason = str(fields.get("reason") or "")
    if not name or not country or not holder_name:
        raise AppError(
            "MISSING_FIELDS",
            "Your full name, your country and the account holder's name are required.",
            status_code=422,
        )
    if not _EMAIL.match(email):
        raise AppError("INVALID_EMAIL", "Enter a valid email address.", status_code=422)
    if reason not in CLAIM_REASONS:
        raise AppError("INVALID_REASON", "Choose the reason for the claim.", status_code=422)
    date_of_death: dt.date | None = None
    if fields.get("date_of_death"):
        try:
            date_of_death = dt.date.fromisoformat(str(fields["date_of_death"])[:10])
        except ValueError as exc:
            raise AppError(
                "INVALID_DATE", "Enter the date as a calendar date.", status_code=422
            ) from exc
        if date_of_death > _utcnow().date() or date_of_death.year < 1900:
            raise AppError("INVALID_DATE", "The date cannot be in the future.", status_code=422)
    if reason == "death" and date_of_death is None:
        raise AppError("DATE_REQUIRED", "Enter the date of death.", status_code=422)
    details = _clean(fields.get("details"), 4000)
    if reason == "other" and not details:
        raise AppError("DETAILS_REQUIRED", "Describe the reason for the claim.", status_code=422)

    kinds = [kind for kind, _name, _data in files]
    if any(kind not in CLAIM_DOC_KINDS for kind in kinds):
        raise AppError("INVALID_DOCUMENT", "Unknown document type.", status_code=422)
    if "certificate" not in kinds or "identity" not in kinds:
        raise AppError(
            "DOCUMENTS_REQUIRED",
            "Attach the beneficiary certificate and a copy of your identity document.",
            status_code=422,
        )
    if len(files) > MAX_CLAIM_DOCUMENTS:
        raise AppError("TOO_MANY_FILES", f"At most {MAX_CLAIM_DOCUMENTS} files.", status_code=422)

    certificate_no = normalize_certificate_no(fields.get("certificate_no"))
    recent = await session.scalar(
        select(func.count(EstateClaim.id)).where(
            func.lower(EstateClaim.claimant_email) == email,
            EstateClaim.created_at >= _utcnow() - dt.timedelta(days=1),
        )
    )
    if (recent or 0) >= CLAIMS_PER_EMAIL_PER_DAY:
        raise AppError(
            "CLAIM_LIMIT",
            "You have sent several claims today. Please wait for our reply, or contact support.",
            status_code=429,
        )
    if certificate_no:
        already = await session.scalar(
            select(EstateClaim.id).where(
                func.lower(EstateClaim.claimant_email) == email,
                EstateClaim.certificate_no == certificate_no,
                EstateClaim.status.in_(OPEN_CLAIM_STATUSES),
            )
        )
        if already:
            raise AppError(
                "CLAIM_OPEN",
                "You already have a claim with this certificate in review. We will write to "
                "you at this address.",
                status_code=409,
            )

    beneficiary = None
    if certificate_no:
        beneficiary = (
            await session.execute(
                select(EstateBeneficiary).where(EstateBeneficiary.certificate_no == certificate_no)
            )
        ).scalar_one_or_none()
    # the claim is the account's when it is sent from it, or to its confirmed address
    account = await session.get(User, user_id) if user_id else await _account_of(session, email)

    claim = EstateClaim(
        id=uuid.uuid4(),
        reference=await _new_reference(session),
        status="submitted",
        reason=reason,
        claimant_name=name,
        claimant_email=email,
        claimant_phone=_clean(fields.get("claimant_phone"), 40),
        claimant_country=country,
        claimant_id_type=_clean(fields.get("claimant_id_type"), 40),
        claimant_id_number=_clean(fields.get("claimant_id_number"), 80),
        relationship=_clean(fields.get("relationship"), 80),
        claimant_user_id=account.id if account else None,
        holder_name=holder_name,
        holder_email=(_clean(fields.get("holder_email"), 200) or "").lower() or None,
        certificate_no=certificate_no,
        date_of_death=date_of_death,
        details=details,
        documents=[],
        subject_user_id=beneficiary.owner_id if beneficiary else None,
        beneficiary_id=beneficiary.id if beneficiary else None,
        ip=ip,
    )
    # every file is checked before the first one is stored
    for _kind, filename, data in files:
        checked_upload(filename, data)
    claim.documents = [
        _store_claim_document(claim, kind=kind, filename=filename, data=data, by="claimant")
        for kind, filename, data in files
    ]
    session.add(claim)
    await session.flush()
    await write_audit(
        session,
        action="estate.claim.submitted",
        entity_type="estate_claim",
        entity_id=str(claim.id),
        actor_id=user_id,
        after={"reference": claim.reference, "reason": reason, "matched": beneficiary is not None},
        ip=ip,
    )

    await _tell_claimant(
        session,
        claim,
        title="We received your claim",
        paragraphs=[
            f"We received your claim about the account of {_plain(holder_name)}. Our team "
            "checks the certificate and the documents you sent, and writes to you at this "
            "address.",
            "Assets are transferred only to your own Capimax PropShare account, once your "
            "identity is verified in it. If you do not have one yet, create it with this "
            f"email address and confirm the address from the email we send you: {_site('/auth')}",
            "Nobody is given access to the account holder's account.",
        ],
    )
    what = CLAIM_REASONS[reason].lower()
    await _tell_staff(
        session,
        claim,
        title="New claim",
        message=(
            f"{_plain(name)} ({email}) claims on the account of {_plain(holder_name)}: {what}. "
            + (
                "The certificate number matches a beneficiary record."
                if beneficiary
                else "The certificate number matches NO beneficiary record."
            )
        ),
    )
    if beneficiary is not None:
        await notification_service.notify(
            session,
            user_id=beneficiary.owner_id,
            type="estate",
            title="A claim was submitted about your account",
            message=(
                "Someone presented a beneficiary certificate from your register and "
                f"submitted a claim about your account (reason given: {what}). If you are "
                "the account holder and this is wrong, contact support now. Nothing is "
                "transferred without a review by our team."
            ),
            email_category="security",
            force_email=True,
        )
    return claim


async def _claims_of(session: AsyncSession, user_id: uuid.UUID) -> list[EstateClaim]:
    """The caller's claims: sent while signed in, or sent with their (verified) address."""
    user = await session.get(User, user_id)
    mine = EstateClaim.claimant_user_id == user_id
    if user is not None and user.email and user.email_verified:
        mine = mine | (func.lower(EstateClaim.claimant_email) == user.email.lower())
    return list(
        (
            await session.execute(
                select(EstateClaim).where(mine).order_by(EstateClaim.created_at.desc()).limit(50)
            )
        )
        .scalars()
        .all()
    )


async def list_my_claims(session: AsyncSession, user_id: uuid.UUID) -> list[EstateClaim]:
    return await _claims_of(session, user_id)


async def add_claim_document(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    claim_id: uuid.UUID,
    kind: str,
    filename: str | None,
    data: bytes,
) -> EstateClaim:
    """The claimant adds a document to their open claim (what staff asked for). A claim
    that was waiting for them goes back to review, and staff are told."""
    claim = next((c for c in await _claims_of(session, user_id) if c.id == claim_id), None)
    if claim is None:
        raise AppError("NOT_FOUND", "Claim not found.", status_code=404)
    if claim.status not in OPEN_CLAIM_STATUSES:
        raise AppError("CLAIM_CLOSED", "This claim is closed.", status_code=409)
    if kind not in CLAIM_DOC_KINDS:
        raise AppError("INVALID_DOCUMENT", "Unknown document type.", status_code=422)
    docs = list(claim.documents or [])
    if len(docs) >= MAX_CLAIM_DOCUMENTS:
        raise AppError(
            "TOO_MANY_FILES", f"At most {MAX_CLAIM_DOCUMENTS} files per claim.", status_code=422
        )
    docs.append(
        _store_claim_document(claim, kind=kind, filename=filename, data=data, by="claimant")
    )
    claim.documents = docs
    was_waiting = claim.status == "needs_info"
    if was_waiting:
        claim.status = "in_review"
    claim.updated_at = _utcnow()
    await write_audit(
        session,
        action="estate.claim.document_added",
        entity_type="estate_claim",
        entity_id=str(claim.id),
        actor_id=user_id,
        after={"kind": kind},
    )
    await _tell_staff(
        session,
        claim,
        title="The claimant added a document",
        message=(
            f"{_plain(claim.claimant_name)} added a document ({CLAIM_DOC_KINDS[kind].lower()}) "
            f"to claim {claim.reference}." + (" It is back in review." if was_waiting else "")
        ),
    )
    await session.flush()
    return claim


# --- claims: staff review ------------------------------------------------------ #
def _same(a: object, b: object) -> bool:
    """Two names or two document numbers that a person would call the same: letters and
    digits only, any case."""
    norm = [re.sub(r"[^0-9a-z]", "", str(v or "").casefold()) for v in (a, b)]
    return bool(norm[0]) and norm[0] == norm[1]


async def _locked_claim(session: AsyncSession, claim_id: uuid.UUID) -> EstateClaim:
    claim = (
        await session.execute(
            select(EstateClaim).where(EstateClaim.id == claim_id).with_for_update()
        )
    ).scalar_one_or_none()
    if claim is None:
        raise AppError("NOT_FOUND", "Claim not found.", status_code=404)
    return claim


def _require_open_claim(claim: EstateClaim) -> None:
    if claim.status not in OPEN_CLAIM_STATUSES:
        raise AppError("ALREADY_DECIDED", "This claim was already decided.", status_code=409)


async def claim_review(session: AsyncSession, claim_id: uuid.UUID) -> dict:
    """Everything the staff page shows for one claim: what was sent beside what the register
    holds, the checks that follow from comparing them, what stands in the way of an
    approval, and what an approval would move."""
    claim = await session.get(EstateClaim, claim_id)
    if claim is None:
        raise AppError("NOT_FOUND", "Claim not found.", status_code=404)
    ben = (
        await session.get(EstateBeneficiary, claim.beneficiary_id) if claim.beneficiary_id else None
    )
    holder = await session.get(User, ben.owner_id) if ben else None
    account = (
        await session.get(User, claim.claimant_user_id)
        if claim.claimant_user_id
        else await _account_of(session, claim.claimant_email)
    )
    # an account opened with the claim's address that never confirmed it is not offered as
    # where the share goes: staff see it, and say whose it is
    unconfirmed = await _user_by_email(session, claim.claimant_email) if account is None else None
    kyc = await _kyc_status(session, account.id) if account else "none"
    event = (
        (
            await session.execute(
                select(EstateEvent).where(EstateEvent.subject_user_id == ben.owner_id)
            )
        ).scalar_one_or_none()
        if ben
        else None
    )
    meta = _meta(ben.meta) if ben else {}

    # what an approval moves: the claimant's part of the split, or (the event was recorded
    # for an earlier claim) the shares written for them that day
    to_move: list[dict] = []
    done: list[dict] = []
    holdings: list[dict] = []
    if ben:
        holdings = await preview_split(session, ben.owner_id)
        rows = (
            await session.execute(
                select(EstateTransfer, Property.title)
                .outerjoin(Property, Property.id == EstateTransfer.property_id)
                .where(EstateTransfer.beneficiary_id == ben.id)
                .order_by(EstateTransfer.created_at)
            )
        ).all()
        for tr, title in rows:
            line = {"property": title or "-", "units": tr.units, "status": tr.status}
            (to_move if tr.status in _WAITING else done).append(line)
        if event is None or event.status != "executed":
            to_move = [
                {"property": h["title"], "units": h["shares"].get(str(ben.id), 0), "status": "now"}
                for h in holdings
                if h["shares"].get(str(ben.id), 0) > 0
            ]

    checks: list[dict] = []

    def check(ok: bool | None, good: str, bad: str) -> None:
        level = "warn" if ok is None else ("ok" if ok else "bad")
        checks.append({"level": level, "text": good if ok else bad})

    if ben is None:
        check(
            False,
            "",
            f"The certificate number {claim.certificate_no or '(none given)'} matches no "
            "beneficiary record. It may be mistyped, or the holder removed the record.",
        )
    else:
        check(True, f"The certificate number {ben.certificate_no} is a record of the register.", "")
        check(
            _same(claim.claimant_name, ben.full_name),
            "The claimant's name is the name on the record.",
            "The claimant's name is NOT the name on the record.",
        )
        if meta.get("idNumber") and claim.claimant_id_number:
            check(
                _same(claim.claimant_id_number, meta["idNumber"]),
                "The identity document number is the one on the record.",
                "The identity document number is NOT the one on the record.",
            )
        else:
            check(None, "", "No identity document number to compare (missing on one side).")
        check(
            _same(claim.holder_name, holder.full_name if holder else ""),
            "The account holder's name is as the claimant wrote it.",
            "The account holder's name differs from what the claimant wrote.",
        )
        if not (ben.id_documents or []):
            check(None, "", "The holder kept no copy of this person's identity document.")
        if claim.date_of_death:
            day = dt.datetime.combine(
                claim.date_of_death + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC
            )
            changed = ben.updated_at or ben.created_at
            if changed is not None and changed >= day:
                check(
                    False,
                    "",
                    f"This record was created or changed on {changed:%Y-%m-%d}, AFTER the "
                    f"stated date of death ({claim.date_of_death:%Y-%m-%d}).",
                )
        check(
            None,
            "",
            f"The certificate presented must show Version {ben.version}: an older copy was "
            "issued before the holder changed this record.",
        )
    if account is not None and ben is not None:
        check(
            _same(account.full_name, ben.full_name),
            "The claimant's account is in the name on the record.",
            "The claimant's account is in a different name from the record.",
        )

    blockers: list[str] = []
    if ben is None:
        blockers.append("No beneficiary record is matched to this claim.")
    if account is None and unconfirmed is not None:
        blockers.append(
            f"An account is registered with {claim.claimant_email}, but the address was never "
            "confirmed in it, so it is not taken as the claimant's. The claimant confirms the "
            "address from their account, or you link the account once you know it is theirs."
        )
    elif account is None:
        blockers.append(
            f"The claimant has no account yet (looked up by {claim.claimant_email}). "
            "They must register, or you can link the account they registered with."
        )
    elif ben is not None and account.id == ben.owner_id:
        blockers.append("The claimant's account is the account holder's own account.")
    elif kyc != "verified":
        blockers.append(f"The claimant's identity is not verified in their account (KYC: {kyc}).")
    if not any(d.get("kind") == "evidence" for d in (claim.documents or [])):
        blockers.append(
            "No official supporting document is on file (for a death: the death "
            "certificate). Ask the claimant for it, or attach it below."
        )
    if ben is not None and ben.allocation_pct <= 0:
        blockers.append("This record carries no share: there is nothing to transfer.")
    elif ben is not None and not to_move:
        blockers.append(
            "There is nothing to transfer to this claimant: "
            + (
                "their share was already transferred."
                if done
                else "the holder has no units free to transfer."
            )
        )

    wallet = (
        await session.scalar(select(Wallet.balance).where(Wallet.user_id == ben.owner_id))
        if ben
        else None
    )
    others = (
        [b for b in await list_beneficiaries(session, ben.owner_id) if b.id != ben.id]
        if ben
        else []
    )
    return {
        "claim": claim,
        "beneficiary": ben,
        "meta": meta,
        "holder": holder,
        "account": account,
        "unconfirmed": unconfirmed,
        "kyc": kyc,
        "event": event,
        "checks": checks,
        "blockers": blockers,
        "to_move": to_move,
        "done": done,
        "holdings": holdings,
        "wallet_balance": wallet,
        "others": others,
    }


async def claim_start_review(
    session: AsyncSession, *, claim_id: uuid.UUID, actor_id: uuid.UUID | None
) -> EstateClaim:
    claim = await _locked_claim(session, claim_id)
    _require_open_claim(claim)
    claim.status = "in_review"
    claim.updated_at = _utcnow()
    await write_audit(
        session,
        action="estate.claim.in_review",
        entity_type="estate_claim",
        entity_id=str(claim.id),
        actor_id=actor_id,
    )
    return claim


async def claim_request_info(
    session: AsyncSession, *, claim_id: uuid.UUID, note: str | None, actor_id: uuid.UUID | None
) -> EstateClaim:
    claim = await _locked_claim(session, claim_id)
    _require_open_claim(claim)
    note = _clean(note, 2000)
    if not note:
        raise AppError("NOTE_REQUIRED", "Write what the claimant must send.", status_code=422)
    claim.status = "needs_info"
    claim.admin_note = note
    claim.updated_at = _utcnow()
    await write_audit(
        session,
        action="estate.claim.needs_info",
        entity_type="estate_claim",
        entity_id=str(claim.id),
        actor_id=actor_id,
        after={"note": note},
    )
    await _tell_claimant(
        session,
        claim,
        title="We need more information for your claim",
        paragraphs=[
            f"To continue with your claim we need: {note}",
            "Sign in to your Capimax PropShare account and add it to the claim on this page: "
            f"{_site('/estate-claim')}",
        ],
    )
    return claim


async def claim_reject(
    session: AsyncSession, *, claim_id: uuid.UUID, note: str | None, actor_id: uuid.UUID | None
) -> EstateClaim:
    claim = await _locked_claim(session, claim_id)
    _require_open_claim(claim)
    note = _clean(note, 2000)
    if not note:
        raise AppError(
            "NOTE_REQUIRED", "Write why: the claimant receives this message.", status_code=422
        )
    claim.status = "rejected"
    claim.admin_note = note
    claim.decided_by = actor_id
    claim.decided_at = _utcnow()
    claim.updated_at = claim.decided_at
    await write_audit(
        session,
        action="estate.claim.rejected",
        entity_type="estate_claim",
        entity_id=str(claim.id),
        actor_id=actor_id,
        after={"note": note},
    )
    await _tell_claimant(
        session,
        claim,
        title="Your claim was not approved",
        paragraphs=[
            f"After review, we could not approve your claim. Message from our team: {note}",
            f"If you believe this is a mistake, contact support: {_site('/support')}",
        ],
    )
    return claim


async def claim_attach_document(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    kind: str,
    filename: str | None,
    data: bytes,
    actor_id: uuid.UUID | None,
) -> EstateClaim:
    """Staff add a document they received another way (by email, on a ticket)."""
    claim = await _locked_claim(session, claim_id)
    _require_open_claim(claim)
    if kind not in CLAIM_DOC_KINDS:
        raise AppError("INVALID_DOCUMENT", "Unknown document type.", status_code=422)
    docs = list(claim.documents or [])
    docs.append(_store_claim_document(claim, kind=kind, filename=filename, data=data, by="staff"))
    claim.documents = docs
    claim.updated_at = _utcnow()
    await write_audit(
        session,
        action="estate.claim.document_attached",
        entity_type="estate_claim",
        entity_id=str(claim.id),
        actor_id=actor_id,
        after={"kind": kind},
    )
    return claim


async def claim_set_match(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    certificate_no: str | None = None,
    account_email: str | None = None,
    actor_id: uuid.UUID | None,
) -> EstateClaim:
    """Staff correct what a claim is matched to: the certificate number (mistyped by the
    claimant) and the account the claimant registered with (another address)."""
    claim = await _locked_claim(session, claim_id)
    _require_open_claim(claim)
    before = {
        "certificate_no": claim.certificate_no,
        "claimant_user_id": str(claim.claimant_user_id or ""),
    }
    number = normalize_certificate_no(certificate_no)
    if number:
        ben = (
            await session.execute(
                select(EstateBeneficiary).where(EstateBeneficiary.certificate_no == number)
            )
        ).scalar_one_or_none()
        if ben is None:
            raise AppError(
                "NO_SUCH_CERTIFICATE",
                f"No beneficiary record has the number {number}.",
                status_code=422,
            )
        claim.certificate_no = number
        claim.beneficiary_id = ben.id
        claim.subject_user_id = ben.owner_id
    email = (_clean(account_email, 200) or "").lower()
    if email:
        account = await _user_by_email(session, email)
        if account is None:
            raise AppError(
                "NO_SUCH_ACCOUNT", f"No account is registered with {email}.", status_code=422
            )
        claim.claimant_user_id = account.id
    claim.updated_at = _utcnow()
    await write_audit(
        session,
        action="estate.claim.matched",
        entity_type="estate_claim",
        entity_id=str(claim.id),
        actor_id=actor_id,
        before=before,
        after={
            "certificate_no": claim.certificate_no,
            "claimant_user_id": str(claim.claimant_user_id or ""),
        },
    )
    return claim


async def claim_approve(
    session: AsyncSession, *, claim_id: uuid.UUID, actor_id: uuid.UUID | None
) -> dict:
    """Approve a claim and move the claimant's share to the claimant's own account. Refused
    while anything on the review page stands in the way (the same list the page shows).

    The first approved claim for a holder records the event and writes every beneficiary's
    share; only the claimant's moves. A later claim for the same holder moves the share
    written for its claimant that day."""
    claim = await _locked_claim(session, claim_id)
    _require_open_claim(claim)
    review = await claim_review(session, claim_id)
    if review["blockers"]:
        raise AppError("APPROVAL_BLOCKED", review["blockers"][0], status_code=422)
    ben: EstateBeneficiary = review["beneficiary"]
    account: User = review["account"]

    # the register now says who this person is on the platform: the account staff verified
    ben.beneficiary_user_id = account.id
    ben.status = "active"
    claim.claimant_user_id = account.id
    await session.flush()

    result = await _execute(
        session, admin_id=actor_id, subject_user_id=ben.owner_id, claim=claim, only=ben.id
    )
    event: EstateEvent = result["event"]
    moves = [m for m in result["moves"] if m["beneficiary_id"] == str(ben.id)]
    if result["replayed"]:
        moves = await _release(session, ben, to_user=account.id, statuses=_WAITING)
    moved = [m for m in moves if m["status"] == "completed"]
    if not moved:
        # nothing changed hands: the claim stays open rather than being called approved
        raise AppError(
            "NOTHING_TO_TRANSFER",
            "Nothing could be transferred to this claimant: the holder's account no longer "
            "has these units.",
            status_code=409,
        )

    claim.status = "approved"
    claim.estate_event_id = event.id
    claim.decided_by = actor_id
    claim.decided_at = _utcnow()
    claim.updated_at = claim.decided_at
    summary = "; ".join(f"{m['units']} unit(s) of {m['property']}" for m in moved)
    claim.admin_note = f"Approved. Transferred to your account: {summary}."
    await write_audit(
        session,
        action="estate.claim.approved",
        entity_type="estate_claim",
        entity_id=str(claim.id),
        actor_id=actor_id,
        after={
            "event": str(event.id),
            "beneficiary": str(ben.id),
            "to": str(account.id),
            "transfers": len(moved),
        },
    )
    notification_service.email_external(
        session,
        to_email=claim.claimant_email if claim.claimant_email != account.email.lower() else None,
        subject=f"Your claim was approved ({claim.reference})",
        body=(
            f"Hello {_plain(claim.claimant_name) or 'there'},\n\n"
            f"Your claim {claim.reference} was approved. Transferred to your Capimax "
            f"PropShare account: {summary}.\n\n"
            f"See them in your dashboard: {_site('/dashboard?tab=investments')}"
        ),
        category="estate_claim",
    )
    return {"claim": claim, "event": event, "moves": moves}
