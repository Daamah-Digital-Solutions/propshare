"""Nova Sukuk — pay for units with a Nova Digital Finance sukuk certificate (0032).

Client feedback 2026-09-27: every property offers the same payment methods as the sister
platform Capimax BRX, Nova Sukuk among them. As there, no money passes through the platform
and there is no Nova API: the investor uploads the certificate (PDF) and staff review it.

  * The units are HELD from submission (like a checkout's reservation, but with no time limit,
    as a review takes time): a purchase waits as a pending investment, an installment plan in
    ``pending_review``. The certificate must cover the purchase total (subtotal + platform
    fee), or the down payment and its fee.
  * Staff approve -> the purchase is confirmed / the plan starts, its down payment booked as
    paid by the certificate — exactly like a paid checkout. Staff reject (with a reason the
    investor reads) -> the units go back on sale.
  * An approved certificate PLEDGES its units to Nova Finance: they cannot be sold, exited,
    gifted or transferred (``secondary_service.reserved_units``) until staff release the pledge
    once Nova Finance clears it. The investor is shown this before submitting (the SPA's Nova
    pledge notice).
"""

from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    EmailOutbox,
    InstallmentPlan,
    Investment,
    Property,
    SukukCertificate,
    User,
    UserRole,
)
from app.services import installment_service, investment_service, notification_service
from app.services.integrations import storage

MAX_CERTIFICATE_BYTES = 10 * 1024 * 1024
_PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True)
class CertificateUpload:
    filename: str
    data: bytes
    certificate_no: str | None = None
    issuer: str | None = None
    certificate_value: decimal.Decimal | None = None
    valid_until: dt.date | None = None


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _clean(value: str | None, limit: int) -> str | None:
    text = " ".join((value or "").split())[:limit]
    return text or None


def check_upload(cert: CertificateUpload) -> None:
    """Refuse what cannot be a Nova certificate BEFORE anything is reserved."""
    if not cert.data:
        raise AppError(
            "CERTIFICATE_REQUIRED", "Attach the Nova certificate (PDF).", status_code=422
        )
    if len(cert.data) > MAX_CERTIFICATE_BYTES:
        raise AppError(
            "FILE_TOO_LARGE", "The certificate must be 10 MB or smaller.", status_code=422
        )
    if not cert.data.startswith(_PDF_MAGIC):
        raise AppError(
            "CERTIFICATE_NOT_PDF", "The certificate must be a PDF file.", status_code=422
        )
    if cert.certificate_value is not None and not cert.certificate_value.is_finite():
        raise AppError("INVALID_VALUE", "The certificate value must be a number.", status_code=422)
    if cert.certificate_value is not None and cert.certificate_value < 0:
        raise AppError(
            "INVALID_VALUE", "The certificate value cannot be negative.", status_code=422
        )
    if cert.valid_until is not None and cert.valid_until < _utcnow().date():
        raise AppError(
            "CERTIFICATE_EXPIRED",
            f"This certificate expired on {cert.valid_until.isoformat()}.",
            status_code=422,
        )


async def _record(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    property_id: uuid.UUID,
    units: int,
    amount_due: decimal.Decimal,
    cert: CertificateUpload,
    investment_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
) -> SukukCertificate:
    from app.services.document_service import _safe_filename

    row_id = uuid.uuid4()
    # the name is only shown to staff; the object key never depends on it
    name = re.sub(r"\.{2,}", ".", _safe_filename(cert.filename or "certificate.pdf"))
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    key = f"sukuk-certificates/{row_id}/certificate.pdf"
    storage.save(key, cert.data, "application/pdf")
    row = SukukCertificate(
        id=row_id,
        user_id=user_id,
        property_id=property_id,
        investment_id=investment_id,
        plan_id=plan_id,
        units=units,
        amount_due=amount_due,
        certificate_no=_clean(cert.certificate_no, 80),
        issuer=_clean(cert.issuer, 120),
        certificate_value=cert.certificate_value,
        valid_until=cert.valid_until,
        file_key=key,
        file_name=name,
        content_type="application/pdf",
        file_size=len(cert.data),
        status="pending",
    )
    session.add(row)
    await session.flush()
    await write_audit(
        session,
        action="sukuk.submitted",
        entity_type="sukuk_certificate",
        entity_id=str(row.id),
        actor_id=user_id,
        after={
            "kind": "purchase" if investment_id else "installment",
            "units": units,
            "amount_due": str(amount_due),
            "property_id": str(property_id),
        },
    )
    return row


def serialize(row: SukukCertificate, prop: Property | None) -> dict:
    return {
        "certificate_id": row.id,
        "kind": "purchase" if row.investment_id else "installment",
        "status": row.status,
        "investment_id": row.investment_id,
        "plan_id": row.plan_id,
        "property_id": row.property_id,
        "property_title": (prop.title if prop else None) or "Property",
        "property_slug": prop.slug if prop else None,
        "units": row.units,
        "amount_due": str(row.amount_due),
        "certificate_no": row.certificate_no,
        "issuer": row.issuer,
        "review_note": row.review_note if row.status != "pending" else None,
        "created_at": row.created_at,
        "reviewed_at": row.reviewed_at,
        "released_at": row.released_at,
    }


async def _serialized(session: AsyncSession, row: SukukCertificate) -> dict:
    return serialize(row, await session.get(Property, row.property_id))


# --- submit -------------------------------------------------------------------------------- #
async def submit_purchase(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    property_id: uuid.UUID,
    amount: float,
    idempotency_key: str,
    cert: CertificateUpload,
) -> dict:
    """Buy units paying with a Nova Sukuk certificate: hold them and send it to staff."""
    existing = (
        await session.execute(
            select(Investment).where(Investment.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        row = (
            await session.execute(
                select(SukukCertificate).where(SukukCertificate.investment_id == existing.id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise AppError(
                "IDEMPOTENCY_KEY_REUSED",
                "This request key was already used for another purchase.",
                status_code=409,
            )
        return await _serialized(session, row)
    check_upload(cert)
    inv, prop = await investment_service.reserve_for_sukuk(
        session,
        user_id=user_id,
        property_id=property_id,
        amount=amount,
        idempotency_key=idempotency_key,
    )
    row = await _record(
        session,
        user_id=user_id,
        property_id=prop.id,
        units=inv.units,
        amount_due=inv.total_charged or inv.amount,
        cert=cert,
        investment_id=inv.id,
    )
    await _notify_submitted(session, row, prop)
    return serialize(row, prop)


async def submit_plan(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    property_id: uuid.UUID,
    amount: float,
    duration_months: int,
    idempotency_key: str,
    cert: CertificateUpload,
) -> dict:
    """Start an installment plan whose down payment a Nova Sukuk certificate covers: hold the
    plan's units and send the certificate to staff."""
    existing = (
        await session.execute(
            select(InstallmentPlan).where(InstallmentPlan.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        row = (
            await session.execute(
                select(SukukCertificate).where(SukukCertificate.plan_id == existing.id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise AppError(
                "IDEMPOTENCY_KEY_REUSED",
                "This request key was already used for another plan.",
                status_code=409,
            )
        return await _serialized(session, row)
    check_upload(cert)
    plan, prop, down = await installment_service.open_plan(
        session,
        investor_id=user_id,
        property_id=property_id,
        amount=amount,
        duration_months=duration_months,
        idempotency_key=idempotency_key,
        status="pending_review",
        method="sukuk",
    )
    row = await _record(
        session,
        user_id=user_id,
        property_id=prop.id,
        # the units the down payment vests are the ones the certificate pays for (and pledges)
        units=down.vest_units,
        amount_due=down.total_amount,
        cert=cert,
        plan_id=plan.id,
    )
    await _notify_submitted(session, row, prop)
    return serialize(row, prop)


# --- staff decisions ----------------------------------------------------------------------- #
async def _lock(session: AsyncSession, certificate_id: uuid.UUID) -> SukukCertificate:
    row = (
        await session.execute(
            select(SukukCertificate)
            .where(SukukCertificate.id == certificate_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        raise AppError("NOT_FOUND", "Certificate not found", status_code=404)
    return row


async def approve(
    session: AsyncSession, *, certificate_id: uuid.UUID, admin_id: uuid.UUID, note: str | None
) -> SukukCertificate:
    row = await _lock(session, certificate_id)
    if row.status != "pending":
        raise AppError(
            "INVALID_TRANSITION",
            "Only a certificate waiting for review can be approved.",
            status_code=409,
        )
    if row.investment_id:
        await investment_service.confirm_sukuk_purchase(
            session, investment_id=row.investment_id, certificate_id=row.id
        )
    else:
        await installment_service.start_sukuk_plan(
            session, plan_id=row.plan_id, certificate_id=row.id
        )
    now = _utcnow()
    row.status = "approved"
    row.review_note = _clean(note, 2000)
    row.reviewed_by = admin_id
    row.reviewed_at = now
    row.updated_at = now
    await write_audit(
        session,
        action="sukuk.approved",
        entity_type="sukuk_certificate",
        entity_id=str(row.id),
        actor_id=admin_id,
        after={"units": row.units, "amount_due": str(row.amount_due)},
    )
    prop = await session.get(Property, row.property_id)
    title = prop.title if prop else "the property"
    what = (
        f"Your {row.units} unit(s) of {title} are confirmed."
        if row.investment_id
        else f"Your installment plan for {title} has started: the certificate covers its down "
        "payment, and the next installments come from your wallet on their dates."
    )
    await notification_service.notify(
        session,
        user_id=row.user_id,
        type="investment",
        title="Nova certificate approved",
        message=(
            f"{what} The units it pays for stay pledged to Nova Finance: you can't sell, exit, "
            "gift or transfer them until Nova Finance releases them."
        ),
        email_category="investment_updates",
    )
    return row


async def reject(
    session: AsyncSession, *, certificate_id: uuid.UUID, admin_id: uuid.UUID, reason: str
) -> SukukCertificate:
    reason = _clean(reason, 2000) or ""
    if len(reason) < 3:
        raise AppError(
            "REASON_REQUIRED",
            "Say why the certificate is not accepted: the investor reads it.",
            status_code=422,
        )
    row = await _lock(session, certificate_id)
    if row.status != "pending":
        raise AppError(
            "INVALID_TRANSITION",
            "Only a certificate waiting for review can be rejected.",
            status_code=409,
        )
    if row.investment_id:
        await investment_service.release_sukuk_purchase(
            session, investment_id=row.investment_id, reason="sukuk_rejected"
        )
    else:
        await installment_service.cancel_sukuk_plan(
            session, plan_id=row.plan_id, reason="sukuk_rejected"
        )
    now = _utcnow()
    row.status = "rejected"
    row.review_note = reason
    row.reviewed_by = admin_id
    row.reviewed_at = now
    row.updated_at = now
    await write_audit(
        session,
        action="sukuk.rejected",
        entity_type="sukuk_certificate",
        entity_id=str(row.id),
        actor_id=admin_id,
        after={"reason": reason},
    )
    prop = await session.get(Property, row.property_id)
    title = prop.title if prop else "the property"
    await notification_service.notify(
        session,
        user_id=row.user_id,
        type="investment",
        title="Nova certificate not accepted",
        message=(
            f"Your Nova Sukuk certificate for {title} was not accepted: {reason} "
            "The units held for you were released. You can submit a new certificate, or pay "
            "another way."
        ),
        email_category="investment_updates",
    )
    return row


async def release_pledge(
    session: AsyncSession, *, certificate_id: uuid.UUID, admin_id: uuid.UUID, note: str | None
) -> SukukCertificate:
    """Nova Finance cleared the financing: the units are free to sell, exit, gift or transfer."""
    row = await _lock(session, certificate_id)
    if row.status != "approved":
        raise AppError(
            "INVALID_TRANSITION",
            "Only an approved certificate has a pledge to release.",
            status_code=409,
        )
    now = _utcnow()
    row.status = "released"
    row.released_by = admin_id
    row.released_at = now
    row.updated_at = now
    note = _clean(note, 2000)
    if note:
        row.review_note = f"{row.review_note}\nPledge released: {note}" if row.review_note else note
    await write_audit(
        session,
        action="sukuk.pledge_released",
        entity_type="sukuk_certificate",
        entity_id=str(row.id),
        actor_id=admin_id,
        after={"units": row.units, "note": note},
    )
    prop = await session.get(Property, row.property_id)
    title = prop.title if prop else "the property"
    await notification_service.notify(
        session,
        user_id=row.user_id,
        type="investment",
        title="Nova pledge released",
        message=(
            f"Nova Finance released the pledge on your {row.units} unit(s) of {title}: you can "
            "now sell, exit, gift or transfer them."
        ),
        email_category="investment_updates",
    )
    return row


# --- reads --------------------------------------------------------------------------------- #
async def list_mine(session: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    rows = (
        (
            await session.execute(
                select(SukukCertificate)
                .where(SukukCertificate.user_id == user_id)
                .order_by(SukukCertificate.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [await _serialized(session, r) for r in rows]


# --- notices ------------------------------------------------------------------------------- #
async def _notify_submitted(session: AsyncSession, row: SukukCertificate, prop: Property) -> None:
    what = (
        f"{row.units} unit(s) of {prop.title}"
        if row.investment_id
        else f"the down payment of an installment plan for {prop.title}"
    )
    await notification_service.notify(
        session,
        user_id=row.user_id,
        type="investment",
        title="Nova certificate received — under review",
        message=(
            f"We received your Nova Sukuk certificate for {what} ({row.amount_due} USD due). "
            "Our team reviews it and tells you the outcome here and by email; the units are "
            "held for you meanwhile."
        ),
        email_category="investment_updates",
    )
    investor = await session.get(User, row.user_id)
    who = (investor.full_name or investor.email) if investor else "an investor"
    admins = (
        (await session.execute(select(UserRole.user_id).where(UserRole.role == "admin")))
        .scalars()
        .all()
    )
    for admin_id in admins:
        await notification_service.notify(
            session,
            user_id=admin_id,
            type="sukuk_review",
            title="Nova certificate waiting for review",
            message=(
                f"{who} paid for {what} with a Nova Sukuk certificate ({row.amount_due} USD). "
                "Review it in the admin panel under Nova Sukuk."
            ),
        )
    inbox = get_settings().support_inbox_email
    if inbox:
        session.add(
            EmailOutbox(
                user_id=None,
                to_email=inbox,
                subject=f"[Nova Sukuk] {prop.title} — {row.amount_due} USD from {who}",
                body=(
                    f"{who}"
                    + (f" <{investor.email}>" if investor else "")
                    + f" paid for {what} with a Nova Sukuk certificate.\n"
                    f"Amount it must cover: {row.amount_due} USD\n"
                    f"Certificate no.: {row.certificate_no or '-'}"
                    f" · issuer: {row.issuer or '-'}\n\n"
                    "Review it in the admin panel: "
                    + get_settings().admin_url(f"/admin/sukuk-review/{row.id}")
                ),
                category="sukuk_review",
                status="pending",
            )
        )
