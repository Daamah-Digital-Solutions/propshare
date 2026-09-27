"""Broker leads (client feedback #2): clients a broker invites, properties / projects a broker
brings for listing — the rows of the broker's "Listings & Referrals" table.

Client invitations keep the signed-off attribution rule intact: the invitation email carries
the broker's own share link (``/auth?ref=CODE``), and the client is linked to the broker only
when they sign up through it (``broker_service.resolve_signup_referral`` stays the only writer
of ``broker_referrals``). An existing account is never linked afterwards, and the broker is
never told whether an address already has an account.

A property / project lead is an introduction for staff to review; it never becomes a
marketplace listing by itself (listings are created in the admin Listing Editor, which can
start from a lead). No money attaches to a lead.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import BrokerLead, EmailOutbox, User, UserRole
from app.services import broker_service, notification_service
from app.services.integrations import storage

logger = logging.getLogger(__name__)

LISTING_KINDS = ("property", "project")
# a broker may invite this many clients a day (the platform sends each one an email)
INVITES_PER_DAY = 20
MAX_LEAD_FILES = 6
MAX_LEAD_FILE_BYTES = 12 * 1024 * 1024

# staff decisions on a property / project lead
DECISIONS = {"contacted": "contacted", "decline": "declined", "listed": "listed"}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _clean(value: Any, limit: int = 300) -> str | None:
    text = str(value or "").strip()
    return text[:limit] or None


async def _broker_name(session: AsyncSession, broker_id: uuid.UUID) -> str:
    broker = await session.get(User, broker_id)
    return (broker.full_name or broker.email) if broker else "Your broker"


# --- clients ---------------------------------------------------------------- #
async def invite_client(
    session: AsyncSession,
    *,
    broker_id: uuid.UUID,
    name: str,
    email: str,
    phone: str | None = None,
    notes: str | None = None,
) -> BrokerLead:
    """Record the client and email them the broker's share link. Linking happens only if they
    sign up through it."""
    email = email.strip().lower()
    broker = await session.get(User, broker_id)
    if broker is not None and broker.email.lower() == email:
        raise AppError("SELF_INVITE", "You cannot invite yourself.", status_code=422)
    pending = await session.scalar(
        select(BrokerLead.id).where(
            BrokerLead.broker_id == broker_id,
            BrokerLead.kind == "client",
            BrokerLead.status == "invited",
            func.lower(BrokerLead.email) == email,
        )
    )
    if pending:
        raise AppError(
            "ALREADY_INVITED",
            "You already invited this person; the invitation is pending.",
            status_code=409,
        )
    today = await session.scalar(
        select(func.count(BrokerLead.id)).where(
            BrokerLead.broker_id == broker_id,
            BrokerLead.kind == "client",
            BrokerLead.created_at >= _now() - datetime.timedelta(days=1),
        )
    )
    if (today or 0) >= INVITES_PER_DAY:
        raise AppError(
            "INVITE_LIMIT",
            f"You can invite up to {INVITES_PER_DAY} clients a day. Please try again tomorrow.",
            status_code=429,
        )
    lead = BrokerLead(
        broker_id=broker_id,
        kind="client",
        status="invited",
        name=_clean(name, 120) or "Client",
        email=email,
        phone=_clean(phone, 40),
        details={"notes": _clean(notes, 1000)} if _clean(notes, 1000) else {},
    )
    session.add(lead)
    await session.flush()
    code = await broker_service.get_or_create_code(session, broker_id)
    link = f"{get_settings().app_base_url.rstrip('/')}/auth?ref={code.code}"
    who = await _broker_name(session, broker_id)
    # The broker gets the in-app row; the invitee (not a member yet) gets the email.
    await notification_service.notify(
        session,
        user_id=broker_id,
        type="broker",
        title="Client invited",
        message=(
            f"{lead.name} was invited. They join your clients when they sign up through "
            "your link."
        ),
        email_category="invite",
        email_to=email,
        force_email=True,
        email_subject=f"{who} invites you to Capimax PropShare",
        email_body=(
            f"Hello {lead.name},\n\n{who} invites you to Capimax PropShare, where you can own "
            "units of income-producing and off-plan real estate.\n\n"
            f"Create your account with this link so {who} can assist you: {link}\n\n"
            "If you did not expect this invitation, you can ignore this email."
        ),
    )
    await write_audit(
        session,
        action="broker.lead.client_invited",
        entity_type="broker_lead",
        entity_id=str(lead.id),
        actor_id=broker_id,
        after={"kind": "client"},
    )
    return lead


async def mark_joined(
    session: AsyncSession, *, broker_id: uuid.UUID, client: User
) -> BrokerLead | None:
    """Called at signup once the client is linked to ``broker_id`` through the share link:
    the broker's pending invitation for that address (if any) becomes 'joined'."""
    lead = (
        await session.execute(
            select(BrokerLead)
            .where(
                BrokerLead.broker_id == broker_id,
                BrokerLead.kind == "client",
                BrokerLead.status == "invited",
                func.lower(BrokerLead.email) == client.email.lower(),
            )
            .order_by(BrokerLead.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if lead is None:
        return None
    lead.status = "joined"
    lead.client_id = client.id
    lead.updated_at = _now()
    await notification_service.notify(
        session,
        user_id=broker_id,
        type="broker",
        title="Your client joined",
        message=f"{lead.name} created an account through your link and is now one of your clients.",
    )
    return lead


# --- properties / projects ---------------------------------------------------- #
async def submit_listing_lead(
    session: AsyncSession,
    *,
    broker_id: uuid.UUID,
    kind: str,
    fields: dict[str, Any],
    files: list[tuple[str, bytes, str | None]],
) -> BrokerLead:
    from app.services.document_service import _safe_filename, content_type_for

    if kind not in LISTING_KINDS:
        raise AppError("INVALID_KIND", "kind must be 'property' or 'project'.", status_code=422)
    title = _clean(fields.get("title"), 200)
    location = _clean(fields.get("location"), 200)
    owner_name = _clean(fields.get("owner_name"), 120)
    if not title or not location or not owner_name:
        raise AppError(
            "MISSING_FIELDS",
            "Title, location and the owner's or developer's name are required.",
            status_code=422,
        )
    if len(files) > MAX_LEAD_FILES:
        raise AppError("TOO_MANY_FILES", f"At most {MAX_LEAD_FILES} documents.", status_code=422)
    details = {
        "location": location,
        "property_type": _clean(fields.get("property_type"), 60),
        "estimated_value": _clean(fields.get("estimated_value"), 40),
        "expected_completion": _clean(fields.get("expected_completion"), 40),
        "owner_name": owner_name,
        "notes": _clean(fields.get("notes"), 2000),
    }
    lead = BrokerLead(
        broker_id=broker_id,
        kind=kind,
        status="new",
        name=title,
        email=_clean(fields.get("owner_email"), 200),
        phone=_clean(fields.get("owner_phone"), 40),
        details={k: v for k, v in details.items() if v},
        documents=[],
    )
    session.add(lead)
    await session.flush()
    docs = []
    for filename, data, content_type in files:
        if len(data) > MAX_LEAD_FILE_BYTES:
            raise AppError("FILE_TOO_LARGE", f"'{filename}' exceeds 12 MB.", status_code=422)
        safe = _safe_filename(filename)
        ct = content_type or content_type_for(safe)
        key = f"broker-leads/{lead.id}/{uuid.uuid4().hex}-{safe}"
        storage.save(key, data, ct)
        docs.append({"label": safe, "key": key, "filename": safe, "content_type": ct})
    lead.documents = docs
    what = "project" if kind == "project" else "property"
    who = await _broker_name(session, broker_id)
    await notification_service.notify(
        session,
        user_id=broker_id,
        type="broker",
        title=f"{what.capitalize()} received",
        message=f'We received "{title}". Our team reviews it and updates its status in your table.',
    )
    admins = (
        (await session.execute(select(UserRole.user_id).where(UserRole.role == "admin")))
        .scalars()
        .all()
    )
    for admin_id in admins:
        await notification_service.notify(
            session,
            user_id=admin_id,
            type="broker",
            title=f"New {what} from a broker",
            message=f'{who} introduced "{title}" ({location}). Review it under Broker Leads.',
        )
    inbox = get_settings().support_inbox_email
    if inbox:
        session.add(
            EmailOutbox(
                user_id=None,
                to_email=inbox,
                subject=f"[Broker lead] {what}: {title} — from {who}",
                body=(
                    f'{who} introduced a {what} for listing: "{title}" ({location}).\n'
                    f"Owner / developer: {owner_name}"
                    + (f" <{lead.email}>" if lead.email else "")
                    + (f", phone {lead.phone}" if lead.phone else "")
                    + f"\nDocuments: {len(docs)}\n\n"
                    f"Review it in the admin panel: /admin/broker-leads/{lead.id}"
                ),
                category="broker_lead",
                status="pending",
            )
        )
    await write_audit(
        session,
        action="broker.lead.listing_submitted",
        entity_type="broker_lead",
        entity_id=str(lead.id),
        actor_id=broker_id,
        after={"kind": kind, "documents": len(docs)},
    )
    return lead


# --- the broker's table ------------------------------------------------------- #
async def list_for_broker(session: AsyncSession, broker_id: uuid.UUID) -> list[BrokerLead]:
    return list(
        (
            await session.execute(
                select(BrokerLead)
                .where(BrokerLead.broker_id == broker_id)
                .order_by(BrokerLead.created_at.desc())
                .limit(500)
            )
        )
        .scalars()
        .all()
    )


async def cancel(session: AsyncSession, *, broker_id: uuid.UUID, lead_id: uuid.UUID) -> BrokerLead:
    """The broker withdraws a pending invitation, or a property / project staff has not
    picked up yet."""
    lead = await session.get(BrokerLead, lead_id)
    if lead is None or lead.broker_id != broker_id:
        raise AppError("NOT_FOUND", "Not found.", status_code=404)
    if lead.kind == "client" and lead.status == "invited":
        lead.status = "cancelled"
    elif lead.kind in LISTING_KINDS and lead.status == "new":
        lead.status = "withdrawn"
    else:
        raise AppError("NOT_CANCELLABLE", "This can no longer be withdrawn.", status_code=409)
    lead.updated_at = _now()
    await write_audit(
        session,
        action="broker.lead.withdrawn",
        entity_type="broker_lead",
        entity_id=str(lead.id),
        actor_id=broker_id,
        after={"status": lead.status},
    )
    return lead


def serialize(lead: BrokerLead) -> dict:
    """What the broker sees. Documents by name only (storage keys never leave the server)."""
    return {
        "id": str(lead.id),
        "kind": lead.kind,
        "status": lead.status,
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "details": lead.details or {},
        "documents": [str(d.get("filename") or "document") for d in (lead.documents or [])],
        "admin_note": lead.admin_note,
        "property_id": str(lead.property_id) if lead.property_id else None,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
    }


# --- staff decisions ------------------------------------------------------------ #
async def admin_decide(
    session: AsyncSession,
    *,
    lead_id: uuid.UUID,
    decision: str,
    note: str | None,
    actor_id: uuid.UUID | None,
    property_id: uuid.UUID | None = None,
) -> BrokerLead:
    lead = await session.get(BrokerLead, lead_id)
    if lead is None or lead.kind not in LISTING_KINDS:
        raise AppError("NOT_FOUND", "Lead not found.", status_code=404)
    if decision not in DECISIONS:
        raise AppError("INVALID_DECISION", f"Unknown decision {decision!r}.", status_code=400)
    if lead.status in ("listed", "declined", "withdrawn"):
        raise AppError("ALREADY_DECIDED", "This lead was already closed.", status_code=409)
    note = _clean(note, 2000)
    if decision == "decline" and not note:
        raise AppError(
            "NOTE_REQUIRED", "Write why — the broker will see this message.", status_code=422
        )
    lead.status = DECISIONS[decision]
    lead.admin_note = note
    lead.decided_by = actor_id
    lead.decided_at = _now()
    lead.updated_at = lead.decided_at
    if decision == "listed" and property_id is not None:
        lead.property_id = property_id
    await write_audit(
        session,
        action=f"broker.lead.{lead.status}",
        entity_type="broker_lead",
        entity_id=str(lead.id),
        actor_id=actor_id,
        after={"status": lead.status, "note": note, "property_id": str(property_id or "")},
    )
    title = {
        "contacted": f'We are in touch about "{lead.name}"',
        "declined": f'"{lead.name}" will not be listed',
        "listed": f'"{lead.name}" is being listed',
    }[lead.status]
    message = {
        "contacted": "Our team has contacted the owner / developer you introduced.",
        "declined": "After review, we will not list it.",
        "listed": "Our team created a listing from your introduction.",
    }[lead.status]
    await notification_service.notify(
        session,
        user_id=lead.broker_id,
        type="broker",
        title=title,
        message=message + (f" Message from our team: {note}" if note else ""),
        email_category="broker_updates",
        force_email=True,
    )
    return lead
