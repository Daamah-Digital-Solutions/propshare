"""0006 phase5 — investment engine: platform_settings + ownership_ledger + investment cols.

  * investment_status enum gains 'expired' (system-released reservations).
  * platform_settings: admin-configurable key/value store; seeds the buyer-side
    platform fee (at purchase) and the management fee (annual, charged Phase 6).
  * ownership_ledger: append-only units ledger (one row per unit movement) — the
    source of truth for "who owns how many units of which property".
  * investments gains: idempotency_key (unique), reservation_expires_at (direct-pay
    reservation TTL), and money/fee snapshots so a later rate change never rewrites
    history.
  * properties gains a CHECK (available_units >= 0) — the DB backstop against
    overselling even if application logic is bypassed.

Oversell protection at runtime is SELECT ... FOR UPDATE on the property row in
investment_service; this CHECK is the last line of defense. Balances still live in
wallets/transactions; every move goes through the audited wallet_service.
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


# Added here; first USED at runtime in a later transaction, so the PG rule
# "can't use a new enum value in the same tx that adds it" does not apply.
ENUM_UPGRADE = "ALTER TYPE public.investment_status ADD VALUE IF NOT EXISTS 'expired';"

TABLES_UPGRADE = r"""
CREATE TABLE public.platform_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  description TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO public.platform_settings (key, value, description) VALUES
  ('platform_fee_pct', '2.5',
   'One-time platform fee charged to the buyer at purchase (percent).'),
  ('management_fee_pct', '1.0',
   'Annual management fee, deducted from rental distributions (percent). '
   'Disclosed at purchase; no money moves until Phase 6.')
ON CONFLICT (key) DO NOTHING;

CREATE TABLE public.ownership_ledger (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  property_id UUID NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  investment_id UUID REFERENCES public.investments(id) ON DELETE SET NULL,
  units INTEGER NOT NULL,
  unit_price NUMERIC(15,2) NOT NULL,
  reason TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ownership_ledger_user_idx ON public.ownership_ledger (user_id);
CREATE INDEX ownership_ledger_property_idx ON public.ownership_ledger (property_id);

ALTER TABLE public.investments
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
  ADD COLUMN IF NOT EXISTS reservation_expires_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS unit_price_snapshot NUMERIC(15,2),
  ADD COLUMN IF NOT EXISTS platform_fee_amount NUMERIC(15,2),
  ADD COLUMN IF NOT EXISTS platform_fee_rate NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS management_fee_rate NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS total_charged NUMERIC(15,2),
  ADD COLUMN IF NOT EXISTS fee_settings_snapshot JSONB,
  ADD COLUMN IF NOT EXISTS payment_id UUID,
  ADD COLUMN IF NOT EXISTS confirmed_via TEXT,
  ADD COLUMN IF NOT EXISTS failure_reason TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS investments_idempotency_key_key
  ON public.investments (idempotency_key);
CREATE INDEX IF NOT EXISTS investments_property_status_idx
  ON public.investments (property_id, status);
CREATE INDEX IF NOT EXISTS investments_reservation_idx
  ON public.investments (reservation_expires_at) WHERE status = 'pending';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'properties_available_units_nonneg'
  ) THEN
    ALTER TABLE public.properties
      ADD CONSTRAINT properties_available_units_nonneg CHECK (available_units >= 0);
  END IF;
END
$$;
"""

DOWNGRADE = r"""
ALTER TABLE public.properties DROP CONSTRAINT IF EXISTS properties_available_units_nonneg;
DROP INDEX IF EXISTS public.investments_reservation_idx;
DROP INDEX IF EXISTS public.investments_property_status_idx;
DROP INDEX IF EXISTS public.investments_idempotency_key_key;
ALTER TABLE public.investments
  DROP COLUMN IF EXISTS idempotency_key,
  DROP COLUMN IF EXISTS reservation_expires_at,
  DROP COLUMN IF EXISTS unit_price_snapshot,
  DROP COLUMN IF EXISTS platform_fee_amount,
  DROP COLUMN IF EXISTS platform_fee_rate,
  DROP COLUMN IF EXISTS management_fee_rate,
  DROP COLUMN IF EXISTS total_charged,
  DROP COLUMN IF EXISTS fee_settings_snapshot,
  DROP COLUMN IF EXISTS payment_id,
  DROP COLUMN IF EXISTS confirmed_via,
  DROP COLUMN IF EXISTS failure_reason;
DROP TABLE IF EXISTS public.ownership_ledger CASCADE;
DROP TABLE IF EXISTS public.platform_settings CASCADE;
-- NOTE: Postgres cannot DROP a value from an enum; 'expired' remains on
-- investment_status after downgrade (harmless, unused).
"""


def upgrade() -> None:
    op.execute(ENUM_UPGRADE)
    op.execute(TABLES_UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
