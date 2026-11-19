"""0048 — the card waitlist.

Client (2026-11-19): the cards section reads "Coming soon · Join the Waitlist" instead of
offering to issue a card; a member who clicks it joins the waitlist with the card they want.
``card_waitlist`` keeps one row per member (joining again changes the card). Additive; raw SQL
like 0029-0047.
"""

from __future__ import annotations

from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute("""
        CREATE TABLE IF NOT EXISTS card_waitlist (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            card_type TEXT NOT NULL CHECK (card_type IN (
                'personal', 'family', 'team', 'developer', 'owner', 'broker', 'liquidity'
            )),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS card_waitlist")
