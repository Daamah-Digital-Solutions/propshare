"""The Arabic and French boxes of the admin Listing Editor: which text a version can translate,
how the form is laid out, and turning what was typed into a version (``listing_translation``).

Only what the English says gets a box, with the English under it, so the form is as short as the
listing and nobody translates a field that is not on the page. Each save rebuilds the version
from the form: a line removed from the English takes its translation with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services import listing_service as ls
from app.services.listing_translation import COLUMNS, KEY, LANGUAGES, version
from app.services.price_service import LABEL_MAX, NOTE_MAX


@dataclass(frozen=True)
class Text:
    path: str  # a column, or a dotted place in content
    label: str
    kind: str = "line"  # line | text | lines
    max_len: int = 200
    max_items: int = 0


# content key -> (label, the columns that are words: a tone or a risk level is not)
ROWS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ownershipStructure": ("Ownership structure", ("label", "value")),
    "scenarios": ("Scenarios", ("label", "outcome")),
    "risks": ("Risk disclosures", ("label", "note")),
    "investmentStructure": ("Financial projections", ("label", "value")),
    "marketAnalysis": ("Market analysis", ("label", "value")),
    "exitMechanisms": ("Exit mechanisms", ("name", "eta", "description")),
}
_CELL_LABELS = {
    "label": "Label",
    "value": "Value",
    "outcome": "Outcome",
    "note": "How it is mitigated",
    "name": "Name",
    "eta": "Timing",
    "description": "Description",
}

# (heading, plain texts, row sections)
GROUPS: tuple[tuple[str, tuple[Text, ...], tuple[str, ...]], ...] = (
    (
        "Property",
        (
            Text("title", "Listing title"),
            Text("subtitle", "Subtitle"),
            Text("location", "Location"),
            Text("description", "Description", "text", 8000),
            Text("details.amenities", "Amenities", "lines", 60, ls.MAX_AMENITIES),
        ),
        (),
    ),
    (
        "Developer",
        (
            Text("developer.name", "Developer name", max_len=120),
            Text("developer.about", "About the developer", "text", 1200),
            Text("developer.previousProjects", "Previous projects", "lines", 160, 12),
            Text("developer.verifications", "Verification points", "lines", 160, 8),
        ),
        (),
    ),
    (
        "SPV & legal structure",
        (
            Text("spv_name", "SPV name"),
            Text("legal_structure", "Legal structure", max_len=300),
            Text("spv.jurisdiction", "Jurisdiction"),
            Text("spv.trustee", "Trustee"),
            Text("spv.auditor", "Auditor"),
            Text("spv.assetHolding", "Asset holding"),
            Text("spv.investorAllocation", "Investor allocation"),
        ),
        (),
    ),
    (
        "Terms",
        (
            Text("terms.distributionFrequency", "Distribution frequency", max_len=160),
            Text("terms.investmentTerm", "Investment period", max_len=160),
            Text("terms.exitOptions", "Exit terms", max_len=160),
        ),
        (),
    ),
    ("Overview tab", (), ("ownershipStructure", "scenarios", "risks")),
    (
        "Financials tab",
        (
            Text("cashflow.rentalProjection", "Rental / income projection", "text", 400),
            Text("cashflow.costs", "Development & operating costs", "text", 400),
            Text("cashflow.exitProjection", "Exit projection", "text", 400),
        ),
        ("investmentStructure", "marketAnalysis", "exitMechanisms"),
    ),
    (
        "Construction status & valuation",
        (
            Text("construction.engineeringStatus", "Engineering status", max_len=60),
            Text("construction.auditStatus", "Milestone audit", max_len=60),
            Text("valuation.provider", "Valuation provider"),
            Text("valuation.reportDate", "Report date", max_len=60),
            Text("valuation.impactNote", "Development impact", max_len=240),
            Text("valuation.summary", "Market analysis", "text", 800),
        ),
        (),
    ),
    ("Compliance", (Text("compliance", "Compliance points", "lines", 160, 10),), ()),
)


def _at(tree: Any, path: str) -> Any:
    for part in path.split("."):
        tree = tree.get(part) if isinstance(tree, dict) else None
    return tree


def _put(tree: dict, path: str, value: Any) -> None:
    *parents, last = path.split(".")
    for part in parents:
        tree = tree.setdefault(part, {})
    tree[last] = value


def _english(prop: Any, content: dict, spec: Text) -> Any:
    return getattr(prop, spec.path) if spec.path in COLUMNS else _at(content, spec.path)


def _translated(found: dict, spec: Text) -> Any:
    part = "columns" if spec.path in COLUMNS else "content"
    return _at(found.get(part), spec.path)


def _rows(content: dict, section: str) -> list[dict]:
    rows = content.get(section)
    return [r if isinstance(r, dict) else {} for r in rows] if isinstance(rows, list) else []


def _as_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(x) for x in value)
    return "" if value is None else str(value)


def _field(name: str, label: str, kind: str, english: Any, value: Any, max_len: int = 200) -> dict:
    return {
        "name": name,
        "label": label,
        "kind": kind,
        "english": _as_text(english),
        "value": _as_text(value),
        "max_len": max_len,
    }


def _cell(section: str, line: int, key: str) -> str:
    return f"r__{section}__{line}__{key}"


def form_model(prop: Any, milestones: list, docs: list, prices: list) -> list[dict]:
    """One form per language for the page to draw: only what the English says."""
    content = prop.content if isinstance(prop.content, dict) else {}
    out = []
    for lang, name in LANGUAGES.items():
        found = version(content, lang)
        groups = []
        for heading, texts, sections in GROUPS:
            fields = []
            for spec in texts:
                english = _english(prop, content, spec)
                if english:
                    fields.append(
                        _field(
                            f"v__{spec.path}",
                            spec.label,
                            spec.kind,
                            english,
                            _translated(found, spec),
                            spec.max_len,
                        )
                    )
            for section in sections:
                label, keys = ROWS[section]
                theirs = _at(found.get("content"), section)
                theirs = theirs if isinstance(theirs, list) else []
                for i, row in enumerate(_rows(content, section)):
                    mine = theirs[i] if i < len(theirs) and isinstance(theirs[i], dict) else {}
                    for key in keys:
                        if row.get(key):
                            fields.append(
                                _field(
                                    _cell(section, i, key),
                                    f"{label}, line {i + 1}: {_CELL_LABELS[key]}",
                                    "line",
                                    row[key],
                                    mine.get(key),
                                    240,
                                )
                            )
            if fields:
                groups.append({"title": heading, "fields": fields})
        versions = found.get("milestones")
        versions = versions if isinstance(versions, dict) else {}
        fields = []
        for i, m in enumerate(milestones, start=1):
            mine = versions.get(str(m.id))
            mine = mine if isinstance(mine, dict) else {}
            fields.append(
                _field(f"m__{m.id}__title", f"{i}. Title", "line", m.title, mine.get("title"), 120)
            )
            if m.description:
                fields.append(
                    _field(
                        f"m__{m.id}__description",
                        f"{i}. Description",
                        "line",
                        m.description,
                        mine.get("description"),
                        500,
                    )
                )
        if fields:
            groups.append({"title": "Construction milestones", "fields": fields})
        versions = found.get("documents")
        versions = versions if isinstance(versions, dict) else {}
        fields = []
        for d in docs:
            mine = versions.get(str(d.id))
            mine = mine if isinstance(mine, dict) else {}
            fields.append(
                _field(f"d__{d.id}__title", "Document title", "line", d.title, mine.get("title"))
            )
        if fields:
            groups.append({"title": "Documents", "fields": fields})
        versions = found.get("prices")
        versions = versions if isinstance(versions, dict) else {}
        fields = []
        for i, row in enumerate(prices, start=1):
            mine = versions.get(str(row.id))
            mine = mine if isinstance(mine, dict) else {}
            if row.label:
                fields.append(
                    _field(
                        f"p__{row.id}__label",
                        f"Price change {i}: phase",
                        "line",
                        row.label,
                        mine.get("label"),
                        LABEL_MAX,
                    )
                )
            if row.note:
                fields.append(
                    _field(
                        f"p__{row.id}__note",
                        f"Price change {i}: note",
                        "line",
                        row.note,
                        mine.get("note"),
                        NOTE_MAX,
                    )
                )
        if fields:
            groups.append({"title": "Unit price history", "fields": fields})
        every = [f for g in groups for f in g["fields"]]
        out.append(
            {
                "lang": lang,
                "name": name,
                "dir": "rtl" if lang == "ar" else "ltr",
                "groups": groups,
                "total": len(every),
                "filled": sum(1 for f in every if f["value"]),
            }
        )
    return out


def with_version(
    prop: Any, form: Any, lang: str, milestones: list, docs: list, prices: list
) -> dict:
    """The listing's content with this language's version rebuilt from the form. The limits are
    the English field's, so a translation fits wherever the English does."""
    if lang not in LANGUAGES:
        raise ValueError("That language is not recognised. Please reload the page.")
    content = prop.content if isinstance(prop.content, dict) else {}
    built: dict[str, Any] = {
        "columns": {},
        "content": {},
        "milestones": {},
        "documents": {},
        "prices": {},
    }

    for _heading, texts, sections in GROUPS:
        for spec in texts:
            if not _english(prop, content, spec):
                continue
            raw = form.get(f"v__{spec.path}")
            if spec.kind == "lines":
                value = ls.parse_lines(
                    raw, spec.label, spec.max_items, max_len=spec.max_len
                )  # one per line, as in the English box
            elif spec.kind == "text":
                value = ls._opt_text(raw, spec.label, max_len=spec.max_len)
            else:
                value = ls._opt_str(raw, spec.label, max_len=spec.max_len)
            if value:
                if spec.path in COLUMNS:
                    built["columns"][spec.path] = value
                else:
                    _put(built["content"], spec.path, value)
        for section in sections:
            label, keys = ROWS[section]
            rows = []
            for i, row in enumerate(_rows(content, section)):
                cells = {}
                for key in keys:
                    value = ls._opt_str(
                        form.get(_cell(section, i, key)),
                        f"{label}, line {i + 1}",
                        max_len=240,
                    )
                    if value and row.get(key):
                        cells[key] = value
                rows.append(cells)
            if any(rows):  # by position: blank rows hold the place of the English ones
                built["content"][section] = rows

    for m in milestones:
        cells = {}
        title = ls._opt_str(form.get(f"m__{m.id}__title"), "Milestone title", max_len=120)
        if title:
            cells["title"] = title
        if m.description:
            note = ls._opt_str(
                form.get(f"m__{m.id}__description"), "Milestone description", max_len=500
            )
            if note:
                cells["description"] = note
        if cells:
            built["milestones"][str(m.id)] = cells
    for d in docs:
        title = ls._opt_str(form.get(f"d__{d.id}__title"), "Document title")
        if title:
            built["documents"][str(d.id)] = {"title": title}
    for row in prices:
        cells = {}
        if row.label:
            label = ls._opt_str(form.get(f"p__{row.id}__label"), "Phase", max_len=LABEL_MAX)
            if label:
                cells["label"] = label
        if row.note:
            note = ls._opt_str(form.get(f"p__{row.id}__note"), "Note", max_len=NOTE_MAX)
            if note:
                cells["note"] = note
        if cells:
            built["prices"][str(row.id)] = cells

    versions = content.get(KEY)
    versions = dict(versions) if isinstance(versions, dict) else {}
    versions[lang] = {k: v for k, v in built.items() if v}
    new = dict(content)
    new[KEY] = versions
    return new
