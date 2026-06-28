"""0016 phase15c — investor communications (developer updates + recipients).

Two tables, no enum changes:

* ``developer_updates`` — one row per "send" by a developer (owner role): the
  per-property update (subject/body) plus a ``recipient_count`` snapshot.
* ``developer_update_recipients`` — one row per investor the update fanned out to,
  linking the created in-app ``notification`` so read-count is REAL (notifications.read).
  UNIQUE(update_id, user_id) makes the fan-out idempotent per (update, user).

Reuses the Phase-12 notify()/email_outbox plumbing 1:1 — no new fan-out machinery.
Metrics are counts only (recipients + in-app reads); email open/click/delivered are
NOT tracked (no infra) and are intentionally absent.
"""

from __future__ import annotations

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE IF NOT EXISTS public.developer_updates (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id      UUID NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  created_by       UUID REFERENCES public.users(id) ON DELETE SET NULL,
  subject          TEXT NOT NULL,
  body             TEXT NOT NULL,
  recipient_count  INTEGER NOT NULL DEFAULT 0,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS developer_updates_property_created_idx
  ON public.developer_updates (property_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.developer_update_recipients (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  update_id        UUID NOT NULL REFERENCES public.developer_updates(id) ON DELETE CASCADE,
  user_id          UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  notification_id  UUID REFERENCES public.notifications(id) ON DELETE SET NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT developer_update_recipients_update_user_key UNIQUE (update_id, user_id)
);
CREATE INDEX IF NOT EXISTS developer_update_recipients_update_idx
  ON public.developer_update_recipients (update_id);
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS public.developer_update_recipients;
DROP TABLE IF EXISTS public.developer_updates;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
