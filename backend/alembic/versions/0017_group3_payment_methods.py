"""0017 group3 — saved payment methods (PCI-safe tokenization).

Stores ONLY tokens + safe display metadata — never raw card data (PAN/CVC). The card is
collected client-side via a Stripe SetupIntent (Stripe.js/Elements); we keep the Stripe
customer id and payment_method id (tokens) plus brand/last4/exp that Stripe returns.

* ``payment_customers`` — one Stripe customer per user (the token vault owner).
* ``saved_payment_methods`` — one row per tokenized method; UNIQUE(provider, pm token)
  makes re-adding the same method idempotent.
"""

from __future__ import annotations

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE IF NOT EXISTS public.payment_customers (
  user_id      UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  provider     TEXT NOT NULL DEFAULT 'stripe',
  customer_id  TEXT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.saved_payment_methods (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                     UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  provider                    TEXT NOT NULL DEFAULT 'stripe',
  provider_customer_id        TEXT,
  provider_payment_method_id  TEXT NOT NULL,   -- TOKEN only (e.g. pm_...), never card data
  type                        TEXT NOT NULL DEFAULT 'card',
  brand                       TEXT,            -- safe display metadata from Stripe
  last4                       TEXT,
  exp_month                   INTEGER,
  exp_year                    INTEGER,
  is_default                  BOOLEAN NOT NULL DEFAULT false,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT saved_payment_methods_provider_pm_key
    UNIQUE (provider, provider_payment_method_id)
);
CREATE INDEX IF NOT EXISTS saved_payment_methods_user_idx
  ON public.saved_payment_methods (user_id, created_at DESC);
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS public.saved_payment_methods;
DROP TABLE IF EXISTS public.payment_customers;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
