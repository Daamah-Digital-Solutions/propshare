"""0012 phase11 — broker referrals & commissions.

A broker (admin-approved app role from Phase 1) shares a code; a client who signs up
with that code is linked to the broker ONCE, at signup only (never retroactively). The
broker then earns a commission = ``broker_commission_pct`` × the **platform revenue
attributable to that client** — NEVER a percentage of the client's investment amount.
The platform-revenue events in v1 are:
  * the purchase platform fee (Phase 5, one-time at investment confirmation), and
  * the rental management fee withheld per distribution (Phase 6, recurring while held).

Schema (three new tables; ``transaction_type.referral_commission`` already exists in 0001):
  * broker_codes        — one server-generated shareable code per broker (UNIQUE broker).
  * broker_referrals     — the first-class broker↔client link. client_id UNIQUE +
                           immutable (one broker per client, set once at signup),
                           CHECK(broker_id <> client_id) (no self-referral link).
  * broker_commissions   — append-only accrual+credit ledger. UNIQUE(revenue_event_type,
                           revenue_event_id) => one revenue event yields at most one
                           accrual (idempotency). CHECK(commission_amount <= revenue_amount)
                           => the broker can STRUCTURALLY never be paid more than the
                           platform earned from that client. commission_rate is snapshotted
                           per row so an admin rate change never rewrites history.

Settings: broker_commission_pct (default 10.0 — % of platform revenue, admin-editable
live exactly like liquidity_fee_pct).
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


TABLES_UPGRADE = r"""
CREATE TABLE IF NOT EXISTS public.broker_codes (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  broker_id   UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  code        TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT broker_codes_broker_id_key UNIQUE (broker_id),
  CONSTRAINT broker_codes_code_key UNIQUE (code)
);

CREATE TABLE IF NOT EXISTS public.broker_referrals (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  broker_id   UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  client_id   UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  code_id     UUID REFERENCES public.broker_codes(id) ON DELETE SET NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT broker_referrals_client_id_key UNIQUE (client_id),
  CONSTRAINT broker_referrals_no_self CHECK (broker_id <> client_id)
);
CREATE INDEX IF NOT EXISTS broker_referrals_broker_idx
  ON public.broker_referrals (broker_id);

CREATE TABLE IF NOT EXISTS public.broker_commissions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  broker_id          UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  client_id          UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  referral_id        UUID NOT NULL REFERENCES public.broker_referrals(id) ON DELETE CASCADE,
  revenue_event_type TEXT NOT NULL,
  revenue_event_id   UUID NOT NULL,
  revenue_amount     NUMERIC(18, 2) NOT NULL,
  commission_rate    NUMERIC(6, 3) NOT NULL,
  commission_amount  NUMERIC(18, 2) NOT NULL,
  transaction_id     UUID REFERENCES public.transactions(id) ON DELETE SET NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT broker_commissions_event_key UNIQUE (revenue_event_type, revenue_event_id),
  CONSTRAINT broker_commissions_amount_non_negative CHECK (commission_amount >= 0),
  CONSTRAINT broker_commissions_cap CHECK (commission_amount <= revenue_amount)
);
CREATE INDEX IF NOT EXISTS broker_commissions_broker_idx
  ON public.broker_commissions (broker_id);
CREATE INDEX IF NOT EXISTS broker_commissions_client_idx
  ON public.broker_commissions (client_id);

INSERT INTO public.platform_settings (key, value, description) VALUES
  ('broker_commission_pct', '10.0',
   'Broker commission rate (percent) applied to the PLATFORM REVENUE attributable to a '
   'broker-referred client (purchase platform fee + rental management fee) — NEVER a '
   'percent of the investment amount. Admin-editable live; each accrual snapshots the '
   'rate so history is never rewritten. A DB CHECK caps any single commission at the '
   'revenue that produced it.')
ON CONFLICT (key) DO NOTHING;
"""

DOWNGRADE = r"""
DELETE FROM public.platform_settings WHERE key = 'broker_commission_pct';
DROP TABLE IF EXISTS public.broker_commissions;
DROP TABLE IF EXISTS public.broker_referrals;
DROP TABLE IF EXISTS public.broker_codes;
"""


def upgrade() -> None:
    op.execute(TABLES_UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
