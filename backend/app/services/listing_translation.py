"""Arabic and French versions of what is written by hand for a listing (client, 2026-11-01): the
site's own words change with its language, a property's description or its developer's details
did not.

A version is kept in ``properties.content`` under ``translations``, one per language:

    {"ar": {"columns": {"title": ..., "description": ...},
            "content": {"developer": {"about": ...}, "risks": [{"label": ..., "note": ...}]},
            "milestones": {"<id>": {"title": ...}},
            "documents": {"<id>": {"title": ...}},
            "prices": {"<id>": {"label": ..., "note": ...}}},
     "fr": {...}}

The public reads ask with ``?lang=ar|fr`` and get the same answer with the translated text in
place, so the pages need not know. English stays the master: a box left blank shows the English,
and text removed from the English goes in every language. Slugs, figures, risk levels and the
country / city the marketplace filters on are never translated.
"""

from __future__ import annotations

from typing import Any

LANGUAGES = {"ar": "Arabic", "fr": "French"}
KEY = "translations"
COLUMNS = ("title", "subtitle", "location", "description", "spv_name", "legal_structure")
SUMMARY_COLUMNS = ("title", "subtitle", "location")


def language(code: str | None) -> str | None:
    """A language with versions, or None for English and anything unknown."""
    return code if code in LANGUAGES else None


def public_content(content: Any) -> dict:
    """The listing's content without its stored versions."""
    if not isinstance(content, dict):
        return {}
    return {k: v for k, v in content.items() if k != KEY}


def version(content: Any, lang: str | None) -> dict:
    """What is stored for one language ({} when nothing is)."""
    if not lang or not isinstance(content, dict):
        return {}
    versions = content.get(KEY)
    found = versions.get(lang) if isinstance(versions, dict) else None
    return found if isinstance(found, dict) else {}


def _part(found: dict, key: str) -> dict:
    part = found.get(key)
    return part if isinstance(part, dict) else {}


def _merged(base: Any, over: Any) -> Any:
    """``base`` with the text of ``over`` in place: same shape, nothing that base does not have."""
    if isinstance(base, dict) and isinstance(over, dict):
        return {k: _merged(v, over[k]) if k in over else v for k, v in base.items()}
    if isinstance(base, list) and isinstance(over, list):
        if base and all(isinstance(x, str) for x in base):
            # a plain list (amenities): the version is its own list
            return [x for x in over if isinstance(x, str) and x] or base
        # rows (risks, scenarios): line by line, and a row the version lacks stays in English
        return [_merged(b, over[i]) if i < len(over) else b for i, b in enumerate(base)]
    if isinstance(base, str) and base and isinstance(over, str) and over:
        return over
    return base


def localized_columns(data: dict, content: Any, lang: str | None, names: tuple[str, ...]) -> dict:
    columns = _part(version(content, lang), "columns")
    for name in names:
        if data.get(name) and isinstance(columns.get(name), str) and columns[name]:
            data[name] = columns[name]
    return data


def developer_field(content: Any, lang: str | None, key: str) -> str | None:
    dev = _part(version(content, lang), "content").get("developer")
    value = dev.get(key) if isinstance(dev, dict) else None
    return value if isinstance(value, str) and value else None


def localized_summary(data: dict, content: Any, lang: str | None) -> dict:
    """A marketplace card in the language. Its developer slug keeps pointing at the same profile:
    only the name shown changes."""
    if not language(lang):
        return data
    localized_columns(data, content, lang, SUMMARY_COLUMNS)
    name = developer_field(content, lang, "name")
    if data.get("developer_name") and name:
        data["developer_name"] = name
    return data


def localized_detail(data: dict, content: Any, lang: str | None) -> dict:
    """A property page in the language; ``data`` carries its serialized milestones, if any."""
    if not language(lang):
        return data
    localized_summary(data, content, lang)
    localized_columns(data, content, lang, COLUMNS)
    found = version(content, lang)
    data["content"] = _merged(data.get("content") or {}, _part(found, "content"))
    if data.get("milestones"):
        versions = _part(found, "milestones")
        data["milestones"] = [
            _merged(m, versions.get(str(m.get("id")), {})) for m in data["milestones"]
        ]
    return data


def localized_prices(history: dict, rows: Any, content: Any, lang: str | None) -> dict:
    """The price line in the language: a sales phase's name and the note of each change. The
    first point is the launch price, which is the site's own words."""
    versions = _part(version(content, lang), "prices")
    if not versions:
        return history
    for point, row in zip(history["points"][1:], rows, strict=False):
        found = _part(versions, str(row.id))
        for key in ("label", "note"):
            if point.get(key) and isinstance(found.get(key), str) and found[key]:
                point[key] = found[key]
    named = [p["label"] for p in history["points"][1:] if p.get("label")]
    if named:
        history["phase"] = named[-1]
    return history


def document_title(content: Any, lang: str | None, doc_id: Any, title: str) -> str:
    doc = _part(_part(version(content, lang), "documents"), str(doc_id))
    value = doc.get("title")
    return value if isinstance(value, str) and value else title
