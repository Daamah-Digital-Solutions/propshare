"""0013 phase12 — notifications read path + email preferences + transactional outbox.

The in-app ``notifications`` table already exists (0001) and ``notify()`` has been
writing rows since Phase 2 — but write-only, with no read path. Phase 12 adds the read
path (API), per-user EMAIL preferences (in-app is always on; SMS/push are not offered),
and a transactional email OUTBOX so email is never sent inside a money transaction:

  * notifications gets a (user_id, read, created_at) index for the feed + unread count.
  * notification_preferences — per-user EMAIL category toggles (only channels we deliver).
  * email_outbox — a row is written ATOMICALLY with the in-app notification inside the
    money tx; a separate cron drainer (SKIP LOCKED, retry, idempotent) sends it OUT of
    any money tx (console locally, Resend live on the VPS).

No enum changes.
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


TABLES_UPGRADE = r"""
CREATE INDEX IF NOT EXISTS notifications_user_read_idx
  ON public.notifications (user_id, read, created_at DESC);

CREATE TABLE IF NOT EXISTS public.notification_preferences (
  user_id                   UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  email_investment_updates  BOOLEAN NOT NULL DEFAULT true,
  email_returns             BOOLEAN NOT NULL DEFAULT true,
  email_security_alerts     BOOLEAN NOT NULL DEFAULT true,
  email_new_properties      BOOLEAN NOT NULL DEFAULT true,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.email_outbox (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES public.users(id) ON DELETE SET NULL,  -- NULL for non-user invitees
  to_email    TEXT NOT NULL,
  subject     TEXT NOT NULL,
  body        TEXT NOT NULL,
  category    TEXT NOT NULL,                       -- investment_updates | returns | security | invite
  status      TEXT NOT NULL DEFAULT 'pending',     -- pending | sent | failed
  attempts    INTEGER NOT NULL DEFAULT 0,
  last_error  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  sent_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS email_outbox_status_idx ON public.email_outbox (status, created_at);
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS public.email_outbox;
DROP TABLE IF EXISTS public.notification_preferences;
DROP INDEX IF EXISTS public.notifications_user_read_idx;
"""


def upgrade() -> None:
    op.execute(TABLES_UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
