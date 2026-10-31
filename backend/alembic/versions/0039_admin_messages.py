"""0039 — messages from the platform team to users (admin panel), as on Capimax BRX.

Client (2026-10-28): the team writes to one user or to everyone holding a role (investors,
property owners / developers, brokers, liquidity providers, everyone) from the admin panel.
Each recipient gets the message in their inbox (/messages), an in-app notification, and an
email through the existing outbox.

  * ``message_templates`` — saved subjects and bodies the team reuses.
  * ``message_broadcasts`` — one row per message sent: audience, the one user (for a direct
    message), subject, body, whether it was emailed, who sent it, how many it reached.
    ``client_token`` is unique: a refreshed or double-clicked Send never sends twice.
  * ``platform_messages`` — one row per recipient (their inbox), with when they read it and
    what happened to the email: queued (the outbox row it links to says sent or failed),
    ``opted_out`` (they turned announcement emails off), ``no_email`` (not emailed).
  * ``notification_preferences.email_announcements`` — the member's switch for emails of
    messages sent to a whole group. A message to one user is always emailed.

Additive; raw SQL like 0029-0038.
"""

from __future__ import annotations

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute("""
        CREATE TABLE IF NOT EXISTS message_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS message_templates_name_key "
        "ON message_templates (lower(name))"
    )
    op.execute("""
        CREATE TABLE IF NOT EXISTS message_broadcasts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            audience TEXT NOT NULL CHECK (audience IN
                ('user', 'investors', 'owners', 'brokers', 'liquidity_providers', 'staff',
                 'everyone')),
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            send_email BOOLEAN NOT NULL DEFAULT true,
            template_id UUID REFERENCES message_templates(id) ON DELETE SET NULL,
            client_token TEXT NOT NULL,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            recipients INTEGER NOT NULL DEFAULT 0,
            emails_queued INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS message_broadcasts_client_token_key "
        "ON message_broadcasts (client_token)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS message_broadcasts_created "
        "ON message_broadcasts (created_at DESC)"
    )
    op.execute("""
        CREATE TABLE IF NOT EXISTS platform_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            recipient_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            broadcast_id UUID REFERENCES message_broadcasts(id) ON DELETE SET NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            read_at TIMESTAMPTZ,
            email_status TEXT NOT NULL DEFAULT 'no_email'
                CHECK (email_status IN ('queued', 'opted_out', 'no_email')),
            email_outbox_id UUID REFERENCES email_outbox(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS platform_messages_inbox "
        "ON platform_messages (recipient_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS platform_messages_unread "
        "ON platform_messages (recipient_id) WHERE read_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS platform_messages_broadcast "
        "ON platform_messages (broadcast_id)"
    )
    op.execute(
        "ALTER TABLE notification_preferences "
        "ADD COLUMN IF NOT EXISTS email_announcements BOOLEAN NOT NULL DEFAULT true"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE notification_preferences DROP COLUMN IF EXISTS email_announcements")
    op.execute("DROP TABLE IF EXISTS platform_messages")
    op.execute("DROP TABLE IF EXISTS message_broadcasts")
    op.execute("DROP TABLE IF EXISTS message_templates")
