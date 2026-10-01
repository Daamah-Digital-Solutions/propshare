"""0033 — pictures and files in the assistant chat, and changing the account's email address.

Client feedback on the assistant (meeting 2026-10-01): a user wants to send a screenshot or a
file (a receipt, a statement, a contract) about a problem, and to change their email from the
chat instead of being sent to a page.

  * ``assistant_attachments`` — a picture or a file a signed-in user attaches to a chat message
    (``kind`` image | file). Stored like the messages themselves: the bytes are AES-GCM
    ciphertext (the key id is in the blob and in ``enc_key_id``); a picture is re-encoded on
    upload so no metadata survives; a file is kept as sent (PDF, Word, Excel, PowerPoint, CSV or
    text, recognised by its content). Deleted with the conversation (retention purge) or the
    message.
  * ``email_change_requests`` — a change of the sign-in address. It is approved from the
    CURRENT address first (so a session left open on someone else's device cannot take the
    account over), then the NEW address is confirmed by its own link; only then does
    ``users.email`` change. Only the hashes of the two one-time tokens are stored.

Additive (two new tables); raw SQL like 0029-0032.
"""

from __future__ import annotations

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS assistant_attachments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL
                REFERENCES assistant_conversations(id) ON DELETE CASCADE,
            message_id UUID REFERENCES assistant_messages(id) ON DELETE CASCADE,
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('image', 'file')),
            filename TEXT NOT NULL,
            mime TEXT NOT NULL CHECK (mime IN (
                'image/png', 'image/jpeg', 'image/webp', 'application/pdf',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                'text/csv', 'text/plain'
            )),
            size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
            -- pictures: their size; PDFs: their page count
            width INTEGER CHECK (width > 0),
            height INTEGER CHECK (height > 0),
            pages INTEGER CHECK (pages > 0),
            -- the AI provider refused it: it is never sent to the model again
            unreadable BOOLEAN NOT NULL DEFAULT false,
            data_enc BYTEA NOT NULL,
            enc_key_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS assistant_attachments_conversation_idx
            ON assistant_attachments (conversation_id, created_at);
        CREATE INDEX IF NOT EXISTS assistant_attachments_message_idx
            ON assistant_attachments (message_id) WHERE message_id IS NOT NULL;

        CREATE TABLE IF NOT EXISTS email_change_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            old_email TEXT NOT NULL,
            new_email TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'awaiting_approval' CHECK (status IN (
                'awaiting_approval', 'awaiting_confirmation', 'completed', 'cancelled',
                'expired'
            )),
            approve_token_hash TEXT UNIQUE,
            confirm_token_hash TEXT UNIQUE,
            source TEXT NOT NULL DEFAULT 'settings' CHECK (source IN ('settings', 'assistant')),
            expires_at TIMESTAMPTZ NOT NULL,
            approved_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS email_change_requests_user_idx
            ON email_change_requests (user_id, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS email_change_requests;
        DROP TABLE IF EXISTS assistant_attachments;
        """
    )
