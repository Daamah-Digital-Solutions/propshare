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

Existing owner listings get their trail back from the audit log (``property.submit`` /
``property.reject``), so a listing submitted — or sent back — before this release is not
shown as "never submitted".

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
    # backfill from the audit log: the last submission of every owner listing...
    op.execute(
        """
        UPDATE properties p
           SET submitted_at = s.at
          FROM (SELECT entity_id, max(created_at) AS at
                  FROM audit_log
                 WHERE entity_type = 'property' AND action = 'property.submit'
                 GROUP BY entity_id) s
         WHERE p.owner_id IS NOT NULL
           AND p.submitted_at IS NULL
           AND s.entity_id = p.id::text;
        """
    )
    # ...and, for a draft whose last decision sent it back, that decision and its reason
    op.execute(
        """
        UPDATE properties p
           SET review_outcome = 'changes_requested',
               review_note = NULLIF(d.after ->> 'reason', ''),
               reviewed_at = d.created_at,
               reviewed_by = (SELECT u.id FROM users u WHERE u.id = d.actor_id)
          FROM (SELECT DISTINCT ON (entity_id) entity_id, action, after, created_at, actor_id
                  FROM audit_log
                 WHERE entity_type = 'property'
                   AND action IN ('property.submit', 'property.approve',
                                  'property.reject', 'property.close')
                 ORDER BY entity_id, created_at DESC) d
         WHERE p.owner_id IS NOT NULL
           AND p.status = 'draft'
           AND p.review_outcome IS NULL
           AND d.entity_id = p.id::text
           AND d.action = 'property.reject';
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
