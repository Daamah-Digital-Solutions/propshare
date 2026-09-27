"""0031 — broker leads: clients a broker invites, properties / projects a broker brings.

Client feedback: the broker's "Listings & Referrals" page must let the broker add a client,
a property and a project, and follow each one in a table — not only share a link.

  * ``kind``   — client | property | project.
  * ``status`` — client: invited -> joined (signed up through the broker's link) | cancelled;
                 property / project: new -> contacted -> listed | declined, or withdrawn by
                 the broker while still new.
  * ``name`` / ``email`` / ``phone`` — the client, or the property title and the owner /
    developer contact the broker is introducing.
  * ``details``   — the rest of what the broker entered (location, type, estimated value,
    expected completion, owner name, notes).
  * ``documents`` — [{label, key, filename, content_type}] in object storage (never public).
  * ``client_id`` — the account the invited client created (set when they join).
  * ``property_id`` — the listing staff created from a property / project lead.
  * ``admin_note`` / ``decided_by`` / ``decided_at`` — staff's last decision and message.

No money attaches to a lead: commissions still come only from referred clients (0012).
One pending invitation per broker and email. Additive and idempotent, raw SQL like 0029.
"""

from __future__ import annotations

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_leads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('client', 'property', 'project')),
            status TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            documents JSONB NOT NULL DEFAULT '[]'::jsonb,
            client_id UUID REFERENCES users(id) ON DELETE SET NULL,
            property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
            admin_note TEXT,
            decided_by UUID REFERENCES users(id) ON DELETE SET NULL,
            decided_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT broker_leads_status_check CHECK (
                (kind = 'client' AND status IN ('invited', 'joined', 'cancelled'))
                OR (kind IN ('property', 'project')
                    AND status IN ('new', 'contacted', 'listed', 'declined', 'withdrawn'))
            )
        );
        CREATE INDEX IF NOT EXISTS broker_leads_broker_idx
            ON broker_leads (broker_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS broker_leads_review_idx
            ON broker_leads (status, created_at DESC) WHERE kind IN ('property', 'project');
        CREATE UNIQUE INDEX IF NOT EXISTS broker_leads_one_pending_invite
            ON broker_leads (broker_id, lower(email)) WHERE kind = 'client' AND status = 'invited';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS broker_leads;")
