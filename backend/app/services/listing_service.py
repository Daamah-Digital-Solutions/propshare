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
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import Property

MAX_AMENITIES = 40


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
