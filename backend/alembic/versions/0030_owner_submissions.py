"""0030 — owner listing submissions: review trail on ``properties``.

A property an owner submits (``owner_id`` set; platform-listed rows have none) now records
when it was submitted and what the review decided, so the owner sees the outcome and the
note behind it, and staff have a dedicated queue:

  * ``submitted_at`` — set on every submit (a resubmission moves it forward).
  * ``review_note``  — the message to the owner from "request changes" / "decline"; cleared
                       when the owner resubmits or the listing is approved.
  * ``review_outcome`` — the last decision: approved | changes_requested | declined | closed
                       (a declined submission and a live listing taken down are both
                       ``closed``; this tells them apart for the owner).
  * ``reviewed_at`` / ``reviewed_by`` — when that decision was taken and by whom.

Additive and idempotent, raw SQL like 0023/0026-0029.
"""

from __future__ import annotations

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE properties
            ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS review_note TEXT,
            ADD COLUMN IF NOT EXISTS review_outcome TEXT,
            ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS properties_owner_submissions_idx
            ON properties (status, submitted_at DESC) WHERE owner_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS properties_owner_submissions_idx;
        ALTER TABLE properties
            DROP COLUMN IF EXISTS reviewed_by,
            DROP COLUMN IF EXISTS reviewed_at,
            DROP COLUMN IF EXISTS review_outcome,
            DROP COLUMN IF EXISTS review_note,
            DROP COLUMN IF EXISTS submitted_at;
        """
    )
