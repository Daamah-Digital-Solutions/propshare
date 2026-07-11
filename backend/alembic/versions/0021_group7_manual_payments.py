"""0021 group7 — manual, admin-settled money-out + bank-transfer deposits.

Owner decision (2026-07-11): withdrawals are MANUAL — the investor picks a saved
destination and the request goes to the admin queue to be paid out BY HAND (no Stripe
Connect / NOWPayments payout). Crypto DEPOSITS stay automated (NOWPayments); crypto
WITHDRAWALS are manual too. Bank-transfer DEPOSITS become a manual claim against the
platform's own receiving accounts, credited by an admin.

Tables (additive; the Stripe/NOWPayments payout path is untouched, just gated off by
``manual_payouts_enabled``):
  * user_bank_accounts     — an investor's saved bank payout destination.
  * user_crypto_wallets    — an investor's saved crypto payout address.
  * platform_bank_accounts — the platform's receiving accounts (admin-managed), shown
    to users for bank-transfer deposits.

No new tables for withdrawals (provider='manual' + the existing JSONB destination) or
deposits (a pending Payment row with provider='manual_bank'). One default per user is
enforced by a partial unique index.
"""

from __future__ import annotations

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE IF NOT EXISTS public.user_bank_accounts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  label           TEXT,
  account_holder  TEXT NOT NULL,
  bank_name       TEXT NOT NULL,
  iban            TEXT,
  account_number  TEXT,
  swift_bic       TEXT,
  country         TEXT,
  currency        TEXT NOT NULL DEFAULT 'USD',
  is_default      BOOLEAN NOT NULL DEFAULT false,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS user_bank_accounts_user_idx
  ON public.user_bank_accounts (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS user_bank_accounts_one_default
  ON public.user_bank_accounts (user_id) WHERE is_default;

CREATE TABLE IF NOT EXISTS public.user_crypto_wallets (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  label        TEXT,
  network      TEXT NOT NULL,
  address      TEXT NOT NULL,
  is_default   BOOLEAN NOT NULL DEFAULT false,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS user_crypto_wallets_user_idx
  ON public.user_crypto_wallets (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS user_crypto_wallets_one_default
  ON public.user_crypto_wallets (user_id) WHERE is_default;

CREATE TABLE IF NOT EXISTS public.platform_bank_accounts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  bank_name       TEXT NOT NULL,
  account_holder  TEXT NOT NULL,
  iban            TEXT,
  account_number  TEXT,
  swift_bic       TEXT,
  currency        TEXT NOT NULL DEFAULT 'USD',
  country         TEXT,
  instructions    TEXT,
  is_active       BOOLEAN NOT NULL DEFAULT true,
  sort_order      INTEGER NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS platform_bank_accounts_active_idx
  ON public.platform_bank_accounts (is_active, sort_order);

INSERT INTO public.platform_settings (key, value, description) VALUES
  ('manual_payouts_enabled', 'true',
   'When true, withdrawals are settled MANUALLY by an admin (no Stripe Connect / NOWPayments '
   'payout): the request holds funds and waits in the admin queue for mark-paid/reject. Flip to '
   'false to re-enable the automated provider payout path.')
ON CONFLICT (key) DO NOTHING;
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS public.user_bank_accounts;
DROP TABLE IF EXISTS public.user_crypto_wallets;
DROP TABLE IF EXISTS public.platform_bank_accounts;
DELETE FROM public.platform_settings WHERE key = 'manual_payouts_enabled';
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
