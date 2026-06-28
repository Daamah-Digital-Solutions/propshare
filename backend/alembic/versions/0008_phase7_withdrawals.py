"""0008 phase7 — withdrawals & payouts: withdrawals + payout_events + connect_accounts.

Money LEAVES the platform here, so the schema encodes the safeguards:
  * withdrawals: the lifecycle (pending_review|approved|processing|completed|failed|
    returned|rejected) with UNIQUE(idempotency_key) — a request replay can't create
    a second hold — and CHECK(amount > 0).
  * payout_events: signed-webhook dedupe ledger, UNIQUE(provider, event_id) — a
    replayed settlement can't double-settle.
  * connect_accounts: Stripe Connect onboarding state per user (bank payouts gate).

transactions/wallets already suffice: transaction_type has 'withdrawal' and
wallets.pending_balance (+ its >= 0 CHECK) holds funds in flight. The
withdrawal_auto_approve_limit lives in platform_settings (admin-editable).
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE public.withdrawals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  amount NUMERIC(15,2) NOT NULL,
  method TEXT NOT NULL,                       -- bank | crypto
  provider TEXT NOT NULL,                     -- stripe | nowpayments
  destination JSONB NOT NULL DEFAULT '{}',    -- tokenized only: connect acct id / crypto address
  status TEXT NOT NULL DEFAULT 'pending_review',
  idempotency_key TEXT,
  provider_payout_id TEXT,
  failure_reason TEXT,
  reviewed_by UUID,
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT withdrawals_amount_positive CHECK (amount > 0),
  CONSTRAINT withdrawals_idempotency_key_key UNIQUE (idempotency_key)
);
CREATE INDEX withdrawals_user_idx ON public.withdrawals (user_id);
CREATE INDEX withdrawals_status_idx ON public.withdrawals (status);

CREATE TABLE public.payout_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider TEXT NOT NULL,
  event_id TEXT NOT NULL,
  withdrawal_id UUID REFERENCES public.withdrawals(id) ON DELETE SET NULL,
  type TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT payout_events_provider_event_key UNIQUE (provider, event_id)
);

CREATE TABLE public.connect_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  stripe_account_id TEXT,
  payouts_enabled BOOLEAN NOT NULL DEFAULT false,
  details_submitted BOOLEAN NOT NULL DEFAULT false,
  status TEXT NOT NULL DEFAULT 'none',        -- none | pending | verified | restricted
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT connect_accounts_user_key UNIQUE (user_id)
);

INSERT INTO public.platform_settings (key, value, description) VALUES
  ('withdrawal_auto_approve_limit', '5000',
   'Withdrawals at or under this amount (USD) auto-process; above it they go to the '
   'admin review queue.')
ON CONFLICT (key) DO NOTHING;
"""

DOWNGRADE = r"""
DELETE FROM public.platform_settings WHERE key = 'withdrawal_auto_approve_limit';
DROP TABLE IF EXISTS public.connect_accounts CASCADE;
DROP TABLE IF EXISTS public.payout_events CASCADE;
DROP TABLE IF EXISTS public.withdrawals CASCADE;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
