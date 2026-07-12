"""0023 — role application data on role_grant_requests (Task 12).

Broker / Liquidity-Provider activation now goes through a real application: the applicant
submits join-form fields + uploaded documents, which the admin reviews before approving. The
application (fields + document storage refs) is stored as JSONB on the existing approval-queue
row. Additive + nullable-safe (defaults to '{}').
"""

from __future__ import annotations

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


UPGRADE = r"""
ALTER TABLE public.role_grant_requests
  ADD COLUMN IF NOT EXISTS application JSONB NOT NULL DEFAULT '{}'::jsonb;
"""

DOWNGRADE = r"""
ALTER TABLE public.role_grant_requests DROP COLUMN IF EXISTS application;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
