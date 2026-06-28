"""0007 phase6 — returns & distributions: distributions + distribution_items.

  * distributions: one row per (property, period) run. UNIQUE(property_id, period_key)
    is the idempotency guard — re-running a period collides and is refused (409),
    so no one is paid twice.
  * distribution_items: one row per investor per run (the audit of who got what).
    UNIQUE(distribution_id, user_id) is the belt-and-suspenders no-double-pay guard.
  * family_return_allocations gains a nullable distribution_id for traceability.

No enum change: transaction_type already carries 'return' and 'fee' (from 0001).
Wallet credits for returns still flow through the audited wallet_service.
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE public.distributions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id UUID NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'rental',           -- rental | appreciation | other
  period_key TEXT NOT NULL,                       -- free-form, e.g. '2026-Q1'
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  gross_pool NUMERIC(15,2) NOT NULL,
  total_net NUMERIC(15,2) NOT NULL DEFAULT 0,
  total_management_fee NUMERIC(15,2) NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',         -- pending | completed | failed
  idempotency_key TEXT,
  created_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT distributions_property_period_key UNIQUE (property_id, period_key),
  CONSTRAINT distributions_gross_pool_positive CHECK (gross_pool > 0)
);
CREATE INDEX distributions_property_idx ON public.distributions (property_id);

CREATE TABLE public.distribution_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  distribution_id UUID NOT NULL REFERENCES public.distributions(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,
  units INTEGER NOT NULL,
  gross_amount NUMERIC(15,2) NOT NULL,
  management_fee NUMERIC(15,2) NOT NULL DEFAULT 0,
  net_amount NUMERIC(15,2) NOT NULL,
  transaction_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT distribution_items_dist_user_key UNIQUE (distribution_id, user_id)
);
CREATE INDEX distribution_items_user_idx ON public.distribution_items (user_id);

ALTER TABLE public.family_return_allocations
  ADD COLUMN IF NOT EXISTS distribution_id UUID
    REFERENCES public.distributions(id) ON DELETE SET NULL;
"""

DOWNGRADE = r"""
ALTER TABLE public.family_return_allocations DROP COLUMN IF EXISTS distribution_id;
DROP TABLE IF EXISTS public.distribution_items CASCADE;
DROP TABLE IF EXISTS public.distributions CASCADE;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
