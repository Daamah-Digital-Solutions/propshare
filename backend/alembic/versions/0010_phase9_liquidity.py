"""0010 phase9 — liquidity provider module: ACTIVE buyback + PASSIVE schema.

Two LP products on one balance sheet, never commingled on the same principal:
  * ACTIVE  — the LP funds a seller's instant-exit request (buys the stake at a
    liquidity discount, bears the risk, earns rental as the new owner + resale).
  * PASSIVE — a fixed-APY locked-term pool deposit (engine shipped behind a
    hard-locked flag, default OFF; no real deposit until the yield-funding source,
    ALM rules and reserve adequacy are real — see lp_passive_enabled).

Never-commingle invariant lives in ``lp_positions``: one row per committed
principal, a single-valued NOT NULL ``classification`` CHECK, and cross-field
CHECKs that force the OTHER product's columns NULL — a row is structurally one
product only.

Decision 2 (mgmt-fee leak): ``ownership_ledger`` gains a per-row ``fee_rate``
stamped at acquisition (original investors keep their agreed rate; LP/secondary
units carry the platform management_fee_pct at acquisition). Phase-6 derives the
rental fee base from the stamped rate × units held — never a global re-derive, so
no investor's agreed fee is ever changed retroactively. Existing Phase-5 rows are
backfilled from their investment's snapshot rate.
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


# Added here; first USED at runtime later, so the PG "no new enum value in the same
# tx that adds it" rule does not apply. PASSIVE principal in/out + fixed interest.
ENUM_LP_DEPOSIT = "ALTER TYPE public.transaction_type ADD VALUE IF NOT EXISTS 'lp_deposit';"
ENUM_LP_YIELD = "ALTER TYPE public.transaction_type ADD VALUE IF NOT EXISTS 'lp_yield';"

TABLES_UPGRADE = r"""
-- Decision 2: per-row management-fee stamp (the liability the owner consented to).
ALTER TABLE public.ownership_ledger
  ADD COLUMN IF NOT EXISTS fee_rate NUMERIC(6,3);

-- Backfill existing acquisitions from their investment's snapshot rate (never a
-- new/global rate — each row keeps the rate the owner originally agreed to).
UPDATE public.ownership_ledger ol
   SET fee_rate = i.management_fee_rate
  FROM public.investments i
 WHERE ol.investment_id = i.id
   AND ol.fee_rate IS NULL
   AND ol.units > 0;

-- Seller-side / non-investment acquisition rows that can't be backfilled keep
-- fee_rate NULL; the fee base treats NULL as 0 (no double-charge, no guess).

CREATE TABLE public.lp_pool_tiers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  period_months INTEGER NOT NULL,
  apy_pct NUMERIC(6,3) NOT NULL,
  min_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT lp_pool_tiers_period_positive CHECK (period_months > 0)
);
INSERT INTO public.lp_pool_tiers (period_months, apy_pct, min_amount) VALUES
  (3,  8.0,  10000),
  (6,  10.0, 25000),
  (12, 12.0, 50000),
  (24, 15.0, 100000);

-- Seller-side instant-buyout order book. The pricing snapshot is AUTHORITATIVE for
-- what the seller receives (locked at creation); the fill re-derive is a band check
-- only (lp_exit_price_band_pct), never changes the agreed payout.
CREATE TABLE public.lp_exit_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  seller_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  property_id UUID NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  units INTEGER NOT NULL,
  units_remaining INTEGER NOT NULL,
  unit_price_snapshot NUMERIC(15,2) NOT NULL,
  discount_pct_snapshot NUMERIC(6,3) NOT NULL,
  fee_pct_snapshot NUMERIC(6,3) NOT NULL,
  gross NUMERIC(15,2) NOT NULL,
  lp_price NUMERIC(15,2) NOT NULL,
  liquidity_fee NUMERIC(15,2) NOT NULL,
  seller_net NUMERIC(15,2) NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',           -- open | filled | cancelled | expired
  idempotency_key TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  filled_at TIMESTAMPTZ,
  cancelled_at TIMESTAMPTZ,
  CONSTRAINT lp_exit_requests_units_positive CHECK (units > 0),
  CONSTRAINT lp_exit_requests_remaining_nonneg CHECK (units_remaining >= 0),
  CONSTRAINT lp_exit_requests_idempotency_key_key UNIQUE (idempotency_key)
);
CREATE INDEX lp_exit_requests_property_status_idx ON public.lp_exit_requests (property_id, status);
CREATE INDEX lp_exit_requests_seller_idx ON public.lp_exit_requests (seller_id);

-- THE never-commingle table: one classified row per committed LP principal.
CREATE TABLE public.lp_positions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lp_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  classification TEXT NOT NULL,
  principal_amount NUMERIC(15,2) NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  idempotency_key TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at TIMESTAMPTZ,
  -- ACTIVE-only (append-only acquisition/audit record; holdings live in ownership_ledger)
  exit_request_id UUID REFERENCES public.lp_exit_requests(id) ON DELETE SET NULL,
  property_id UUID REFERENCES public.properties(id) ON DELETE CASCADE,
  units INTEGER,
  unit_price_snapshot NUMERIC(15,2),
  discount_pct NUMERIC(6,3),
  spread_at_entry NUMERIC(15,2),
  -- PASSIVE-only
  pool_tier_id UUID REFERENCES public.lp_pool_tiers(id) ON DELETE SET NULL,
  apy_pct_snapshot NUMERIC(6,3),
  term_months INTEGER,
  maturity_date DATE,
  accrued_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
  CONSTRAINT lp_positions_classification_chk CHECK (classification IN ('active','passive')),
  CONSTRAINT lp_positions_idempotency_key_key UNIQUE (idempotency_key),
  -- Never-commingle: an ACTIVE row carries ONLY active columns; the passive ones MUST be NULL.
  CONSTRAINT lp_positions_active_shape CHECK (
    classification <> 'active' OR (
      exit_request_id IS NOT NULL AND property_id IS NOT NULL AND units IS NOT NULL
      AND pool_tier_id IS NULL AND maturity_date IS NULL AND term_months IS NULL
    )
  ),
  CONSTRAINT lp_positions_passive_shape CHECK (
    classification <> 'passive' OR (
      pool_tier_id IS NOT NULL AND maturity_date IS NOT NULL AND term_months IS NOT NULL
      AND exit_request_id IS NULL AND units IS NULL AND property_id IS NULL
    )
  )
);
CREATE INDEX lp_positions_user_class_status_idx
  ON public.lp_positions (lp_user_id, classification, status);
CREATE INDEX lp_positions_property_idx ON public.lp_positions (property_id);

INSERT INTO public.platform_settings (key, value, description) VALUES
  ('liquidity_discount_pct', '3.0',
   'Seller haircut for an instant LP exit (percent off unit_price). The discount is '
   'the LP''s spread; snapshotted authoritatively at exit-request creation.'),
  ('liquidity_fee_pct', '2.0',
   'Single source of truth for the LP-exit liquidity fee (percent), retained as '
   'platform revenue. Replaces the conflicting per-surface display literals.'),
  ('lp_exit_request_ttl_minutes', '1440',
   'How long an open LP exit request stays fundable before it expires (minutes).'),
  ('lp_exit_price_band_pct', '10',
   'Fill-time sanity band: reject a fill if the snapshot price deviates from a fresh '
   'recompute by more than this percent. Validation only — never changes the payout.'),
  ('lp_passive_enabled', 'false',
   'HARD LOCK for the PASSIVE fixed-APY pool. Must stay false until a yield-funding '
   'source + reserve, written ALM rules, and capital/reserve adequacy are real. The '
   'engine rejects every real deposit while this is false.')
ON CONFLICT (key) DO NOTHING;
"""

DOWNGRADE = r"""
DELETE FROM public.platform_settings WHERE key IN (
  'liquidity_discount_pct', 'liquidity_fee_pct', 'lp_exit_request_ttl_minutes',
  'lp_exit_price_band_pct', 'lp_passive_enabled'
);
DROP TABLE IF EXISTS public.lp_positions CASCADE;
DROP TABLE IF EXISTS public.lp_exit_requests CASCADE;
DROP TABLE IF EXISTS public.lp_pool_tiers CASCADE;
ALTER TABLE public.ownership_ledger DROP COLUMN IF EXISTS fee_rate;
-- NOTE: enum values 'lp_deposit'/'lp_yield' remain (Postgres can't drop them); harmless.
"""


def upgrade() -> None:
    op.execute(ENUM_LP_DEPOSIT)
    op.execute(ENUM_LP_YIELD)
    op.execute(TABLES_UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
