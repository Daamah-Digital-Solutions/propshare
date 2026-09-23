"""Structured listing content (go-live audit, Step 2).

The public property page reads rich, optional fields from ``properties.content`` (a JSONB
blob). Until now the only way to fill it was a raw JSON textarea. This module gives the
admin Listing Editor typed, validated setters for each section and keeps every other key
of the blob untouched. Every save writes an audit row.

Sections and the JSON they own:
  details   -> content.details.{bedrooms, bathrooms, area, parking, maxInvestment, amenities[]}
  developer -> content.developer.{name, logo, rating, projectsCompleted, about, website}
  spv       -> content.spv.{jurisdiction, trustee, auditor}
  terms     -> content.terms.{distributionFrequency, investmentTerm, exitOptions}
               + content.fees.{performance, exit}
"""

from __future__ import annotations

import copy
import datetime as dt
import decimal
import re
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

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
# Ownership models, profiles and human labels (the admin is used by a non-technical owner)
# --------------------------------------------------------------------------- #
MODEL_LABELS: dict[str, str] = {
    "ready-income": "Ready property, rental income",
    "ready-portfolio": "Ready portfolio, several income properties",
    "installment": "Off-plan, paid in installments",
    "construction-portfolio": "Off-plan portfolio, several projects",
    "future": "Future property (not available)",
    "option": "Option position (not available)",
    "shared-development": "Shared development (not available)",
}
assert set(MODEL_LABELS) == set(OWNERSHIP_MODELS)

# Models investors can actually get today. The other keys stay in code so they can be
# enabled once their mechanics exist; until then nobody can create or switch to them.
ENABLED_MODELS: tuple[str, ...] = (
    "ready-income",
    "ready-portfolio",
    "installment",
    "construction-portfolio",
)
HIDDEN_MODELS: tuple[str, ...] = tuple(m for m in OWNERSHIP_MODELS if m not in ENABLED_MODELS)
HIDDEN_MODEL_REASONS: dict[str, str] = {
    "future": "forward purchase and settlement at delivery are not built",
    "option": "option premiums, strike prices and expiry are not built",
    "shared-development": "developer partnerships and profit sharing are not built",
}
assert set(HIDDEN_MODEL_REASONS) == set(HIDDEN_MODELS)

PROFILE_READY = "ready_single"
PROFILE_READY_PORTFOLIO = "ready_portfolio"
PROFILE_OFFPLAN = "offplan_single"
PROFILE_OFFPLAN_PORTFOLIO = "offplan_portfolio"
ALL_PROFILES = (PROFILE_READY, PROFILE_READY_PORTFOLIO, PROFILE_OFFPLAN, PROFILE_OFFPLAN_PORTFOLIO)
READY_PROFILES = (PROFILE_READY, PROFILE_READY_PORTFOLIO)
OFFPLAN_PROFILES = (PROFILE_OFFPLAN, PROFILE_OFFPLAN_PORTFOLIO)
SINGLE_PROFILES = (PROFILE_READY, PROFILE_OFFPLAN)
PORTFOLIO_PROFILES = (PROFILE_READY_PORTFOLIO, PROFILE_OFFPLAN_PORTFOLIO)

# Mirrors the public site: only ready-income / ready-portfolio get the "Ready" page; every
# other key renders the under-construction page with the installment calculator.
MODEL_PROFILE: dict[str, str] = {
    "ready-income": PROFILE_READY,
    "ready-portfolio": PROFILE_READY_PORTFOLIO,
    "installment": PROFILE_OFFPLAN,
    "future": PROFILE_OFFPLAN,
    "option": PROFILE_OFFPLAN,
    "shared-development": PROFILE_OFFPLAN,
    "construction-portfolio": PROFILE_OFFPLAN_PORTFOLIO,
}
assert set(MODEL_PROFILE) == set(OWNERSHIP_MODELS)

MODEL_EXPLAIN: dict[str, str] = {
    "ready-income": (
        "A completed property. Investors buy whole units outright and receive their share "
        "of the rental income."
    ),
    "ready-portfolio": (
        "Several completed income properties offered together. Investors buy whole units "
        "in the whole portfolio and share its rental income."
    ),
    "installment": (
        "A property under construction. Investors lock today's unit price and pay through "
        "the platform's standard installment plan; rental income starts after handover."
    ),
    "construction-portfolio": (
        "Several projects under construction offered together, bought through the "
        "platform's standard installment plan; rental income starts after handover."
    ),
    "future": "Not available: " + HIDDEN_MODEL_REASONS["future"] + ".",
    "option": "Not available: " + HIDDEN_MODEL_REASONS["option"] + ".",
    "shared-development": "Not available: " + HIDDEN_MODEL_REASONS["shared-development"] + ".",
}


def profile_of(model: str | None) -> str:
    return MODEL_PROFILE.get(model or "", PROFILE_READY)


def validate_model_choice(model: str, *, current: str | None = None) -> str:
    """A listing may keep a legacy hidden model it already has, but nobody can create a
    listing with one or switch a listing to one."""
    if model not in OWNERSHIP_MODELS:
        raise AppError(
            "INVALID_MODEL",
            "Ownership model: choose one of the options in the list.",
            status_code=422,
        )
    if model in HIDDEN_MODELS and model != current:
        raise AppError(
            "MODEL_NOT_AVAILABLE",
            f"The '{model}' ownership model is not available: {HIDDEN_MODEL_REASONS[model]}. "
            "Choose ready property, ready portfolio, off-plan paid in installments or "
            "off-plan portfolio.",
            status_code=422,
        )
    return model


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
    """One editable listing column: label, help and example shown in the admin.

    ``show_in`` / ``required_in`` / ``profile_labels`` make the same field adapt to the
    ownership model's profile; ``computed`` fields are calculated by the server and shown
    read-only; ``positive`` rejects 0 because the public page would show "0%"."""

    name: str
    label: str
    help: str
    example: str = ""
    kind: str = "text"  # text | textarea | select | money | percent | int | date
    required: bool = False
    group: str = ""
    options: tuple[tuple[str, str], ...] = ()
    max_len: int = 200
    show_in: tuple[str, ...] = ALL_PROFILES
    required_in: tuple[str, ...] = ()
    profile_labels: tuple[tuple[str, str], ...] = ()
    profile_help: tuple[tuple[str, str], ...] = ()
    computed: bool = False
    positive: bool = False

    @property
    def description(self) -> str:
        """Help + example as one sentence (used by the raw SQLAdmin form as well)."""
        return f"{self.help} Example: {self.example}" if self.example else self.help

    def shown(self, profile: str) -> bool:
        return profile in self.show_in

    def is_required(self, profile: str) -> bool:
        return self.required or profile in self.required_in

    def label_for(self, profile: str) -> str:
        return dict(self.profile_labels).get(profile, self.label)

    def help_for(self, profile: str) -> str:
        return dict(self.profile_help).get(profile, self.help)

    def rules(self) -> dict[str, dict[str, Any]]:
        """Per-profile rules, embedded as JSON so the form adapts live when the model changes."""
        return {
            p: {
                "show": self.shown(p),
                "required": self.is_required(p) and not self.computed,
                "label": self.label_for(p),
                "help": self.help_for(p),
            }
            for p in ALL_PROFILES
        }


GROUP_IDENTITY = "Listing identity"
GROUP_LOCATION = "Location"
GROUP_OFFERING = "Offering, units and price"
GROUP_RETURNS = "Returns shown to investors"
GROUP_SPV = "SPV and legal structure"
GROUP_CONSTRUCTION = "Construction and timeline"

_OFFPLAN_YIELD_LABEL = "Expected rental yield after handover (% per year)"

CORE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "title",
        "Listing title",
        "The headline investors see everywhere (cards, page, emails).",
        "Marina Bay Residences 2BR Sea View",
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
        "Decides the page layout and how investors buy. Cannot change once investors hold units.",
        "",
        kind="select",
        required=True,
        group=GROUP_IDENTITY,
        options=tuple((m, MODEL_LABELS[m]) for m in ENABLED_MODELS),
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
        "Shown in the Overview tab. Describe the asset, the tenant or lease situation and why "
        "it is a good investment. Plain text; blank lines make paragraphs.",
        "A 1,350 sq ft two-bedroom apartment on the 18th floor, let to a corporate tenant "
        "until 2028.",
        kind="textarea",
        group=GROUP_IDENTITY,
        max_len=8000,
        profile_help=(
            (
                PROFILE_READY_PORTFOLIO,
                "Shown in the Overview tab. List the properties in the portfolio, their "
                "locations and tenancy. Plain text; blank lines make paragraphs.",
            ),
            (
                PROFILE_OFFPLAN_PORTFOLIO,
                "Shown in the Overview tab. List the projects in the portfolio, their "
                "developers and expected handover dates. Plain text; blank lines make "
                "paragraphs.",
            ),
        ),
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
        "The full value of the offering. The funding goal equals this amount. Digits only, "
        "no commas.",
        "1200000",
        kind="money",
        required=True,
        group=GROUP_OFFERING,
    ),
    FieldSpec(
        "unit_price",
        "Price per unit (USD)",
        "What one unit costs. Investors buy whole units only. Locked once investors hold units.",
        "100",
        kind="money",
        required=True,
        group=GROUP_OFFERING,
    ),
    FieldSpec(
        "total_units",
        "Total units (calculated)",
        "Calculated automatically: total property value divided by price per unit.",
        "12000",
        kind="int",
        group=GROUP_OFFERING,
        computed=True,
    ),
    FieldSpec(
        "minimum_investment",
        "Minimum investment (USD)",
        "Smallest amount an investor may put in. Must be a whole number of units: at least "
        "one unit price and a multiple of it.",
        "500",
        kind="money",
        required=True,
        group=GROUP_OFFERING,
    ),
    FieldSpec(
        "expected_yield",
        "Expected annual rental yield (%)",
        "Shown on the marketplace card, in the Financials tab and in the calculator. Must be "
        "greater than 0, otherwise the page would show 0%.",
        "7.5",
        kind="percent",
        required=True,
        positive=True,
        group=GROUP_RETURNS,
        profile_labels=(
            (PROFILE_OFFPLAN, _OFFPLAN_YIELD_LABEL),
            (PROFILE_OFFPLAN_PORTFOLIO, _OFFPLAN_YIELD_LABEL),
        ),
        profile_help=(
            (
                PROFILE_OFFPLAN,
                "The rental yield expected once the property is handed over. The property "
                "page labels it Expected Rental Yield, so it must be greater than 0.",
            ),
            (
                PROFILE_OFFPLAN_PORTFOLIO,
                "The rental yield expected once the projects are handed over. The property "
                "page labels it Expected Rental Yield, so it must be greater than 0.",
            ),
        ),
    ),
    FieldSpec(
        "target_yield",
        "Target yield (%)",
        "Kept equal to the expected rental yield automatically.",
        "",
        kind="percent",
        group=GROUP_RETURNS,
        show_in=(),
        computed=True,
    ),
    FieldSpec(
        "capital_appreciation",
        "Expected capital appreciation (% per year)",
        "Shown in the Financials tab. Must be greater than 0, otherwise the page would show 0%.",
        "3",
        kind="percent",
        required=True,
        positive=True,
        group=GROUP_RETURNS,
    ),
    FieldSpec(
        "total_return",
        "Total expected return (%)",
        "Leave blank to calculate it as rental yield plus capital appreciation. If you enter "
        "a different figure you will see a warning.",
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
        "Special purpose vehicle: investors hold units in the SPV that owns the property",
        group=GROUP_SPV,
        max_len=300,
    ),
    FieldSpec(
        "expected_completion",
        "Expected completion date",
        "When the property is expected to be handed over. Shown in the investment sidebar. "
        "Required before an off-plan listing can be published.",
        "2027-06-30",
        kind="date",
        group=GROUP_CONSTRUCTION,
        show_in=OFFPLAN_PROFILES,
    ),
)
CORE_BY_NAME = {f.name: f for f in CORE_FIELDS}
# Groups rendered by the editor's main "Listing details" form (SPV/construction have own cards)
CORE_FORM_GROUPS = (GROUP_IDENTITY, GROUP_LOCATION, GROUP_OFFERING, GROUP_RETURNS)
# The New listing form also asks for the completion date (shown for off-plan models only).
CREATE_FORM_GROUPS = (*CORE_FORM_GROUPS, GROUP_CONSTRUCTION)
# Fields an investor's purchase is defined by — frozen once anyone holds units.
LOCKED_WITH_POSITIONS = ("unit_price", "total_units", "model")

# Editor-only content fields that depend on the profile (key facts card).
FACT_RULES: dict[str, dict[str, Any]] = {
    "bedrooms": {"show_in": SINGLE_PROFILES},
    "bathrooms": {"show_in": SINGLE_PROFILES},
    "parking": {"show_in": SINGLE_PROFILES},
    "amenities": {"show_in": SINGLE_PROFILES},
    "area": {"show_in": ALL_PROFILES},
    "max_investment": {"show_in": ALL_PROFILES},
}
AREA_LABELS = {
    PROFILE_READY: "Area (sq ft)",
    PROFILE_OFFPLAN: "Area (sq ft)",
    PROFILE_READY_PORTFOLIO: "Total area across all properties (sq ft)",
    PROFILE_OFFPLAN_PORTFOLIO: "Total area across all projects (sq ft)",
}


def fields_in(*groups: str) -> list[FieldSpec]:
    return [f for f in CORE_FIELDS if f.group in groups]


def form_rules_json() -> dict[str, Any]:
    """Everything the admin page script needs to adapt the form without a round trip."""
    return {
        "profiles": MODEL_PROFILE,
        "explain": MODEL_EXPLAIN,
        "fields": {f.name: f.rules() for f in CORE_FIELDS},
        "facts": {k: {p: p in v["show_in"] for p in ALL_PROFILES} for k, v in FACT_RULES.items()},
        "area_labels": AREA_LABELS,
    }


def _bad_field(spec: FieldSpec, what: str, profile: str | None = None) -> AppError:
    eg = f" Example: {spec.example}." if spec.example else ""
    label = spec.label_for(profile) if profile else spec.label
    return AppError("INVALID_INPUT", f"{label}: {what}.{eg}", status_code=422)


def parse_core_value(spec: FieldSpec, raw: Any, profile: str | None = None) -> Any:
    """Coerce one submitted value to its column type with a human-readable error."""
    s = " ".join(str(raw or "").split()) if spec.kind != "textarea" else str(raw or "").strip()
    required = spec.is_required(profile) if profile else spec.required
    if not s:
        if required:
            raise _bad_field(spec, "this field is required", profile)
        return None
    if spec.kind in ("text", "textarea"):
        if len(s) > spec.max_len:
            raise _bad_field(spec, f"must be at most {spec.max_len} characters", profile)
        return s
    if spec.kind == "select":
        allowed = {v for v, _ in spec.options}
        if s not in allowed:
            raise _bad_field(spec, "choose one of the options in the list", profile)
        return s
    if spec.kind == "date":
        try:
            return dt.date.fromisoformat(s)
        except ValueError as exc:
            raise _bad_field(spec, "enter a date as YYYY-MM-DD", profile) from exc
    s = s.replace(",", "").replace("$", "").replace("%", "")
    try:
        num = decimal.Decimal(s)
    except decimal.InvalidOperation as exc:
        raise _bad_field(spec, "enter a number using digits only", profile) from exc
    if num < 0:
        raise _bad_field(spec, "cannot be negative", profile)
    if spec.kind == "int":
        if num != num.to_integral_value():
            raise _bad_field(spec, "must be a whole number", profile)
        if required and num == 0:
            raise _bad_field(spec, "must be at least 1", profile)
        return int(num)
    if spec.kind == "percent" and num > 100:
        raise _bad_field(spec, "must be between 0 and 100", profile)
    if spec.kind == "percent" and spec.positive and num == 0:
        raise AppError(
            "INVALID_INPUT",
            f"{spec.label_for(profile) if profile else spec.label}: must be greater than 0. "
            "The property page would show 0%.",
            status_code=422,
        )
    if spec.kind == "money" and required and num == 0:
        raise _bad_field(spec, "must be greater than zero", profile)
    return num.quantize(decimal.Decimal("0.01"))


def parse_core(form: Any, names: list[str], *, model: str | None = None) -> dict[str, Any]:
    """Parse the submitted core fields for the listing's model profile.

    Fields hidden for the profile and computed fields are skipped (their stored values are
    kept, so switching model back loses nothing). Errors name the field label."""
    profile = profile_of(model)
    out: dict[str, Any] = {}
    for name in names:
        spec = CORE_BY_NAME[name]
        if spec.computed or not spec.shown(profile):
            continue
        out[name] = parse_core_value(spec, form.get(name), profile)
    return out


# --------------------------------------------------------------------------- #
# Consistency checks (units, minimum, total return) and the publish checklist
# --------------------------------------------------------------------------- #
_CENT = decimal.Decimal("0.01")
_RETURN_TOLERANCE = decimal.Decimal("0.05")


def usd(value: Any) -> str:
    d = decimal.Decimal(str(value)).quantize(_CENT)
    return f"${d:,.0f}" if d == d.to_integral_value() else f"${d:,.2f}"


def pct(value: Any) -> str:
    d = decimal.Decimal(str(value)).quantize(_CENT).normalize()
    return f"{d:f}%"


def _dec(value: Any) -> decimal.Decimal | None:
    return None if value is None else decimal.Decimal(str(value))


def units_problem(total_value: Any, unit_price: Any) -> str | None:
    tv, up = _dec(total_value), _dec(unit_price)
    if tv is None or up is None or up <= 0:
        return None
    if tv % up == 0:
        return None
    lower = (tv // up) * up
    upper = lower + up
    exact = (tv / up).quantize(decimal.Decimal("0.01"))
    return (
        f"Total units: {usd(tv)} ÷ {usd(up)} is not a whole number of units ({exact:f}). "
        f"Use {usd(lower)} or {usd(upper)} as the total property value, or change the price "
        "per unit."
    )


def minimum_problem(minimum: Any, unit_price: Any, total_value: Any = None) -> str | None:
    mn, up = _dec(minimum), _dec(unit_price)
    if mn is None or up is None or up <= 0:
        return None
    if mn < up:
        return (
            f"Minimum investment: {usd(mn)} is less than one unit ({usd(up)}). "
            f"Use {usd(up)} or a multiple of {usd(up)}."
        )
    if mn % up != 0:
        whole = int(mn // up)
        lower = up * whole
        upper = lower + up
        return (
            f"Minimum investment: {usd(mn)} buys only {whole} whole unit"
            f"{'' if whole == 1 else 's'} at {usd(up)} each. Use {usd(lower)} or {usd(upper)}."
        )
    tv = _dec(total_value)
    if tv is not None and mn > tv:
        return f"Minimum investment: {usd(mn)} is more than the total property value ({usd(tv)})."
    return None


def total_return_warning(yield_: Any, appreciation: Any, total: Any) -> str | None:
    y, a, t = _dec(yield_), _dec(appreciation), _dec(total)
    if y is None or a is None or t is None:
        return None
    if abs((y + a) - t) <= _RETURN_TOLERANCE:
        return None
    return (
        f"Total expected return is {pct(t)} but expected rental yield ({pct(y)}) plus capital "
        f"appreciation ({pct(a)}) is {pct(y + a)}. Check the figures: the property page shows "
        "all three side by side."
    )


def apply_offering_rules(
    data: dict[str, Any], *, current: Property | None = None, positions: int = 0
) -> tuple[dict[str, Any], list[str]]:
    """Derive calculated fields and enforce the offering consistency rules.

    Raises AppError (plain sentence) for inconsistent units or minimum; returns the
    completed data plus non-blocking warnings. On a listing investors already hold, the
    offering is frozen: unchanged legacy figures are left alone so content stays editable
    (an actual change to units or price is refused by the offering lock)."""

    def val(key: str) -> Any:
        if key in data:
            return data[key]
        return getattr(current, key, None) if current is not None else None

    def changed(key: str) -> bool:
        return key in data and (current is None or not _same(data[key], getattr(current, key)))

    has_positions = positions > 0
    tv, up = val("total_value"), val("unit_price")
    offering_changed = changed("total_value") or changed("unit_price")
    if has_positions and offering_changed:
        # investors bought a defined offering: say so before any other consistency message
        raise AppError("OFFERING_LOCKED", locked_message(positions), status_code=409)
    if ("total_value" in data or "unit_price" in data) and (offering_changed or not has_positions):
        problem = units_problem(tv, up)
        if problem:
            raise AppError("UNITS_MISMATCH", problem, status_code=422)
        if tv is not None and up:
            data["total_units"] = int(_dec(tv) / _dec(up))
    minimum_changed = offering_changed or changed("minimum_investment")
    if {"minimum_investment", "unit_price", "total_value"} & set(data) and (
        minimum_changed or not has_positions
    ):
        problem = minimum_problem(val("minimum_investment"), up, tv)
        if problem:
            raise AppError("MINIMUM_NOT_WHOLE_UNITS", problem, status_code=422)
    warnings: list[str] = []
    if "expected_yield" in data:
        data["target_yield"] = data["expected_yield"]
    if {"expected_yield", "capital_appreciation", "total_return"} & set(data):
        y, a = val("expected_yield"), val("capital_appreciation")
        if (
            "total_return" in data
            and data["total_return"] is None
            and y is not None
            and a is not None
        ):
            data["total_return"] = (_dec(y) + _dec(a)).quantize(_CENT)
        warning = total_return_warning(y, a, val("total_return"))
        if warning:
            warnings.append(warning)
    return data, warnings


def _effective_yield(prop: Property) -> Any:
    return prop.expected_yield if prop.expected_yield is not None else prop.target_yield


def publish_checklist(
    prop: Property, *, milestones: int, has_positions: bool = False
) -> dict[str, list[str]]:
    """What must be fixed before publishing (blockers) and what is worth adding.

    Return fields are blocking for EVERY model because the public property page renders
    expected rental yield, capital appreciation and total return unconditionally (blank shows
    "0%"), and the marketplace card shows the yield."""
    blockers: list[str] = []
    recommended: list[str] = []
    warnings: list[str] = []
    profile = profile_of(prop.model)
    if prop.model in HIDDEN_MODELS:
        blockers.append(
            f"Ownership model: '{prop.model}' is not available "
            f"({HIDDEN_MODEL_REASONS[prop.model]}). "
            "Choose an available model under Listing details."
        )
    if not has_positions:
        units_msg = units_problem(prop.total_value, prop.unit_price)
        if units_msg:
            blockers.append(units_msg)
        elif prop.unit_price:
            expected = int(_dec(prop.total_value) / _dec(prop.unit_price))
            if prop.total_units != expected:
                blockers.append(
                    f"Total units: the listing has {prop.total_units:,} units but "
                    f"{usd(prop.total_value)} ÷ {usd(prop.unit_price)} = {expected:,}. "
                    "Open Listing details and press Save to recalculate."
                )
        minimum_msg = minimum_problem(prop.minimum_investment, prop.unit_price, prop.total_value)
        if minimum_msg:
            blockers.append(minimum_msg)
    yield_label = CORE_BY_NAME["expected_yield"].label_for(profile)
    for label, value in (
        (yield_label, _effective_yield(prop)),
        ("Expected capital appreciation", prop.capital_appreciation),
        ("Total expected return", prop.total_return),
    ):
        if value is None or _dec(value) == 0:
            state = "empty" if value is None else "0"
            blockers.append(
                f"{label}: is {state}. The property page would show 0%. Enter a figure "
                "greater than 0 under Listing details."
            )
    if profile in OFFPLAN_PROFILES and prop.expected_completion is None:
        blockers.append(
            "Expected completion date: is empty. Off-plan listings must show when the "
            "property is expected to be handed over. Set it under Construction and timeline."
        )
    warning = total_return_warning(
        _effective_yield(prop), prop.capital_appreciation, prop.total_return
    )
    if warning:
        warnings.append(warning)
    content = prop.content or {}
    if not (prop.description or "").strip():
        recommended.append("Description: the Overview tab would show an empty description.")
    if not (prop.images or []):
        recommended.append("Photos: the page would show a 'Photos coming soon' placeholder.")
    if not ((content.get("developer") or {}).get("name")):
        recommended.append("Developer: the developer card would show '—' instead of a name.")
    if profile in OFFPLAN_PROFILES and milestones == 0:
        recommended.append(
            "Milestones: the Timeline tab would say no milestones have been published yet."
        )
    return {"blockers": blockers, "recommended": recommended, "warnings": warnings}


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


def _opt_text(raw: Any, field: str, *, max_len: int = 1200) -> str:
    """Multi-line free text: keeps paragraph breaks, trims each line, drops blank runs."""
    lines = [" ".join(line.split()) for line in str(raw or "").splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if len(text) > max_len:
        raise _bad(field, f"must be at most {max_len} characters")
    return text


def _opt_website(raw: Any, field: str = "website") -> str:
    """An http(s) link with a real host, or blank. Rendered as a clickable link on the public
    developer profile, so anything else (javascript:, data:, a bare word) is refused."""
    s = str(raw or "").strip()
    if not s:
        return ""
    if len(s) > 200:
        raise _bad(field, "must be at most 200 characters")
    if "://" not in s:
        s = "https://" + s
    parsed = urlparse(s)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or "." not in parsed.hostname:
        raise _bad(field, "must be a web address such as https://www.example.com")
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
    # shown on the public developer profile (/developers/{slug})
    _put(d, "about", _opt_text(form.get("about"), "about"))
    _put(d, "website", _opt_website(form.get("website")))
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
