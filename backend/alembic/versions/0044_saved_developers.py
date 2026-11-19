"""0044 — saved developer profiles.

Client letter (2026-11-18): the admin panel keeps each developer's full profile once; a new
listing picks a saved developer and its fields are filled from it, instead of being typed again.

  * ``saved_developers`` — one row per developer (``slug`` = the URL key the public profile
    already uses, from the name), with ``profile`` = the same object a listing keeps in
    ``content.developer`` (name, logo, rating, projectsCompleted, about, website, verified,
    yearsExperience, onTimeDelivery, previousProjects, verifications).

Filled at once from the listings that already name a developer (the newest listing's profile
wins), so the list is not empty on the first day. Additive; raw SQL like 0029-0043.
"""

from __future__ import annotations

import json
import re
import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def _slug(name: str) -> str | None:
    # the same rule as property_service.developer_slug (kept here: a migration never imports app)
    norm = unicodedata.normalize("NFKC", name).casefold()
    slug = re.sub(r"[^\w]+", "-", norm, flags=re.UNICODE).replace("_", "-").strip("-")
    return slug[:80] or None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute("""
        CREATE TABLE IF NOT EXISTS saved_developers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            profile JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT content->'developer' FROM properties "
            "WHERE jsonb_typeof(content->'developer') = 'object' "
            "AND coalesce(content->'developer'->>'name', '') <> '' ORDER BY created_at"
        )
    ).all()
    newest: dict[str, dict] = {}
    for (dev,) in rows:
        profile = dev if isinstance(dev, dict) else json.loads(dev)
        slug = _slug(str(profile.get("name") or "").strip())
        if slug:
            newest[slug] = profile  # later listings overwrite earlier ones
    for slug, profile in newest.items():
        bind.execute(
            sa.text(
                "INSERT INTO saved_developers (slug, name, profile) "
                "VALUES (:s, :n, CAST(:p AS jsonb)) ON CONFLICT (slug) DO NOTHING"
            ),
            {"s": slug, "n": str(profile.get("name")).strip(), "p": json.dumps(profile)},
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS saved_developers")
