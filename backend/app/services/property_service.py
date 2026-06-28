"""Property catalog service (Phase 3).

The single source of truth for the marketplace. Public reads only ever return
``active``/``funded`` rows (replicating the old RLS "anyone can view active"
rule). Owners create drafts and submit them for review; admins approve a draft to
``active`` (go-live), reject it back to ``draft`` with a reason, or close it.
Every admin moderation action is written to the append-only audit log.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import Property
from app.models.base import PropertyStatus
from app.models.identity import User
from app.schemas.property import OWNERSHIP_MODELS

PUBLIC_STATUSES = (PropertyStatus.active, PropertyStatus.funded)
EDITABLE_STATUSES = (PropertyStatus.draft, PropertyStatus.under_review)


def _slugify(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "property"
    return f"{base}-{uuid.uuid4().hex[:6]}"


def _validate_model(model: str) -> str:
    if model not in OWNERSHIP_MODELS:
        raise AppError(
            "INVALID_MODEL",
            f"model must be one of {list(OWNERSHIP_MODELS)}",
            status_code=422,
        )
    return model


def _num(value: Decimal | float | int | None) -> float | None:
    return float(value) if value is not None else None


def _developer_name(prop: Property, owner_names: dict[uuid.UUID, str | None]) -> str | None:
    dev = (prop.content or {}).get("developer") if isinstance(prop.content, dict) else None
    if isinstance(dev, dict) and dev.get("name"):
        return str(dev["name"])
    if prop.owner_id is not None:
        return owner_names.get(prop.owner_id)
    return None


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
        }
    )
    return data


async def _owner_names(session: AsyncSession, props: list[Property]) -> dict[uuid.UUID, str | None]:
    ids = {p.owner_id for p in props if p.owner_id is not None}
    if not ids:
        return {}
    res = await session.execute(select(User.id, User.full_name).where(User.id.in_(ids)))
    return {row[0]: row[1] for row in res.all()}


# --- Public reads ---------------------------------------------------------- #
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
    search: str | None = None,
    sort: str = "newest",
    limit: int = 60,
    offset: int = 0,
) -> tuple[list[Property], int]:
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
    else:  # newest
        stmt = stmt.order_by(Property.created_at.desc())
    stmt = stmt.limit(min(limit, 200)).offset(max(offset, 0))

    rows = list((await session.execute(stmt)).scalars().all())
    return rows, int(total)


async def get_public_detail(session: AsyncSession, id_or_slug: str) -> Property:
    prop = await _resolve(session, id_or_slug)
    if prop is None or prop.status not in PUBLIC_STATUSES:
        raise AppError("NOT_FOUND", "Property not found", status_code=404)
    return prop


async def _resolve(session: AsyncSession, id_or_slug: str) -> Property | None:
    try:
        pid = uuid.UUID(id_or_slug)
    except ValueError:
        res = await session.execute(select(Property).where(Property.slug == id_or_slug))
        return res.scalar_one_or_none()
    return await session.get(Property, pid)


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
        prop.model = _validate_model(data["model"])
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
    prop.status = PropertyStatus.under_review
    await write_audit(
        session,
        action="property.submit",
        entity_type="property",
        entity_id=str(prop.id),
        actor_id=owner_id,
        after={"status": str(prop.status)},
    )
    return prop


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
    before = {"status": str(prop.status)}
    if action == "approve":
        prop.status = PropertyStatus.active
    elif action == "reject":
        prop.status = PropertyStatus.draft
    elif action == "close":
        prop.status = PropertyStatus.closed
    else:  # pragma: no cover - guarded by the route
        raise AppError("INVALID_ACTION", f"Unknown action {action!r}", status_code=400)
    await write_audit(
        session,
        action=f"property.{action}",
        entity_type="property",
        entity_id=str(prop.id),
        actor_id=actor_id,
        before=before,
        after={"status": str(prop.status), "reason": reason},
    )
    return prop
