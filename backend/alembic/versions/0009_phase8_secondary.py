"""0009 phase8 — secondary market: investor-to-investor unit resale.

Ownership transfers AND money moves between wallets, so the schema encodes the
safeguards exactly like the primary engine:

  * secondary_listings (existing table from 0001) is upgraded to a real listing:
    adds property_id (the unit ledger is keyed by property, not the old
    investment_id), units_remaining (the live counter that partial fills decrement,
    with CHECK >= 0), and cancelled_at. investment_id becomes nullable legacy.
    Statuses: active | sold | cancelled.
  * secondary_trades: one row per fill (a listing can be partially filled many
    times). UNIQUE(idempotency_key) — a buyer's request replay can't double-buy.
  * transaction_type gains 'secondary_sale' (the seller's proceeds credit). The
    buyer side reuses 'investment' (the gross) + 'fee' (the resale fee).
  * platform_settings seeds the admin-configurable knobs: resale fee (buyer-side,
    default 1.0%), lock-up days (default 0 = sell immediately), and price bounds
    (default OPEN = no bounds; empty string means "unset/open").

Ownership stays in the append-only ownership_ledger (reasons 'secondary_sale' for
the seller's -M row and 'secondary_purchase' for the buyer's +M row): Σ units per
property is conserved by every trade.
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


# Added here; first USED at runtime in a later transaction, so the PG rule
# "can't use a new enum value in the same tx that adds it" does not apply.
ENUM_UPGRADE = "ALTER TYPE public.transaction_type ADD VALUE IF NOT EXISTS 'secondary_sale';"

TABLES_UPGRADE = r"""
-- Upgrade the legacy secondary_listings table into a property-keyed listing.
ALTER TABLE public.secondary_listings
  ADD COLUMN IF NOT EXISTS property_id UUID REFERENCES public.properties(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS units_remaining INTEGER,
  ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;

-- Backfill units_remaining for any pre-existing rows, then enforce NOT NULL + CHECK.
UPDATE public.secondary_listings SET units_remaining = units_for_sale WHERE units_remaining IS NULL;
ALTER TABLE public.secondary_listings ALTER COLUMN units_remaining SET NOT NULL;
ALTER TABLE public.secondary_listings ALTER COLUMN investment_id DROP NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'secondary_listings_units_remaining_nonneg'
  ) THEN
    ALTER TABLE public.secondary_listings
      ADD CONSTRAINT secondary_listings_units_remaining_nonneg CHECK (units_remaining >= 0);
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS secondary_listings_property_status_idx
  ON public.secondary_listings (property_id, status);
CREATE INDEX IF NOT EXISTS secondary_listings_seller_idx
  ON public.secondary_listings (seller_id);

CREATE TABLE public.secondary_trades (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id UUID NOT NULL REFERENCES public.secondary_listings(id) ON DELETE CASCADE,
  property_id UUID NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  seller_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  buyer_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  units INTEGER NOT NULL,
  price_per_unit NUMERIC(15,2) NOT NULL,
  gross NUMERIC(15,2) NOT NULL,
  resale_fee NUMERIC(15,2) NOT NULL,
  total_charged NUMERIC(15,2) NOT NULL,
  idempotency_key TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT secondary_trades_units_positive CHECK (units > 0),
  CONSTRAINT secondary_trades_idempotency_key_key UNIQUE (idempotency_key)
);
CREATE INDEX secondary_trades_listing_idx ON public.secondary_trades (listing_id);
CREATE INDEX secondary_trades_buyer_idx ON public.secondary_trades (buyer_id);
CREATE INDEX secondary_trades_seller_idx ON public.secondary_trades (seller_id);

INSERT INTO public.platform_settings (key, value, description) VALUES
  ('secondary_resale_fee_pct', '1.0',
   'Secondary-market resale fee (percent), charged buyer-side on top of the gross. '
   'The seller receives the full gross; the fee is retained as platform revenue.'),
  ('secondary_lockup_days', '0',
   'Days a holder must wait after their earliest acquisition of a property before '
   'they may list units of it. 0 = sell immediately.'),
  ('secondary_price_min_pct', '',
   'Minimum listing price as a percent of the property unit_price. Empty = open '
   '(no lower bound).'),
  ('secondary_price_max_pct', '',
   'Maximum listing price as a percent of the property unit_price. Empty = open '
   '(no upper bound).')
ON CONFLICT (key) DO NOTHING;
"""

DOWNGRADE = r"""
DELETE FROM public.platform_settings WHERE key IN (
  'secondary_resale_fee_pct', 'secondary_lockup_days',
  'secondary_price_min_pct', 'secondary_price_max_pct'
);
DROP TABLE IF EXISTS public.secondary_trades CASCADE;
DROP INDEX IF EXISTS public.secondary_listings_seller_idx;
DROP INDEX IF EXISTS public.secondary_listings_property_status_idx;
ALTER TABLE public.secondary_listings DROP CONSTRAINT IF EXISTS secondary_listings_units_remaining_nonneg;
ALTER TABLE public.secondary_listings
  DROP COLUMN IF EXISTS cancelled_at,
  DROP COLUMN IF EXISTS units_remaining,
  DROP COLUMN IF EXISTS property_id;
-- NOTE: Postgres cannot DROP a value from an enum; 'secondary_sale' remains on
-- transaction_type after downgrade (harmless, unused). investment_id stays nullable.
"""


def upgrade() -> None:
    op.execute(ENUM_UPGRADE)
    op.execute(TABLES_UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
