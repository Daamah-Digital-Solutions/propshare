"""0011 phase10 — family groups & gifting: real on-ledger unit transfers.

Family co-investment becomes a real money feature: a holder allocates/transfers units
to family members. Two disjoint states (the basis for the invariant + no-double-count):
  * REAL  — units physically in a member's ownership_ledger (a KYC'd user). Paid by
    Phase-6 directly, like any owner.
  * PENDING — units still in the from-holder's ledger, RESERVED for a not-yet-registered
    member, recorded as a 'pending' family_transfers row. Materializes to a real move
    when the member registers + KYC.

Schema deltas (the family_* tables from 0001 mostly suffice):
  * family_transfers gains property_id (transfers are property-scoped — the ledger is),
    idempotency_key (UNIQUE, money-move replay guard), and materialized_at.
  * family_groups gains UNIQUE(owner_id) — one group per owner.
  * transaction_type += 'family_allocation' (manual owner→member returns transfer;
    reinvest reuses 'investment').
  * platform_settings: family_reinvest_discount_pct (default 7.5 — the §7 subsidy,
    "Pronova 2.5%" is just a label inside it; Pronova system stays disabled) and
    family_transfer_fee_pct (default 0 — the UI's "$0 fee" as a real configurable source).
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


# Added here; first USED at runtime later (PG "no new enum value in same tx" is moot).
ENUM_FAMILY_ALLOCATION = (
    "ALTER TYPE public.transaction_type ADD VALUE IF NOT EXISTS 'family_allocation';"
)

TABLES_UPGRADE = r"""
ALTER TABLE public.family_transfers
  ADD COLUMN IF NOT EXISTS property_id UUID REFERENCES public.properties(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
  ADD COLUMN IF NOT EXISTS materialized_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS family_transfers_idempotency_key_key
  ON public.family_transfers (idempotency_key);
CREATE INDEX IF NOT EXISTS family_transfers_from_prop_status_idx
  ON public.family_transfers (from_member_id, property_id, status);
CREATE INDEX IF NOT EXISTS family_transfers_to_status_idx
  ON public.family_transfers (to_member_id, status);

-- One family group per owner.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'family_groups_owner_id_key'
  ) THEN
    ALTER TABLE public.family_groups ADD CONSTRAINT family_groups_owner_id_key UNIQUE (owner_id);
  END IF;
END
$$;

INSERT INTO public.platform_settings (key, value, description) VALUES
  ('family_reinvest_discount_pct', '7.5',
   'Family-scoped reinvest discount (percent). Reinvesting family returns buys units at '
   'an effective price = unit_price x (1 - this/100). The "Pronova 2.5%" is a label '
   'inside this single percentage; the Pronova payment system stays disabled. D5 (no '
   'discounts) still holds everywhere else.'),
  ('family_transfer_fee_pct', '0',
   'Fee on a family member-to-member unit transfer (percent). Default 0 — the UI''s '
   '"$0 family transfer" as a real configurable source.')
ON CONFLICT (key) DO NOTHING;
"""

DOWNGRADE = r"""
DELETE FROM public.platform_settings
 WHERE key IN ('family_reinvest_discount_pct', 'family_transfer_fee_pct');
ALTER TABLE public.family_groups DROP CONSTRAINT IF EXISTS family_groups_owner_id_key;
DROP INDEX IF EXISTS public.family_transfers_to_status_idx;
DROP INDEX IF EXISTS public.family_transfers_from_prop_status_idx;
DROP INDEX IF EXISTS public.family_transfers_idempotency_key_key;
ALTER TABLE public.family_transfers
  DROP COLUMN IF EXISTS materialized_at,
  DROP COLUMN IF EXISTS idempotency_key,
  DROP COLUMN IF EXISTS property_id;
-- enum value 'family_allocation' remains (Postgres can't drop it); harmless.
"""


def upgrade() -> None:
    op.execute(ENUM_FAMILY_ALLOCATION)
    op.execute(TABLES_UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
