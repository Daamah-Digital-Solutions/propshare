"""0018 group4 — estate / inheritance (beneficiary register + admin-verified death execution).

Owner decisions (legal risk accepted, see plan/phase-estate-design.md + DECISIONS.md):
  * Allocation is FREE (owner sets beneficiary % however they wish) — NOT enforced to
    Sharia fara'id; a non-blocking disclaimer is shown at allocation time.
  * Death verification is MANUAL-ADMIN only (a death certificate document is uploaded and
    an admin confirms) — never client-asserted, never auto-inactivity.

Tables:
  * estate_beneficiaries — the holder's designated beneficiaries (free allocation %;
    REAL/PENDING like Phase-10 family: linked to a KYC'd user, or pending registration).
  * estate_events — one per deceased holder (UNIQUE subject) with the death-certificate
    document + admin verifier; status guards idempotent execution (no double transfer).
  * estate_transfers — audit of each ownership move executed / pending materialization.
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE IF NOT EXISTS public.estate_beneficiaries (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id             UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  full_name            TEXT NOT NULL,
  relationship         TEXT,
  email                TEXT,
  phone                TEXT,
  allocation_pct       INTEGER NOT NULL DEFAULT 0,
  notes                TEXT,
  meta                 JSONB NOT NULL DEFAULT '{}',   -- UI extras (role/scope/trigger/id) — round-trip
  beneficiary_user_id  UUID REFERENCES public.users(id) ON DELETE SET NULL,
  status               TEXT NOT NULL DEFAULT 'pending',   -- pending | active
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT estate_beneficiaries_alloc_check
    CHECK (allocation_pct >= 0 AND allocation_pct <= 100)
);
CREATE INDEX IF NOT EXISTS estate_beneficiaries_owner_idx
  ON public.estate_beneficiaries (owner_id);

CREATE TABLE IF NOT EXISTS public.estate_events (
  id                            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_user_id               UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  status                        TEXT NOT NULL DEFAULT 'verified',  -- verified | executed
  death_certificate_document_id UUID REFERENCES public.documents(id) ON DELETE SET NULL,
  verified_by                   UUID REFERENCES public.users(id) ON DELETE SET NULL,
  verified_at                   TIMESTAMPTZ,
  executed_at                   TIMESTAMPTZ,
  created_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT estate_events_subject_key UNIQUE (subject_user_id)
);

CREATE TABLE IF NOT EXISTS public.estate_transfers (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  estate_event_id  UUID NOT NULL REFERENCES public.estate_events(id) ON DELETE CASCADE,
  beneficiary_id   UUID REFERENCES public.estate_beneficiaries(id) ON DELETE SET NULL,
  property_id      UUID REFERENCES public.properties(id) ON DELETE SET NULL,
  units            INTEGER NOT NULL,
  status           TEXT NOT NULL DEFAULT 'completed',  -- completed | pending
  materialized_at  TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS estate_transfers_event_idx
  ON public.estate_transfers (estate_event_id);
CREATE INDEX IF NOT EXISTS estate_transfers_beneficiary_idx
  ON public.estate_transfers (beneficiary_id);
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS public.estate_transfers;
DROP TABLE IF EXISTS public.estate_events;
DROP TABLE IF EXISTS public.estate_beneficiaries;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
