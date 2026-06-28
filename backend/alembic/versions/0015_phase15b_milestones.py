"""0015 phase15b — property milestones (real source for the timeline surfaces).

Adds the ``milestone_status`` enum + ``property_milestones`` table, then BACKFILLS
it from the legacy ``content.timeline[]`` JSONB so existing demo properties keep
their timelines (relative dates anchored on ``properties.created_at``, statuses
mapped done/active/upcoming -> completed/in_progress/planned, ``valueIndex`` ->
``value_index``, array order -> ``sort_index``, ``created_by`` = owner). The JSONB
is KEPT (superseded, not deleted) — the frontend just stops reading it.

The backfill reuses the SAME pure converter the seed + tests use
(``milestone_service.timeline_to_milestone_rows``), so all three stay consistent.
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


SCHEMA_UPGRADE = r"""
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'milestone_status') THEN
    CREATE TYPE milestone_status AS ENUM ('planned', 'in_progress', 'completed');
  END IF;
END$$;

CREATE TABLE IF NOT EXISTS public.property_milestones (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id   UUID NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  title         TEXT NOT NULL,
  description   TEXT,
  status        milestone_status NOT NULL DEFAULT 'planned',
  progress_pct  INTEGER,
  value_index   INTEGER,
  target_date   DATE,
  completed_at  TIMESTAMPTZ,
  sort_index    INTEGER NOT NULL DEFAULT 0,
  created_by    UUID REFERENCES public.users(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT property_milestones_progress_pct_check
    CHECK (progress_pct IS NULL OR (progress_pct >= 0 AND progress_pct <= 100))
);
CREATE INDEX IF NOT EXISTS property_milestones_property_sort_idx
  ON public.property_milestones (property_id, sort_index);
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS public.property_milestones;
DROP TYPE IF EXISTS milestone_status;
"""

_INSERT = sa.text(
    """
    INSERT INTO public.property_milestones
      (property_id, title, description, status, progress_pct, value_index,
       target_date, completed_at, sort_index, created_by)
    VALUES
      (:property_id, :title, :description, CAST(:status AS milestone_status),
       :progress_pct, :value_index, :target_date, :completed_at, :sort_index, :created_by)
    """
)


def _backfill() -> None:
    # Reuse the single pure converter the seed + tests use, so the three stay consistent.
    from app.services.milestone_service import timeline_to_milestone_rows

    bind = op.get_bind()
    props = bind.execute(
        sa.text("SELECT id, owner_id, created_at, content FROM public.properties")
    ).fetchall()
    for pid, owner_id, created_at, content in props:
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except (ValueError, TypeError):
                content = None
        timeline = content.get("timeline") if isinstance(content, dict) else None
        if not timeline:
            continue
        anchor = created_at.date()
        rows = timeline_to_milestone_rows(
            timeline,
            anchor=anchor,
            created_by=uuid.UUID(str(owner_id)) if owner_id is not None else None,
        )
        for r in rows:
            bind.execute(_INSERT, {"property_id": pid, **r})


def upgrade() -> None:
    op.execute(SCHEMA_UPGRADE)
    _backfill()


def downgrade() -> None:
    op.execute(DOWNGRADE)
