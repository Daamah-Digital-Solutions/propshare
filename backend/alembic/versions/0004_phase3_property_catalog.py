"""0004 phase3 — property catalog & live marketplace.

Adds the ownership-model + presentation/metric columns the SPA needs so every
property screen can read live DB data (retiring the mock arrays), plus a single
JSONB ``content`` column that mirrors the rich, model-specific fields the
frontend ``SampleProperty`` type carries (ownership/investment structure,
timeline/milestones, scenarios, risks, exit mechanisms, model terms, SPV detail,
amenities, developer, market analysis). Core scalar fields stay typed columns so
they can be filtered/sorted server-side.

No enum change — property_status (draft|under_review|active|funded|closed) from
0001 already models the create->submit->approve->fund->close workflow.
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


UPGRADE = r"""
ALTER TABLE public.properties
  ADD COLUMN IF NOT EXISTS slug TEXT,
  ADD COLUMN IF NOT EXISTS model TEXT NOT NULL DEFAULT 'ready-income',
  ADD COLUMN IF NOT EXISTS subtitle TEXT,
  ADD COLUMN IF NOT EXISTS country TEXT,
  ADD COLUMN IF NOT EXISTS city TEXT,
  ADD COLUMN IF NOT EXISTS expected_yield NUMERIC(6,2),
  ADD COLUMN IF NOT EXISTS capital_appreciation NUMERIC(6,2),
  ADD COLUMN IF NOT EXISTS total_return NUMERIC(6,2),
  ADD COLUMN IF NOT EXISTS funding_progress NUMERIC(6,2) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS investors_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS content JSONB NOT NULL DEFAULT '{}'::jsonb;

-- slug is optional but unique when present (sample/demo deep-link routing).
CREATE UNIQUE INDEX IF NOT EXISTS properties_slug_key
  ON public.properties (slug) WHERE slug IS NOT NULL;

-- Public marketplace reads status IN ('active','funded'); index for the hot path.
CREATE INDEX IF NOT EXISTS properties_status_idx ON public.properties (status);
CREATE INDEX IF NOT EXISTS properties_model_idx ON public.properties (model);
CREATE INDEX IF NOT EXISTS properties_owner_idx ON public.properties (owner_id);
"""

DOWNGRADE = r"""
DROP INDEX IF EXISTS public.properties_owner_idx;
DROP INDEX IF EXISTS public.properties_model_idx;
DROP INDEX IF EXISTS public.properties_status_idx;
DROP INDEX IF EXISTS public.properties_slug_key;
ALTER TABLE public.properties
  DROP COLUMN IF EXISTS content,
  DROP COLUMN IF EXISTS investors_count,
  DROP COLUMN IF EXISTS funding_progress,
  DROP COLUMN IF EXISTS total_return,
  DROP COLUMN IF EXISTS capital_appreciation,
  DROP COLUMN IF EXISTS expected_yield,
  DROP COLUMN IF EXISTS city,
  DROP COLUMN IF EXISTS country,
  DROP COLUMN IF EXISTS subtitle,
  DROP COLUMN IF EXISTS model,
  DROP COLUMN IF EXISTS slug;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
