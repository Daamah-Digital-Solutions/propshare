"""Saved developer profiles (client letter, 2026-11-18).

The admin panel keeps each developer's full profile once (``saved_developers``). It fills itself:
every time a listing's developer card is saved, that profile is remembered under the developer's
name. The Listing Editor offers the saved developers; picking one fills the card, so a new listing
does not need the developer typed again. The Developers page edits a saved profile and can apply
it to every listing that names that developer.

A saved developer also keeps its Arabic and French text (``versions``, client 2026-11-19: the
developer must not be typed again in every language for each listing): the developer part of a
listing's language versions. It is learned from the listings (a saved Arabic or French version
of a listing teaches it), edited on the Developers page, and comes with the developer when a
listing picks it.
"""

from __future__ import annotations

import copy
import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import Property
from app.models.developers import SavedDeveloper
from app.services import listing_service
from app.services.listing_translation import KEY, LANGUAGES, version
from app.services.property_service import developer_slug

# the developer card's text a language version translates, with the English box's limits
# (listing_translation_form "Developer"): (key, label, kind, max_len, max_items)
VERSION_FIELDS: tuple[tuple[str, str, str, int, int], ...] = (
    ("name", "Developer name", "line", 120, 0),
    ("about", "About the developer", "text", 1200, 0),
    ("previousProjects", "Previous projects", "lines", 160, 12),
    ("verifications", "Verification points", "lines", 160, 8),
)
_TEXT_KEYS = tuple(f[0] for f in VERSION_FIELDS)


def profile_of(content: dict | None) -> dict:
    dev = (content or {}).get("developer")
    return copy.deepcopy(dev) if isinstance(dev, dict) else {}


async def list_saved(session: AsyncSession) -> list[SavedDeveloper]:
    res = await session.execute(select(SavedDeveloper).order_by(SavedDeveloper.name))
    return list(res.scalars().all())


def versions_in(content: dict | None) -> dict[str, dict]:
    """The developer part of each of a listing's language versions ({} where there is none)."""
    out: dict[str, dict] = {}
    for lang in LANGUAGES:
        part = version(content, lang).get("content")
        dev = part.get("developer") if isinstance(part, dict) else None
        if isinstance(dev, dict):
            text = {k: copy.deepcopy(v) for k, v in dev.items() if k in _TEXT_KEYS and v}
            if text:
                out[lang] = text
    return out


def with_versions(
    content: dict | None, versions: dict | None, *, replace: bool, drop_missing: bool
) -> dict:
    """The listing's content with the developer part of each language version set from a saved
    developer's ``versions``.

    ``replace``: a saved language replaces the listing's (the developer was picked from the saved
    list); otherwise it only fills a language the listing has not translated. ``drop_missing``: a
    language the saved developer has no text for loses the listing's (it described the developer
    the card named before)."""
    new = copy.deepcopy(content or {})
    have = versions_in(new)
    stored = new.get(KEY)
    stored = copy.deepcopy(stored) if isinstance(stored, dict) else {}
    changed = False
    for lang in LANGUAGES:
        mine = (versions or {}).get(lang)
        mine = mine if isinstance(mine, dict) and mine else None
        if mine is not None and (replace or lang not in have):
            target: dict | None = mine
        elif mine is None and drop_missing and lang in have:
            target = None
        else:
            continue
        found = stored.get(lang) if isinstance(stored.get(lang), dict) else {}
        part = dict(found.get("content")) if isinstance(found.get("content"), dict) else {}
        if target is None:
            part.pop("developer", None)
        else:
            part["developer"] = copy.deepcopy(target)
        found = {k: v for k, v in found.items() if k != "content"}
        if part:
            found["content"] = part
        if found:
            stored[lang] = found
        else:
            stored.pop(lang, None)
        changed = True
    if changed:
        new[KEY] = stored
    return new


async def find_saved(session: AsyncSession, name: str) -> SavedDeveloper | None:
    slug = developer_slug(str(name or "").strip())
    if not slug:
        return None
    return await session.scalar(select(SavedDeveloper).where(SavedDeveloper.slug == slug))


async def get_saved(session: AsyncSession, dev_id: uuid.UUID) -> SavedDeveloper:
    dev = await session.get(SavedDeveloper, dev_id)
    if dev is None:
        raise AppError("NOT_FOUND", "That developer is no longer saved.", status_code=404)
    return dev


def _snapshot(dev: SavedDeveloper | None) -> dict | None:
    if dev is None:
        return None
    return {"profile": dict(dev.profile or {}), "versions": dict(dev.versions or {})}


async def _saved(
    session: AsyncSession,
    dev: SavedDeveloper,
    before: dict | None,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    always: bool = False,
) -> None:
    """Flush, and audit when something changed (or always: a save pressed on the Developers
    page is recorded even when nothing in it changed)."""
    after = _snapshot(dev)
    if before is not None and (before != after or always):
        dev.updated_at = dt.datetime.now(dt.UTC)
    await session.flush()
    if before != after or always:
        await write_audit(
            session,
            action=action,
            entity_type="saved_developer",
            entity_id=str(dev.id),
            actor_id=actor_id,
            before=before,
            after=after,
        )


async def remember(
    session: AsyncSession,
    profile: dict,
    *,
    actor_id: uuid.UUID | None,
    versions: dict | None = None,
) -> SavedDeveloper | None:
    """Keep this profile as the saved one for its developer (by name); nothing without a name.
    ``versions`` (a listing's developer text in Arabic / French) fills only the languages the
    saved developer does not have yet."""
    name = str(profile.get("name") or "").strip()
    slug = developer_slug(name)
    if not slug:
        return None
    dev = await session.scalar(select(SavedDeveloper).where(SavedDeveloper.slug == slug))
    before = _snapshot(dev)
    if dev is None:
        dev = SavedDeveloper(slug=slug, name=name, profile=copy.deepcopy(profile), versions={})
        session.add(dev)
    else:
        dev.name = name
        dev.profile = copy.deepcopy(profile)
    known = dict(dev.versions or {})
    for lang, text in (versions or {}).items():
        if lang in LANGUAGES and text and not known.get(lang):
            known[lang] = copy.deepcopy(text)
    dev.versions = known
    await _saved(session, dev, before, actor_id=actor_id, action="developer.saved")
    return dev


async def remember_version(
    session: AsyncSession, content: dict | None, lang: str, *, actor_id: uuid.UUID | None
) -> SavedDeveloper | None:
    """A listing's Arabic or French version was saved: its developer text becomes the saved
    developer's text in that language. A version with no developer text changes nothing (one
    listing left blank does not wipe what the others taught)."""
    profile = profile_of(content)
    text = versions_in(content).get(lang)
    if not text or lang not in LANGUAGES:
        return None
    dev = await find_saved(session, str(profile.get("name") or ""))
    if dev is None:
        return await remember(session, profile, actor_id=actor_id, versions={lang: text})
    if (dev.versions or {}).get(lang) == text:
        return dev
    before = _snapshot(dev)
    dev.versions = {**(dev.versions or {}), lang: copy.deepcopy(text)}
    await _saved(session, dev, before, actor_id=actor_id, action="developer.saved")
    return dev


def parse_versions(form: Any) -> dict[str, dict]:
    """The Developers page's Arabic / French boxes (``v_<lang>__<key>``), with the limits of the
    listing's own language boxes."""
    out: dict[str, dict] = {}
    for lang, lang_name in LANGUAGES.items():
        text: dict[str, Any] = {}
        for key, label, kind, max_len, max_items in VERSION_FIELDS:
            raw = form.get(f"v_{lang}__{key}")
            field = f"{label} ({lang_name})"
            if kind == "lines":
                value: Any = listing_service.parse_lines(raw, field, max_items, max_len=max_len)
            elif kind == "text":
                value = listing_service._opt_text(raw, field, max_len=max_len)
            else:
                value = listing_service._opt_str(raw, field, max_len=max_len)
            if value:
                text[key] = value
        if text:
            out[lang] = text
    return out


async def update_saved(
    session: AsyncSession,
    dev: SavedDeveloper,
    form: dict,
    *,
    logo_url: str | None,
    actor_id: uuid.UUID | None,
) -> SavedDeveloper:
    """Edit a saved profile with the same fields and checks as a listing's developer card, and
    its Arabic / French text."""
    content = listing_service.with_developer({"developer": dev.profile}, form, logo_url=logo_url)
    profile = profile_of(content)
    versions = parse_versions(form)
    name = str(profile.get("name") or "").strip()
    slug = developer_slug(name)
    if not slug:
        raise AppError(
            "VALIDATION_ERROR", "Developer name: this field is required.", status_code=422
        )
    if slug != dev.slug:
        clash = await session.scalar(select(SavedDeveloper).where(SavedDeveloper.slug == slug))
        if clash is not None:
            raise AppError(
                "CONFLICT", f"A developer called “{clash.name}” is already saved.", status_code=409
            )
    before = _snapshot(dev)
    dev.slug, dev.name, dev.profile, dev.versions = slug, name, profile, versions
    await _saved(session, dev, before, actor_id=actor_id, action="developer.updated", always=True)
    return dev


async def delete_saved(
    session: AsyncSession, dev: SavedDeveloper, *, actor_id: uuid.UUID | None
) -> None:
    """Forget a saved profile. Listings keep their own copy of it."""
    await write_audit(
        session,
        action="developer.deleted",
        entity_type="saved_developer",
        entity_id=str(dev.id),
        actor_id=actor_id,
        before=_snapshot(dev),
        after=None,
    )
    await session.delete(dev)
    await session.flush()


async def listings_of(session: AsyncSession, slug: str) -> list[Property]:
    """Every listing whose developer card names this developer."""
    res = await session.execute(select(Property).order_by(Property.created_at.desc()))
    return [
        p
        for p in res.scalars().all()
        if developer_slug(str(profile_of(p.content).get("name") or "").strip()) == slug
    ]


async def apply_to_listings(
    session: AsyncSession, dev: SavedDeveloper, *, actor_id: uuid.UUID | None
) -> int:
    """Copy the saved profile, and its Arabic / French text, into every listing that names this
    developer (audited per listing like a save from the Listing Editor). A language the saved
    developer has no text for keeps the listing's own. Returns how many listings changed."""
    changed = 0
    for prop in await listings_of(session, dev.slug):
        new = copy.deepcopy(prop.content or {})
        new["developer"] = copy.deepcopy(dev.profile)
        new = with_versions(new, dev.versions, replace=True, drop_missing=False)
        if new == (prop.content or {}):
            continue
        await listing_service.apply_content(
            session, prop=prop, new_content=new, section="developer", actor_id=actor_id
        )
        changed += 1
    return changed


def options(saved: list[SavedDeveloper]) -> list[dict[str, Any]]:
    """What the Listing Editor needs to fill its developer card from a saved profile."""
    return [{"id": str(d.id), "name": d.name, "profile": d.profile} for d in saved]
