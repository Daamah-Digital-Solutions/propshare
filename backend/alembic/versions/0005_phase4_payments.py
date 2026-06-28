"""0005 phase4 — wallet deposits: payments + payment_events + transaction_type 'deposit'.

  * transaction_type enum gains 'deposit' (the gap the audit/plan flagged).
  * payments: one row per deposit intent; idempotency on (provider,provider_payment_id)
    and on idempotency_key.
  * payment_events: inbound-webhook dedupe ledger (one row per processed provider
    event); a replay collides on (provider,event_id) -> no double-credit.

Balances themselves live in wallets/transactions from 0001 (no structural change);
all balance mutations go through the audited wallet_service (server-only).
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


# 'ADD VALUE IF NOT EXISTS' is supported on PG12+ and is safe to run in the
# migration transaction on PG16 (we add the value here; it's first USED at runtime
# in a later transaction, so the "can't use a new enum value in the same tx" rule
# doesn't apply).
ENUM_UPGRADE = "ALTER TYPE public.transaction_type ADD VALUE IF NOT EXISTS 'deposit';"

TABLES_UPGRADE = r"""
CREATE TABLE public.payments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  provider_payment_id TEXT,
  amount NUMERIC(15,2) NOT NULL,
  amount_captured NUMERIC(15,2),
  currency TEXT NOT NULL DEFAULT 'USD',
  status TEXT NOT NULL DEFAULT 'pending',
  purpose TEXT NOT NULL DEFAULT 'deposit',
  payment_method TEXT,
  related_investment_id UUID,
  idempotency_key TEXT,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT payments_provider_pid_key UNIQUE (provider, provider_payment_id),
  CONSTRAINT payments_idempotency_key_key UNIQUE (idempotency_key)
);
CREATE INDEX payments_user_idx ON public.payments (user_id);
CREATE INDEX payments_status_idx ON public.payments (status);

CREATE TABLE public.payment_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider TEXT NOT NULL,
  event_id TEXT NOT NULL,
  payment_id UUID REFERENCES public.payments(id) ON DELETE SET NULL,
  type TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT payment_events_provider_event_key UNIQUE (provider, event_id)
);
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS public.payment_events CASCADE;
DROP TABLE IF EXISTS public.payments CASCADE;
-- NOTE: Postgres cannot DROP a value from an enum; 'deposit' remains on
-- transaction_type after downgrade (harmless, unused).
"""


def upgrade() -> None:
    op.execute(ENUM_UPGRADE)
    op.execute(TABLES_UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
