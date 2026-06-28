"""0003 phase2 — KYC automation (Sumsub) + audit log + webhook idempotency.

  * kyc_verifications: provider columns + manual-review flag + last review answer.
  * kyc_webhook_events: idempotency ledger (one row per verified webhook delivery).
  * audit_log: append-only record of privileged/state-changing actions.

No enum change — the manual-review "exception" is a boolean flag, so the existing
kyc_status (pending|submitted|verified|rejected) the SPA already renders is kept.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


UPGRADE = r"""
ALTER TABLE public.kyc_verifications
  ADD COLUMN IF NOT EXISTS provider TEXT,
  ADD COLUMN IF NOT EXISTS provider_applicant_id TEXT,
  ADD COLUMN IF NOT EXISTS manual_review_required BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS last_review_answer TEXT;

CREATE INDEX IF NOT EXISTS kyc_verifications_applicant_idx
  ON public.kyc_verifications (provider_applicant_id);
CREATE INDEX IF NOT EXISTS kyc_verifications_review_idx
  ON public.kyc_verifications (manual_review_required) WHERE manual_review_required;

CREATE TABLE public.kyc_webhook_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_key TEXT NOT NULL UNIQUE,
  provider TEXT NOT NULL,
  applicant_id TEXT,
  type TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id UUID,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT,
  before JSONB,
  after JSONB,
  ip TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_entity_idx ON public.audit_log (entity_type, entity_id);
CREATE INDEX audit_log_created_idx ON public.audit_log (created_at);
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS public.audit_log CASCADE;
DROP TABLE IF EXISTS public.kyc_webhook_events CASCADE;
DROP INDEX IF EXISTS public.kyc_verifications_review_idx;
DROP INDEX IF EXISTS public.kyc_verifications_applicant_idx;
ALTER TABLE public.kyc_verifications
  DROP COLUMN IF EXISTS last_review_answer,
  DROP COLUMN IF EXISTS manual_review_required,
  DROP COLUMN IF EXISTS provider_applicant_id,
  DROP COLUMN IF EXISTS provider;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
