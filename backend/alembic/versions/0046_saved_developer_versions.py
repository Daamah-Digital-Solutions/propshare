"""0046 — the Arabic and French text of a saved developer.

Client (2026-11-19): a saved developer must not be typed again in Arabic and French for every
listing. ``saved_developers.versions`` keeps the developer part of a listing's language versions
({"ar": {"name", "about", "previousProjects", "verifications"}, "fr": {...}}); picking a saved
developer in the Listing Editor brings every language with it.

Filled at once from the listings that already translate their developer card (the newest
listing's text wins, per language). Additive; raw SQL like 0029-0045.
"""

from __future__ import annotations

import json
import re
import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

LANGUAGES = ("ar", "fr")
TEXT = ("name", "about", "previousProjects", "verifications")


def _slug(name: str) -> str | None:
    # the same rule as property_service.developer_slug (kept here: a migration never imports app)
    norm = unicodedata.normalize("NFKC", name).casefold()
    slug = re.sub(r"[^\w]+", "-", norm, flags=re.UNICODE).replace("_", "-").strip("-")
    return slug[:80] or None


def _obj(value):
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute(
        "ALTER TABLE saved_developers "
        "ADD COLUMN IF NOT EXISTS versions JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT content->'developer', content->'translations' FROM properties "
            "WHERE jsonb_typeof(content->'developer') = 'object' "
            "AND jsonb_typeof(content->'translations') = 'object' ORDER BY created_at"
        )
    ).all()
    found: dict[str, dict] = {}
    for dev, versions in rows:
        slug = _slug(str(_obj(dev).get("name") or "").strip())
        if not slug:
            continue
        for lang in LANGUAGES:
            part = _obj(_obj(_obj(versions).get(lang)).get("content")).get("developer")
            text = {k: v for k, v in _obj(part).items() if k in TEXT and v}
            if text:
                found.setdefault(slug, {})[lang] = text  # later listings overwrite earlier ones
    for slug, versions in found.items():
        bind.execute(
            sa.text(
                "UPDATE saved_developers SET versions = CAST(:v AS jsonb) "
                "WHERE slug = :s AND versions = '{}'::jsonb"
            ),
            {"s": slug, "v": json.dumps(versions, ensure_ascii=False)},
        )


def downgrade() -> None:
    op.execute("ALTER TABLE saved_developers DROP COLUMN IF EXISTS versions")
