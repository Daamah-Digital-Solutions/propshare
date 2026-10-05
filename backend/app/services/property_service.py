"""Property catalog service (Phase 3).

The single source of truth for the marketplace. Public reads only ever return
``active``/``funded`` rows (replicating the old RLS "anyone can view active"
rule). Owners create drafts and submit them for review; admins approve a draft to
``active`` (go-live), send it back to ``draft`` with a message (request changes),
decline it (``closed``, never public) or close it. The owner is told every step
(in-app + email) and staff are told of every submission. Every admin moderation
action is written to the append-only audit log.
"""

from __future__ import annotations

import datetime
import logging
import re
import unicodedata
import uuid
from decimal import Decimal

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Property
from app.models.base import PropertyStatus
from app.models.identity import User
from app.schemas.property import OWNERSHIP_MODELS

PUBLIC_STATUSES = (PropertyStatus.active, PropertyStatus.funded)
EDITABLE_STATUSES = (PropertyStatus.draft, PropertyStatus.under_review)

logger = logging.getLogger(__name__)


def _slugify(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "property"
    return f"{base}-{uuid.uuid4().hex[:6]}"


def _validate_model(model: str, *, current: str | None = None) -> str:
    """Known key AND available: option / future / shared-development are hidden until their
    mechanics exist (a listing that already has one may keep it, nobody can pick one)."""
    if model not in OWNERSHIP_MODELS:
        raise AppError(
            "INVALID_MODEL",
            f"model must be one of {list(OWNERSHIP_MODELS)}",
            status_code=422,
        )
    from app.services import listing_service  # local: listing_service imports this module

    return listing_service.validate_model_choice(model, current=current)


def _num(value: Decimal | float | int | None) -> float | None:
    return float(value) if value is not None else None


def _developer_name(prop: Property, owner_names: dict[uuid.UUID, str | None]) -> str | None:
    dev = (prop.content or {}).get("developer") if isinstance(prop.content, dict) else None
    if isinstance(dev, dict) and dev.get("name"):
        return str(dev["name"])
    if prop.owner_id is not None:
        return owner_names.get(prop.owner_id)
    return None


def developer_slug(name: str | None) -> str | None:
    """URL key of a developer profile, derived from the developer name every listing shows.

    Unicode-aware so an Arabic company name keeps its letters instead of collapsing to "".
    The same function builds the link on the property page and resolves the profile, so the
    two can never disagree."""
    if not name:
        return None
    norm = unicodedata.normalize("NFKC", name).casefold()
    slug = re.sub(r"[^\w]+", "-", norm, flags=re.UNICODE).replace("_", "-").strip("-")
    return slug[:80] or None


def serialize_summary(prop: Property, owner_names: dict[uuid.UUID, str | None]) -> dict:
    images = prop.images or []
    return {
        "id": prop.id,
        "slug": prop.slug,
        "title": prop.title,
        "subtitle": prop.subtitle,
        "location": prop.location,
        "country": prop.country,
        "city": prop.city,
        "model": prop.model,
        "property_type": prop.property_type,
        "status": str(prop.status),
        "image": images[0] if images else None,
        "total_value": _num(prop.total_value),
        "minimum_investment": _num(prop.minimum_investment),
        "unit_price": _num(prop.unit_price),
        # how an under-construction listing is bought: installments | full | both
        "offplan_payment": prop.offplan_payment or "installments",
        # set once the unit price has changed: what the listing was launched at
        "launch_price": _num(prop.launch_price) if prop.launch_price is not None else None,
        "target_yield": _num(prop.target_yield),
        "expected_yield": _num(prop.expected_yield),
        "capital_appreciation": _num(prop.capital_appreciation),
        "total_return": _num(prop.total_return),
        "funded_amount": _num(prop.funded_amount),
        "funding_progress": _num(prop.funding_progress),
        "total_units": prop.total_units,
        "available_units": prop.available_units,
        "investors_count": prop.investors_count,
        "developer_name": _developer_name(prop, owner_names),
        "developer_slug": developer_slug(_developer_name(prop, owner_names)),
    }


def serialize_detail(prop: Property, owner_names: dict[uuid.UUID, str | None]) -> dict:
    data = serialize_summary(prop, owner_names)
    data.update(
        {
            "description": prop.description,
            "images": prop.images or [],
            "expected_completion": prop.expected_completion,
            "spv_name": prop.spv_name,
            "spv_registration": prop.spv_registration,
            "legal_structure": prop.legal_structure,
            "fees": prop.fees if isinstance(prop.fees, dict) else None,
            "content": prop.content if isinstance(prop.content, dict) else {},
            "owner_id": prop.owner_id,
            "created_at": prop.created_at,
            "updated_at": prop.updated_at,
            "submitted_at": prop.submitted_at,
            "review_note": prop.review_note,
            "review_outcome": prop.review_outcome,
            "reviewed_at": prop.reviewed_at,
        }
    )
    return data


async def get_owned_for_update(
    session: AsyncSession, owner_id: uuid.UUID, prop_id: uuid.UUID
) -> Property:
    """Load a property the caller owns (403 if not theirs, 404 if missing)."""
    prop = await session.get(Property, prop_id)
    if prop is None:
        raise AppError("PROPERTY_NOT_FOUND", "Property not found.", status_code=404)
    if prop.owner_id != owner_id:
        raise AppError("NOT_PROPERTY_OWNER", "You do not own this property.", status_code=403)
    return prop


async def _owner_names(session: AsyncSession, props: list[Property]) -> dict[uuid.UUID, str | None]:
    ids = {p.owner_id for p in props if p.owner_id is not None}
    if not ids:
        return {}
    res = await session.execute(select(User.id, User.full_name).where(User.id.in_(ids)))
    return {row[0]: row[1] for row in res.all()}


# --- Public reads ---------------------------------------------------------- #
# The least an investor can put into a listing: its minimum investment, or one unit.
ENTRY_AMOUNT = func.coalesce(Property.minimum_investment, Property.unit_price)


async def lowest_entry(session: AsyncSession) -> float | None:
    """The smallest amount that buys into any published listing with units left (None when
    there is none)."""
    value = await session.scalar(
        select(func.min(ENTRY_AMOUNT)).where(
            Property.status.in_(PUBLIC_STATUSES), Property.available_units > 0
        )
    )
    return float(value) if value is not None else None


async def list_public(
    session: AsyncSession,
    *,
    model: str | None = None,
    property_type: str | None = None,
    country: str | None = None,
    city: str | None = None,
    status: str | None = None,
    min_yield: float | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    max_entry: float | None = None,
    search: str | None = None,
    sort: str = "newest",
    limit: int = 60,
    offset: int = 0,
) -> tuple[list[Property], int]:
    """Published listings. ``max_entry`` keeps only those an investor can enter with that much
    (the listing's minimum investment, or one unit when it sets none) that still have units."""
    conds: list[ColumnElement[bool]] = [Property.status.in_(PUBLIC_STATUSES)]
    if status in ("active", "funded"):
        conds = [Property.status == PropertyStatus(status)]
    if model:
        conds.append(Property.model == model)
    if property_type:
        conds.append(Property.property_type == property_type)
    if country:
        conds.append(Property.country == country)
    if city:
        conds.append(Property.city == city)
    if min_yield is not None:
        conds.append(func.coalesce(Property.expected_yield, Property.target_yield) >= min_yield)
    if min_price is not None:
        conds.append(Property.total_value >= min_price)
    if max_price is not None:
        conds.append(Property.total_value <= max_price)
    if max_entry is not None:
        conds.append(ENTRY_AMOUNT <= max_entry)
        conds.append(Property.available_units > 0)
    if search:
        like = f"%{search.lower()}%"
        conds.append(
            func.lower(Property.title).like(like) | func.lower(Property.location).like(like)
        )

    total = await session.scalar(select(func.count()).select_from(Property).where(*conds)) or 0

    stmt = select(Property).where(*conds)
    if sort == "price-low":
        stmt = stmt.order_by(Property.total_value.asc())
    elif sort == "price-high":
        stmt = stmt.order_by(Property.total_value.desc())
    elif sort == "yield-high":
        stmt = stmt.order_by(func.coalesce(Property.expected_yield, Property.target_yield).desc())
    elif sort == "funded":
        stmt = stmt.order_by(Property.funding_progress.desc())
    elif sort == "entry-low":
        stmt = stmt.order_by(ENTRY_AMOUNT.asc(), Property.created_at.desc())
    else:  # newest
        stmt = stmt.order_by(Property.created_at.desc())
    stmt = stmt.limit(min(limit, 200)).offset(max(offset, 0))

    rows = list((await session.execute(stmt)).scalars().all())
    return rows, int(total)


async def public_developer_profile(session: AsyncSession, slug: str) -> dict:
    """Everything the platform can honestly say about one developer: the facts entered on its
    listings (name, logo, about, website, rating, projects) and the live figures of every
    PUBLIC listing it has here. Drafts and closed listings never leak through."""
    wanted = developer_slug(slug)
    if not wanted:
        raise AppError("DEVELOPER_NOT_FOUND", "Developer not found.", status_code=404)
    rows = list(
        (
            await session.execute(
                select(Property)
                .where(Property.status.in_(PUBLIC_STATUSES))
                .order_by(Property.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    owner_names = await _owner_names(session, rows)
    mine = [p for p in rows if developer_slug(_developer_name(p, owner_names)) == wanted]
    if not mine:
        raise AppError("DEVELOPER_NOT_FOUND", "Developer not found.", status_code=404)

    def first(key: str):
        """The newest listing that filled a field wins; nothing is invented."""
        for p in mine:
            dev = (p.content or {}).get("developer") if isinstance(p.content, dict) else None
            if isinstance(dev, dict) and dev.get(key) not in (None, ""):
                return dev[key]
        return None

    summaries = [serialize_summary(p, owner_names) for p in mine]
    return {
        "slug": wanted,
        "name": summaries[0]["developer_name"],
        "logo": first("logo"),
        "about": first("about"),
        "website": first("website"),
        "rating": first("rating"),
        "projects_completed": first("projectsCompleted"),
        "stats": {
            "listings": len(mine),
            "active": sum(1 for p in mine if p.status == PropertyStatus.active),
            "funded": sum(1 for p in mine if p.status == PropertyStatus.funded),
            "total_raised": float(sum((p.funded_amount or 0) for p in mine)),
            "investors": sum(int(p.investors_count or 0) for p in mine),
        },
        "properties": summaries,
    }


# --- Preview-before-publish ------------------------------------------------- #
# A draft/under-review listing is invisible publicly. The admin Listing Editor mints a
# signed, property-scoped, 24-hour token so the owner can open the real public page
# ("as investors will see it") before approving it. The token grants READ of that one
# property (+ its documents) and nothing else.
PREVIEW_TTL_SECONDS = 24 * 3600


def _preview_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().jwt_secret, salt="property-preview")


def make_preview_token(prop_id: uuid.UUID) -> str:
    return _preview_serializer().dumps(str(prop_id))


def verify_preview_token(token: str | None, prop_id: uuid.UUID) -> bool:
    if not token:
        return False
    try:
        value = _preview_serializer().loads(token, max_age=PREVIEW_TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    return value == str(prop_id)


async def get_public_detail(
    session: AsyncSession, id_or_slug: str, *, preview_token: str | None = None
) -> Property:
    prop = await _resolve(session, id_or_slug)
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    if prop.status not in PUBLIC_STATUSES and not verify_preview_token(preview_token, prop.id):
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    return prop


async def _resolve(session: AsyncSession, id_or_slug: str) -> Property | None:
    try:
        pid = uuid.UUID(id_or_slug)
    except ValueError:
        res = await session.execute(select(Property).where(Property.slug == id_or_slug))
        return res.scalar_one_or_none()
    return await session.get(Property, pid)


# Public aliases for the admin panel (same rules as the owner API).
slugify = _slugify
validate_model = _validate_model


# --- Owner writes ---------------------------------------------------------- #
async def create(session: AsyncSession, *, owner_id: uuid.UUID, data: dict) -> Property:
    model = _validate_model(data.get("model") or "ready-income")
    prop = Property(
        owner_id=owner_id,
        title=data["title"],
        subtitle=data.get("subtitle"),
        description=data.get("description"),
        location=data["location"],
        country=data.get("country"),
        city=data.get("city"),
        property_type=data["property_type"],
        model=model,
        status=PropertyStatus.draft,
        total_value=data["total_value"],
        unit_price=data["unit_price"],
        total_units=data.get("total_units") or 100,
        available_units=data.get("total_units") or 100,
        minimum_investment=data.get("minimum_investment") or 500,
        target_yield=data.get("target_yield"),
        expected_yield=data.get("expected_yield"),
        capital_appreciation=data.get("capital_appreciation"),
        total_return=data.get("total_return"),
        expected_completion=data.get("expected_completion"),
        spv_name=data.get("spv_name"),
        spv_registration=data.get("spv_registration"),
        legal_structure=data.get("legal_structure"),
        images=data.get("images") or [],
        content=data.get("content") or {},
        funded_amount=0,
        funding_progress=0,
        investors_count=0,
        slug=_slugify(data["title"]),
    )
    session.add(prop)
    await session.flush()
    await write_audit(
        session,
        action="property.create",
        entity_type="property",
        entity_id=str(prop.id),
        actor_id=owner_id,
        after={"title": prop.title, "status": str(prop.status)},
    )
    return prop


_EDITABLE_FIELDS = (
    "title",
    "subtitle",
    "description",
    "location",
    "country",
    "city",
    "property_type",
    "total_value",
    "unit_price",
    "minimum_investment",
    "target_yield",
    "expected_yield",
    "capital_appreciation",
    "total_return",
    "expected_completion",
    "spv_name",
    "spv_registration",
    "legal_structure",
    "images",
    "content",
)


async def update(
    session: AsyncSession, *, owner_id: uuid.UUID, prop_id: uuid.UUID, data: dict
) -> Property:
    prop = await _owned_or_403(session, owner_id, prop_id)
    if prop.status not in EDITABLE_STATUSES:
        raise AppError(
            "PROPERTY_LOCKED",
            "Only draft or under-review properties can be edited.",
            status_code=409,
        )
    if "model" in data and data["model"] is not None:
        prop.model = _validate_model(data["model"], current=prop.model)
    if data.get("total_units") is not None:
        # available stays in lock-step with total while no units are sold yet (pre-Phase-5).
        prop.total_units = data["total_units"]
        prop.available_units = data["total_units"]
    for field in _EDITABLE_FIELDS:
        if field in data and data[field] is not None:
            setattr(prop, field, data[field])
    await session.flush()
    return prop


async def submit(session: AsyncSession, *, owner_id: uuid.UUID, prop_id: uuid.UUID) -> Property:
    prop = await _owned_or_403(session, owner_id, prop_id)
    if prop.status != PropertyStatus.draft:
        raise AppError(
            "INVALID_TRANSITION",
            "Only a draft can be submitted for review.",
            status_code=409,
        )
    if prop.review_outcome == "declined":  # pragma: no cover - a declined listing is closed
        raise AppError("INVALID_TRANSITION", "This listing was not approved.", status_code=409)
    resubmission = prop.submitted_at is not None
    prop.status = PropertyStatus.under_review
    prop.submitted_at = datetime.datetime.now(datetime.UTC)
    # the owner has acted on the last review; its note stays in the audit trail
    prop.review_note = None
    prop.review_outcome = None
    await write_audit(
        session,
        action="property.submit",
        entity_type="property",
        entity_id=str(prop.id),
        actor_id=owner_id,
        after={"status": str(prop.status), "resubmission": resubmission},
    )
    await _notify_submitted(session, prop, resubmission=resubmission)
    return prop


# --- Owner submission notices ------------------------------------------------ #
# The owner hears about every step of their submission (in-app + email), the admins get an
# in-app notice and the support inbox one email for each submission to review. All of it is
# best-effort: a notification problem must never undo the submission or the decision.
_OUTCOME_OF_ACTION = {
    "approve": "approved",
    "request_changes": "changes_requested",
    "reject": "changes_requested",  # legacy name: back to draft for the owner to fix
    "decline": "declined",
    "close": "closed",
}


async def _notify_owner(
    session: AsyncSession, prop: Property, *, title: str, message: str, link: str
) -> None:
    if prop.owner_id is None:
        return
    from app.services import notification_service

    try:
        await notification_service.notify(
            session,
            user_id=prop.owner_id,
            type="property",
            title=title,
            message=message,
            email_category="listing",
            force_email=True,  # transactional: the owner always hears the outcome
            email_subject=title,
            email_body=f"{message}\n\n{link}",
        )
    except Exception:  # noqa: BLE001 — best-effort, never block the listing change
        logger.exception("listing notice to the owner failed (property=%s)", prop.id)


async def _notify_submitted(session: AsyncSession, prop: Property, *, resubmission: bool) -> None:
    from app.models import EmailOutbox, UserRole
    from app.services import notification_service

    site = get_settings().app_base_url.rstrip("/")
    what = "resubmitted" if resubmission else "received"
    await _notify_owner(
        session,
        prop,
        title=f"Listing {what} — under review",
        message=(
            f'We {what} "{prop.title}". Our team is reviewing it and will tell you the outcome '
            "here and by email. You can still add documents from your dashboard meanwhile."
        ),
        link=f"Follow it from your dashboard: {site}/owner-dashboard?tab=properties",
    )
    owner = await session.get(User, prop.owner_id) if prop.owner_id else None
    who = (owner.full_name or owner.email) if owner else "an owner"
    try:
        admins = (
            (await session.execute(select(UserRole.user_id).where(UserRole.role == "admin")))
            .scalars()
            .all()
        )
        for admin_id in admins:
            await notification_service.notify(
                session,
                user_id=admin_id,
                type="listing_review",
                title="Owner listing waiting for review",
                message=(
                    f'"{prop.title}" from {who} was {what}. Review it in the admin panel under '
                    "Owner Submissions."
                ),
            )
        inbox = get_settings().support_inbox_email
        if inbox:
            session.add(
                EmailOutbox(
                    user_id=None,
                    to_email=inbox,
                    subject=f"[Listing review] {prop.title} — {what} from {who}",
                    body=(
                        f'A property owner {what} "{prop.title}" ({prop.location}) for review.\n'
                        f"Owner: {who}"
                        + (f" <{owner.email}>" if owner else "")
                        + (f", phone {owner.phone}" if owner and owner.phone else "")
                        + "\n\nReview it in the admin panel: "
                        + get_settings().admin_url(f"/admin/owner-submissions/{prop.id}")
                    ),
                    category="listing_review",
                    status="pending",
                )
            )
    except Exception:  # noqa: BLE001 — best-effort, never block the submission
        logger.exception("listing review notice to staff failed (property=%s)", prop.id)


async def _notify_decision(
    session: AsyncSession, prop: Property, *, action: str, note: str | None
) -> None:
    site = get_settings().app_base_url.rstrip("/")
    dashboard = f"{site}/owner-dashboard?tab=properties"
    note_line = f"\n\nMessage from our team: {note}" if note else ""
    if action == "approve":
        await _notify_owner(
            session,
            prop,
            title="Your listing is live",
            message=f'"{prop.title}" was approved and is now open for investment.',
            link=f"See it on the marketplace: {site}/property/{prop.slug or prop.id}",
        )
    elif action in ("request_changes", "reject"):
        await _notify_owner(
            session,
            prop,
            title="Changes requested on your listing",
            message=(
                f'Our team reviewed "{prop.title}" and needs some changes before it can go '
                f"live. Update it from your dashboard and send it back for review.{note_line}"
            ),
            link=f"Edit and resubmit: {dashboard}",
        )
    elif action == "decline":
        await _notify_owner(
            session,
            prop,
            title="Your listing was not approved",
            message=f'After review, "{prop.title}" was not approved.{note_line}',
            link=f"Questions? Reply to this email or contact support. Your listings: {dashboard}",
        )
    elif action == "close":
        await _notify_owner(
            session,
            prop,
            title="Your listing was unpublished",
            message=f'"{prop.title}" is no longer visible to investors.{note_line}',
            link=f"Your listings: {dashboard}",
        )


async def list_owner(session: AsyncSession, owner_id: uuid.UUID) -> list[Property]:
    res = await session.execute(
        select(Property).where(Property.owner_id == owner_id).order_by(Property.created_at.desc())
    )
    return list(res.scalars().all())


async def _owned_or_403(session: AsyncSession, owner_id: uuid.UUID, prop_id: uuid.UUID) -> Property:
    prop = await session.get(Property, prop_id)
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    if prop.owner_id != owner_id:
        raise AppError("FORBIDDEN", "You do not own this property.", status_code=403)
    return prop


# --- Admin moderation ------------------------------------------------------ #
async def admin_moderate(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    prop_id: uuid.UUID,
    action: str,
    reason: str | None = None,
) -> Property:
    prop = await session.get(Property, prop_id)
    if prop is None:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    note = (reason or "").strip()[:2000] or None
    if action in ("reject", "request_changes", "decline") and prop.status not in EDITABLE_STATUSES:
        # Sending back or declining is for a submission that is not on the market. A live
        # listing going back to an editable draft would let its units be reset under the
        # investors who hold them; take a live listing down with "close" instead.
        raise AppError(
            "INVALID_TRANSITION",
            "Only a listing that is not live can be sent back or declined. "
            "Use Close (unpublish) for a live listing.",
            status_code=409,
        )
    before = {"status": str(prop.status)}
    if action == "approve":
        # Publish checklist — the ONE gate every publish path goes through (Listing Editor,
        # SQLAdmin action, admin API). Blocks anything the public page would render as 0% or
        # empty for this model, inconsistent units/minimum, and unavailable models.
        from app.services import listing_service

        positions = await listing_service.count_positions(session, prop.id)
        milestones = await listing_service.list_milestones(session, prop.id)
        check = listing_service.publish_checklist(
            prop, milestones=len(milestones), has_positions=positions > 0
        )
        if check["blockers"]:
            raise AppError(
                "PUBLISH_BLOCKED",
                "This listing cannot be published yet. Fix these first:\n- "
                + "\n- ".join(check["blockers"]),
                status_code=409,
                details={"blockers": check["blockers"]},
            )
        prop.status = PropertyStatus.active
    elif action in ("reject", "request_changes"):
        # back to the owner as a draft; the note tells them what to change
        if action == "request_changes" and not note:
            raise AppError(
                "NOTE_REQUIRED",
                "Write what the owner should change — they will see this message.",
                status_code=422,
            )
        prop.status = PropertyStatus.draft
    elif action == "decline":
        # a final "no" for a submission: closed, never public, not editable by the owner
        if not note:
            raise AppError(
                "NOTE_REQUIRED",
                "Write why the listing is not approved — the owner will see this message.",
                status_code=422,
            )
        prop.status = PropertyStatus.closed
    elif action == "close":
        prop.status = PropertyStatus.closed
    else:  # pragma: no cover - guarded by the route
        raise AppError("INVALID_ACTION", f"Unknown action {action!r}", status_code=400)
    prop.review_outcome = _OUTCOME_OF_ACTION[action]
    prop.review_note = None if action == "approve" else note
    prop.reviewed_at = datetime.datetime.now(datetime.UTC)
    prop.reviewed_by = actor_id
    await write_audit(
        session,
        action=f"property.{action}",
        entity_type="property",
        entity_id=str(prop.id),
        actor_id=actor_id,
        before=before,
        after={"status": str(prop.status), "reason": note},
    )
    await _notify_decision(session, prop, action=action, note=note)
    return prop
