"""Structured listing content (go-live audit, Step 2).

The public property page reads rich, optional fields from ``properties.content`` (a JSONB
blob). Until now the only way to fill it was a raw JSON textarea. This module gives the
admin Listing Editor typed, validated setters for each section and keeps every other key
of the blob untouched. Every save writes an audit row.

Sections and the JSON they own:
  details   -> content.details.{bedrooms, bathrooms, area, parking, maxInvestment, amenities[]}
  developer -> content.developer.{name, logo, rating, projectsCompleted}
  spv       -> content.spv.{jurisdiction, trustee, auditor}
  terms     -> content.terms.{distributionFrequency, investmentTerm, exitOptions}
               + content.fees.{performance, exit}
"""

from __future__ import annotations

import copy
import datetime as dt
import decimal
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import (
    Document,
    InstallmentPlan,
    Investment,
    OwnershipLedger,
    Property,
    PropertyMilestone,
)
from app.models.base import InvestmentStatus, MilestoneStatus, PropertyStatus
from app.schemas.milestone import MILESTONE_STATUSES
from app.schemas.property import OWNERSHIP_MODELS
from app.services import property_service

MAX_AMENITIES = 40

# --------------------------------------------------------------------------- #
# Human labels (the admin is used by a non-technical owner)
# --------------------------------------------------------------------------- #
MODEL_LABELS: dict[str, str] = {
    "ready-income": "Ready property — rental income",
    "installment": "Ready property — paid in installments",
    "future": "Under construction — future property",
    "option": "Option position — right to buy at a fixed price",
    "shared-development": "Shared development — co-fund a build",
    "ready-portfolio": "Portfolio — several ready income properties",
    "construction-portfolio": "Portfolio — several off-plan projects",
}
assert set(MODEL_LABELS) == set(OWNERSHIP_MODELS)

PROPERTY_TYPES: tuple[tuple[str, str], ...] = (
    ("apartment", "Apartment"),
    ("villa", "Villa"),
    ("residential", "Residential (other)"),
    ("commercial", "Commercial"),
    ("office", "Office"),
    ("retail", "Retail"),
    ("mixed-use", "Mixed-use"),
    ("industrial", "Industrial / warehouse"),
    ("hotel", "Hotel / hospitality"),
    ("land", "Land"),
)
PROPERTY_TYPE_VALUES = tuple(v for v, _ in PROPERTY_TYPES)

MILESTONE_STATUS_LABELS: dict[str, str] = {
    "planned": "Planned",
    "in_progress": "In progress",
    "completed": "Completed",
}
assert set(MILESTONE_STATUS_LABELS) == set(MILESTONE_STATUSES)


@dataclass(frozen=True)
class FieldSpec:
    """One editable listing column: label, help and example shown in the admin."""

    name: str
    label: str
    help: str
    example: str = ""
    kind: str = "text"  # text | textarea | select | money | percent | int | date
    required: bool = False
    group: str = ""
    options: tuple[tuple[str, str], ...] = ()
    max_len: int = 200

    @property
    def description(self) -> str:
        """Help + example as one sentence (used by the raw SQLAdmin form as well)."""
        return f"{self.help} Example: {self.example}" if self.example else self.help


GROUP_IDENTITY = "Listing identity"
GROUP_LOCATION = "Location"
GROUP_OFFERING = "Offering — units & price"
GROUP_RETURNS = "Returns shown to investors"
GROUP_SPV = "SPV & legal structure"
GROUP_CONSTRUCTION = "Construction & timeline"

CORE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "title",
        "Listing title",
        "The headline investors see everywhere (cards, page, emails).",
        "Marina Bay Residences — 2BR Sea View",
        required=True,
        group=GROUP_IDENTITY,
    ),
    FieldSpec(
        "subtitle",
        "Short tagline",
        "One line under the title. Leave blank to show nothing.",
        "Fully let two-bedroom apartment with uninterrupted sea views",
        group=GROUP_IDENTITY,
    ),
    FieldSpec(
        "model",
        "Ownership model",
        "Decides the page layout, calculator and badges. Cannot change once investors hold units.",
        "",
        kind="select",
        required=True,
        group=GROUP_IDENTITY,
        options=tuple((m, MODEL_LABELS[m]) for m in OWNERSHIP_MODELS),
    ),
    FieldSpec(
        "property_type",
        "Property type",
        "Used for filters on the marketplace.",
        "",
        kind="select",
        required=True,
        group=GROUP_IDENTITY,
        options=PROPERTY_TYPES,
    ),
    FieldSpec(
        "description",
        "Description",
        "Shown in the Overview tab. Describe the asset, the tenant/lease situation and why it "
        "is a good investment. Plain text; blank lines make paragraphs.",
        "A 1,350 sq ft two-bedroom apartment on the 18th floor, let to a corporate tenant "
        "until 2028…",
        kind="textarea",
        group=GROUP_IDENTITY,
        max_len=8000,
    ),
    FieldSpec(
        "location",
        "Location (as shown)",
        "The location line under the title.",
        "Dubai Marina, Dubai",
        required=True,
        group=GROUP_LOCATION,
    ),
    FieldSpec(
        "city",
        "City",
        "Used for the city filter on the marketplace.",
        "Dubai",
        group=GROUP_LOCATION,
    ),
    FieldSpec(
        "country",
        "Country",
        "Used for the country filter on the marketplace.",
        "United Arab Emirates",
        group=GROUP_LOCATION,
    ),
    FieldSpec(
        "total_value",
        "Total property value (USD)",
        "The full value of the asset. Funding goal = this amount. Digits only, no commas.",
        "1200000",
        kind="money",
        required=True,
        group=GROUP_OFFERING,
    ),
    FieldSpec(
        "unit_price",
        "Price per unit (USD)",
        "What one unit costs. Locked once investors hold units.",
        "100",
        kind="money",
        required=True,
        group=GROUP_OFFERING,
    ),
    FieldSpec(
        "total_units",
        "Total units",
        "Number of units on offer — normally total value ÷ unit price. Locked once investors "
        "hold units.",
        "12000",
        kind="int",
        required=True,
        group=GROUP_OFFERING,
    ),
    FieldSpec(
        "minimum_investment",
        "Minimum investment (USD)",
        "Smallest amount an investor may put in.",
        "500",
        kind="money",
        required=True,
        group=GROUP_OFFERING,
    ),
    FieldSpec(
        "target_yield",
        "Target rental yield (% per year)",
        "Shown on the marketplace card. Leave blank if not applicable.",
        "7.5",
        kind="percent",
        group=GROUP_RETURNS,
    ),
    FieldSpec(
        "expected_yield",
        "Expected annual yield (%)",
        "Drives the “Expected return” and the calculator on the property page.",
        "7.5",
        kind="percent",
        group=GROUP_RETURNS,
    ),
    FieldSpec(
        "capital_appreciation",
        "Expected capital appreciation (% per year)",
        "Shown in the Financials tab.",
        "3",
        kind="percent",
        group=GROUP_RETURNS,
    ),
    FieldSpec(
        "total_return",
        "Total expected return (%)",
        "Yield + appreciation, as one headline number.",
        "10.5",
        kind="percent",
        group=GROUP_RETURNS,
    ),
    FieldSpec(
        "spv_name",
        "SPV name",
        "The legal entity that holds the title deed.",
        "Marina Bay Residences SPV Ltd",
        group=GROUP_SPV,
    ),
    FieldSpec(
        "spv_registration",
        "SPV registration number",
        "As on the certificate of incorporation.",
        "DIFC-12345",
        group=GROUP_SPV,
    ),
    FieldSpec(
        "legal_structure",
        "Legal structure",
        "One line investors can understand.",
        "Special purpose vehicle (SPV) — investors hold units in the SPV that owns the property",
        group=GROUP_SPV,
        max_len=300,
    ),
    FieldSpec(
        "expected_completion",
        "Expected completion date",
        "Under-construction listings only; shown in the Timeline tab.",
        "2027-06-30",
        kind="date",
        group=GROUP_CONSTRUCTION,
    ),
)
CORE_BY_NAME = {f.name: f for f in CORE_FIELDS}
# Groups rendered by the editor's main "Listing details" form (SPV/construction have own cards)
CORE_FORM_GROUPS = (GROUP_IDENTITY, GROUP_LOCATION, GROUP_OFFERING, GROUP_RETURNS)
# Fields an investor's purchase is defined by — frozen once anyone holds units.
LOCKED_WITH_POSITIONS = ("unit_price", "total_units", "model")


def fields_in(*groups: str) -> list[FieldSpec]:
    return [f for f in CORE_FIELDS if f.group in groups]


def _bad_field(spec: FieldSpec, what: str) -> AppError:
    eg = f" Example: {spec.example}." if spec.example else ""
    return AppError("INVALID_INPUT", f"{spec.label}: {what}.{eg}", status_code=422)


def parse_core_value(spec: FieldSpec, raw: Any) -> Any:
    """Coerce one submitted value to its column type with a human-readable error."""
    s = " ".join(str(raw or "").split()) if spec.kind != "textarea" else str(raw or "").strip()
    if not s:
        if spec.required:
            raise _bad_field(spec, "this field is required")
        return None
    if spec.kind in ("text", "textarea"):
        if len(s) > spec.max_len:
            raise _bad_field(spec, f"must be at most {spec.max_len} characters")
        return s
    if spec.kind == "select":
        allowed = {v for v, _ in spec.options}
        if s not in allowed:
            raise _bad_field(spec, "choose one of the options in the list")
        return s
    if spec.kind == "date":
        try:
            return dt.date.fromisoformat(s)
        except ValueError as exc:
            raise _bad_field(spec, "enter a date as YYYY-MM-DD") from exc
    s = s.replace(",", "").replace("$", "").replace("%", "")
    try:
        num = decimal.Decimal(s)
    except decimal.InvalidOperation as exc:
        raise _bad_field(spec, "enter a number using digits only") from exc
    if num < 0:
        raise _bad_field(spec, "cannot be negative")
    if spec.kind == "int":
        if num != num.to_integral_value():
            raise _bad_field(spec, "must be a whole number")
        if spec.required and num == 0:
            raise _bad_field(spec, "must be at least 1")
        return int(num)
    if spec.kind == "percent" and num > 100:
        raise _bad_field(spec, "must be between 0 and 100")
    if spec.kind == "money" and spec.required and num == 0:
        raise _bad_field(spec, "must be greater than zero")
    return num.quantize(decimal.Decimal("0.01"))


def parse_core(form: Any, names: list[str]) -> dict[str, Any]:
    """Parse the submitted core fields (only ``names``); errors name the field label."""
    out: dict[str, Any] = {}
    for name in names:
        spec = CORE_BY_NAME[name]
        out[name] = parse_core_value(spec, form.get(name))
    return out


async def count_positions(session: AsyncSession, prop_id: uuid.UUID) -> int:
    """Open investor positions on a property: live investments + ledger rows + plans."""
    inv = await session.scalar(
        select(func.count())
        .select_from(Investment)
        .where(
            Investment.property_id == prop_id,
            Investment.status.in_(
                (
                    InvestmentStatus.pending,
                    InvestmentStatus.confirmed,
                    InvestmentStatus.active,
                    InvestmentStatus.completed,
                )
            ),
        )
    )
    led = await session.scalar(
        select(func.count())
        .select_from(OwnershipLedger)
        .where(OwnershipLedger.property_id == prop_id)
    )
    plans = await session.scalar(
        select(func.count())
        .select_from(InstallmentPlan)
        .where(InstallmentPlan.property_id == prop_id)
    )
    return int(inv or 0) + int(led or 0) + int(plans or 0)


def _same(a: object, b: object) -> bool:
    if a is None or b is None:
        return a is b
    try:
        return decimal.Decimal(str(a)) == decimal.Decimal(str(b))
    except (decimal.InvalidOperation, ValueError):
        return str(a) == str(b)


def locked_message(positions: int) -> str:
    return (
        f"Units, unit price and ownership model are locked: {positions} investor position(s) "
        "exist on this listing. Investors bought a defined offering, so it cannot change. "
        "Close the listing and create a new one instead."
    )


def _snapshot(prop: Property, keys: list[str]) -> dict[str, str | None]:
    return {
        k: (None if getattr(prop, k, None) is None else str(getattr(prop, k)))
        for k in keys
        if hasattr(prop, k)
    }


async def create_listing(
    session: AsyncSession, *, data: dict[str, Any], actor_id: uuid.UUID | None
) -> Property:
    """Create a DRAFT listing from parsed core fields (admin path, no owner)."""
    title = data["title"]
    slug = property_service.slugify(title)
    prop = Property(
        title=title,
        slug=slug,
        status=PropertyStatus.draft,
        available_units=int(data["total_units"]),
        content={},
        fees={},
        images=[],
        **{k: v for k, v in data.items() if k != "title"},
    )
    session.add(prop)
    await session.flush()
    await write_audit(
        session,
        action="property.admin_create",
        entity_type="property",
        entity_id=str(prop.id),
        actor_id=actor_id,
        after={k: (None if v is None else str(v)) for k, v in data.items()},
    )
    return prop


async def update_core(
    session: AsyncSession,
    *,
    prop: Property,
    data: dict[str, Any],
    actor_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Apply parsed core fields to an existing listing under the offering-lock rule.

    Returns the dict of changed keys (after values). ``available_units`` follows
    ``total_units`` while nothing is sold — the same invariant the owner API keeps."""
    before = _snapshot(prop, list(data))
    changed = {k: v for k, v in data.items() if not _same(v, getattr(prop, k, None))}
    if not changed:
        return {}
    if any(k in changed for k in LOCKED_WITH_POSITIONS):
        positions = await count_positions(session, prop.id)
        if positions:
            raise AppError("OFFERING_LOCKED", locked_message(positions), status_code=409)
    for k, v in changed.items():
        setattr(prop, k, v)
    if "total_units" in changed:
        prop.available_units = int(changed["total_units"])
    await session.flush()
    await write_audit(
        session,
        action="property.admin_edit",
        entity_type="property",
        entity_id=str(prop.id),
        actor_id=actor_id,
        before={k: before.get(k) for k in changed},
        after={k: (None if v is None else str(v)) for k, v in changed.items()},
    )
    return changed


# --------------------------------------------------------------------------- #
# Milestones (admin path — no owner scoping, audited, flush not commit)
# --------------------------------------------------------------------------- #
def parse_milestone(form: Any) -> dict[str, Any]:
    title = " ".join(str(form.get("title") or "").split())
    if not title:
        raise AppError(
            "INVALID_INPUT",
            "Milestone title: this field is required. Example: Foundation complete.",
            status_code=422,
        )
    if len(title) > 120:
        raise AppError(
            "INVALID_INPUT", "Milestone title: must be at most 120 characters.", status_code=422
        )
    description = str(form.get("description") or "").strip()
    if len(description) > 500:
        raise AppError(
            "INVALID_INPUT",
            "Milestone description: must be at most 500 characters.",
            status_code=422,
        )
    status = str(form.get("status") or "planned")
    if status not in MILESTONE_STATUSES:
        raise AppError(
            "INVALID_INPUT",
            "Milestone status: choose Planned, In progress or Completed.",
            status_code=422,
        )
    progress = _opt_int(form.get("progress_pct"), "Progress %", hi=100)
    target = parse_core_value(
        FieldSpec("target_date", "Target date", "", "2027-03-31", kind="date"),
        form.get("target_date"),
    )
    return {
        "title": title,
        "description": description or None,
        "status": status,
        "progress_pct": progress,
        "target_date": target,
    }


async def list_milestones(session: AsyncSession, prop_id: uuid.UUID) -> list[PropertyMilestone]:
    res = await session.execute(
        select(PropertyMilestone)
        .where(PropertyMilestone.property_id == prop_id)
        .order_by(PropertyMilestone.sort_index, PropertyMilestone.created_at)
    )
    return list(res.scalars().all())


def construction_progress(rows: list[PropertyMilestone]) -> int:
    """Same rule the public API uses (milestone_service): the in-progress milestone's %."""
    in_prog = [
        r for r in rows if r.status == MilestoneStatus.in_progress and r.progress_pct is not None
    ]
    if not in_prog:
        return 0
    return int(max(in_prog, key=lambda r: r.sort_index).progress_pct or 0)


async def _milestone_audit(session, prop, action, actor_id, before=None, after=None) -> None:
    await write_audit(
        session,
        action=f"property.milestone.{action}",
        entity_type="property",
        entity_id=str(prop.id),
        actor_id=actor_id,
        before=before,
        after=after,
    )


def _ms_dict(m: PropertyMilestone) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "title": m.title,
        "status": str(m.status),
        "progress_pct": m.progress_pct,
        "target_date": m.target_date.isoformat() if m.target_date else None,
        "sort_index": m.sort_index,
    }


async def _get_milestone(session, prop: Property, milestone_id: str) -> PropertyMilestone:
    try:
        mid = uuid.UUID(str(milestone_id))
    except ValueError as exc:
        raise AppError("NOT_FOUND", "Milestone not found.", status_code=404) from exc
    m = await session.get(PropertyMilestone, mid)
    if m is None or m.property_id != prop.id:
        raise AppError("NOT_FOUND", "Milestone not found.", status_code=404)
    return m


async def add_milestone(
    session: AsyncSession, *, prop: Property, data: dict[str, Any], actor_id: uuid.UUID | None
) -> PropertyMilestone:
    rows = await list_milestones(session, prop.id)
    m = PropertyMilestone(
        property_id=prop.id,
        title=data["title"],
        description=data.get("description"),
        status=MilestoneStatus(data["status"]),
        progress_pct=data.get("progress_pct"),
        target_date=data.get("target_date"),
        sort_index=(max((r.sort_index for r in rows), default=-1) + 1),
        created_by=actor_id,
    )
    if data["status"] == "completed":
        m.completed_at = dt.datetime.now(dt.UTC)
    session.add(m)
    await session.flush()
    await _milestone_audit(session, prop, "add", actor_id, after=_ms_dict(m))
    return m


async def update_milestone(
    session: AsyncSession,
    *,
    prop: Property,
    milestone_id: str,
    data: dict[str, Any],
    actor_id: uuid.UUID | None,
) -> PropertyMilestone:
    m = await _get_milestone(session, prop, milestone_id)
    before = _ms_dict(m)
    m.title = data["title"]
    m.description = data.get("description")
    m.progress_pct = data.get("progress_pct")
    m.target_date = data.get("target_date")
    new_status = data["status"]
    was_completed = m.status == MilestoneStatus.completed
    m.status = MilestoneStatus(new_status)
    if new_status == "completed" and not was_completed:
        m.completed_at = dt.datetime.now(dt.UTC)
    elif new_status != "completed":
        m.completed_at = None
    m.updated_at = dt.datetime.now(dt.UTC)
    await session.flush()
    await _milestone_audit(session, prop, "update", actor_id, before=before, after=_ms_dict(m))
    return m


async def delete_milestone(
    session: AsyncSession, *, prop: Property, milestone_id: str, actor_id: uuid.UUID | None
) -> None:
    m = await _get_milestone(session, prop, milestone_id)
    before = _ms_dict(m)
    await session.delete(m)
    await session.flush()
    await _milestone_audit(session, prop, "delete", actor_id, before=before)


async def move_milestone(
    session: AsyncSession,
    *,
    prop: Property,
    milestone_id: str,
    delta: int,
    actor_id: uuid.UUID | None,
) -> list[PropertyMilestone]:
    rows = await list_milestones(session, prop.id)
    m = await _get_milestone(session, prop, milestone_id)
    ids = [r.id for r in rows]
    i = ids.index(m.id)
    j = max(0, min(len(ids) - 1, i + delta))
    rows.insert(j, rows.pop(i))
    for idx, r in enumerate(rows):
        r.sort_index = idx
    await session.flush()
    await _milestone_audit(
        session, prop, "reorder", actor_id, after={"order": [str(r.id) for r in rows]}
    )
    return rows


# --------------------------------------------------------------------------- #
# Delete a listing (row cascades to documents/milestones; files cleaned by the caller)
# --------------------------------------------------------------------------- #
def _url_key(url: str | None) -> str | None:
    from app.services import listing_media_service

    return listing_media_service.url_to_key(url) if isinstance(url, str) else None


async def collect_file_keys(session: AsyncSession, prop: Property) -> list[str]:
    """Every storage key the listing owns: gallery, developer logo, document files."""
    keys = [k for k in (_url_key(u) for u in (prop.images or [])) if k]
    logo_key = _url_key(((prop.content or {}).get("developer") or {}).get("logo"))
    if logo_key:
        keys.append(logo_key)
    doc_keys = await session.scalars(
        select(Document.file_url).where(Document.property_id == prop.id)
    )
    keys.extend(k for k in doc_keys if k)
    return keys


async def delete_listing(
    session: AsyncSession, *, prop: Property, actor_id: uuid.UUID | None
) -> list[str]:
    """Delete the listing row (refused while investors hold units). Returns the storage
    keys to remove AFTER the transaction commits (a failed delete must not lose files)."""
    positions = await count_positions(session, prop.id)
    if positions:
        raise AppError(
            "LISTING_HAS_POSITIONS",
            f"This listing cannot be deleted: {positions} investor position(s) exist. "
            "Unpublish (close) it instead.",
            status_code=409,
        )
    keys = await collect_file_keys(session, prop)
    before = {
        "title": prop.title,
        "slug": prop.slug,
        "status": str(prop.status),
        "files": len(keys),
    }
    await write_audit(
        session,
        action="property.admin_delete",
        entity_type="property",
        entity_id=str(prop.id),
        actor_id=actor_id,
        before=before,
    )
    await session.delete(prop)
    await session.flush()
    return keys


def _bad(field: str, msg: str) -> AppError:
    return AppError("INVALID_INPUT", f"{field}: {msg}", status_code=422)


def _opt_int(raw: Any, field: str, *, lo: int = 0, hi: int = 1_000_000) -> int | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        v = int(float(s))
    except ValueError as exc:
        raise _bad(field, "must be a whole number") from exc
    if not lo <= v <= hi:
        raise _bad(field, f"must be between {lo} and {hi}")
    return v


def _opt_num(raw: Any, field: str, *, lo: float = 0, hi: float = 1e12) -> float | None:
    s = str(raw or "").strip().replace(",", "")
    if not s:
        return None
    try:
        v = float(s)
    except ValueError as exc:
        raise _bad(field, "must be a number") from exc
    if not lo <= v <= hi:
        raise _bad(field, f"must be between {lo:g} and {hi:g}")
    return v


def _opt_str(raw: Any, field: str, *, max_len: int = 200) -> str:
    s = " ".join(str(raw or "").split())
    if len(s) > max_len:
        raise _bad(field, f"must be at most {max_len} characters")
    return s


def parse_amenities(raw: Any) -> list[str]:
    """One amenity per line (or comma-separated); trimmed, de-duplicated, capped."""
    text = str(raw or "").replace(",", "\n")
    out: list[str] = []
    for line in text.splitlines():
        item = " ".join(line.split())
        if not item or item in out:
            continue
        if len(item) > 60:
            raise _bad("amenities", "each amenity must be at most 60 characters")
        out.append(item)
    if len(out) > MAX_AMENITIES:
        raise _bad("amenities", f"at most {MAX_AMENITIES} amenities")
    return out


def _section(content: dict, key: str) -> dict:
    sec = content.get(key)
    return dict(sec) if isinstance(sec, dict) else {}


def _put(sec: dict, key: str, value: Any) -> None:
    """Store a value, dropping the key entirely when it is empty (no nulls in the blob)."""
    if value is None or value == "" or value == []:
        sec.pop(key, None)
    else:
        sec[key] = value


def with_details(content: dict, form: dict) -> dict:
    c = copy.deepcopy(content or {})
    d = _section(c, "details")
    _put(d, "bedrooms", _opt_int(form.get("bedrooms"), "bedrooms", hi=50))
    _put(d, "bathrooms", _opt_int(form.get("bathrooms"), "bathrooms", hi=50))
    _put(d, "area", _opt_num(form.get("area"), "area"))
    _put(d, "parking", _opt_int(form.get("parking"), "parking", hi=100))
    _put(d, "maxInvestment", _opt_num(form.get("max_investment"), "max_investment"))
    _put(d, "amenities", parse_amenities(form.get("amenities")))
    _put(c, "details", d)
    return c


def with_developer(content: dict, form: dict, *, logo_url: str | None = None) -> dict:
    c = copy.deepcopy(content or {})
    d = _section(c, "developer")
    _put(d, "name", _opt_str(form.get("name"), "name", max_len=120))
    _put(d, "rating", _opt_num(form.get("rating"), "rating", lo=0, hi=5))
    _put(d, "projectsCompleted", _opt_int(form.get("projects_completed"), "projects_completed"))
    if logo_url is not None:
        _put(d, "logo", logo_url)
    elif str(form.get("clear_logo") or "") == "1":
        d.pop("logo", None)
    _put(c, "developer", d)
    return c


def with_spv(content: dict, form: dict) -> dict:
    c = copy.deepcopy(content or {})
    d = _section(c, "spv")
    for key in ("jurisdiction", "trustee", "auditor"):
        _put(d, key, _opt_str(form.get(key), key))
    _put(c, "spv", d)
    return c


def with_terms(content: dict, form: dict) -> dict:
    c = copy.deepcopy(content or {})
    t = _section(c, "terms")
    for key, field in (
        ("distributionFrequency", "distribution_frequency"),
        ("investmentTerm", "investment_term"),
        ("exitOptions", "exit_options"),
    ):
        _put(t, key, _opt_str(form.get(field), field, max_len=160))
    _put(c, "terms", t)
    f = _section(c, "fees")
    _put(f, "performance", _opt_num(form.get("performance_fee"), "performance_fee", lo=0, hi=100))
    _put(f, "exit", _opt_num(form.get("exit_fee"), "exit_fee", lo=0, hi=100))
    _put(c, "fees", f)
    return c


async def apply_content(
    session: AsyncSession,
    *,
    prop: Property,
    new_content: dict,
    section: str,
    actor_id: uuid.UUID | None,
) -> Property:
    before = (prop.content or {}).get(section)
    prop.content = new_content
    await session.flush()
    await write_audit(
        session,
        action="property.content.update",
        entity_type="property",
        entity_id=str(prop.id),
        actor_id=actor_id,
        before={section: before},
        after={section: new_content.get(section)},
    )
    return prop
