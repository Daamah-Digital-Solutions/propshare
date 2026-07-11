"""0022 group8 — richer family member data + member bank accounts (Task 9).

The family group owner keeps a full record of each member: personal data (date of birth,
phone, national ID / passport, nationality, address) plus one or more bank accounts (the
BRX-style "Bank Accounts" list). Additive — existing members keep working (all new columns
are nullable). No card PII; bank identifiers only.
"""

from __future__ import annotations

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


UPGRADE = r"""
ALTER TABLE public.family_members ADD COLUMN IF NOT EXISTS date_of_birth DATE;
ALTER TABLE public.family_members ADD COLUMN IF NOT EXISTS phone         TEXT;
ALTER TABLE public.family_members ADD COLUMN IF NOT EXISTS national_id   TEXT;
ALTER TABLE public.family_members ADD COLUMN IF NOT EXISTS nationality   TEXT;
ALTER TABLE public.family_members ADD COLUMN IF NOT EXISTS address       TEXT;

CREATE TABLE IF NOT EXISTS public.family_member_bank_accounts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  member_id       UUID NOT NULL REFERENCES public.family_members(id) ON DELETE CASCADE,
  label           TEXT,
  bank_name       TEXT NOT NULL,
  account_holder  TEXT,
  iban            TEXT,
  account_number  TEXT,
  swift_bic       TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS family_member_bank_accounts_member_idx
  ON public.family_member_bank_accounts (member_id);
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS public.family_member_bank_accounts;
ALTER TABLE public.family_members DROP COLUMN IF EXISTS address;
ALTER TABLE public.family_members DROP COLUMN IF EXISTS nationality;
ALTER TABLE public.family_members DROP COLUMN IF EXISTS national_id;
ALTER TABLE public.family_members DROP COLUMN IF EXISTS phone;
ALTER TABLE public.family_members DROP COLUMN IF EXISTS date_of_birth;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
