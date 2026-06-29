"""0019 group5 — inter-vivos gifting (scheduled + recurring gifts, real on the date).

Owner decision: *follow the frontend and make it real.* The original mock was a SCHEDULED
+ recurring gift (recipient, occasion, asset, amount/units, scheduled date, yearly
recurrence, "executes automatically", "7-day reminder"). This builds the REAL scheduling
that backs every promise — no fake auto-execute, no fake reminder.

  * scheduled_gifts — a holder schedules a future transfer of property-share UNITS (zero
    price, reservation held via the shared reserved_units rule) or WALLET cash (escrowed
    at schedule via a real wallet debit). A cron (POST /admin/gifts/run-due) sends the
    7-day reminder, then on the date executes via the family atomic-transfer engine
    (REAL recipient) or leaves a PENDING row that materializes on the recipient's KYC.
    Recurring gifts re-enqueue the next single occurrence (UNIQUE(series_id, scheduled_for)).
  * transaction_type += 'gift' — the wallet escrow / credit / refund ledger entries.
  * platform_settings += gift_fee_pct (default 0 — a gift isn't a sale; admin-editable).

Asset scope: property_shares + wallet are REAL; passive_income / rental_returns /
tokenized / allocation are honest-disabled in the UI (no real backing — tokenization is
the separate BRX project, not PropShare), never reaching this table (CHECK).
"""

from __future__ import annotations

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


# Added here; first USED at runtime later (PG "no new enum value in same tx" is moot).
ENUM_GIFT = "ALTER TYPE public.transaction_type ADD VALUE IF NOT EXISTS 'gift';"

UPGRADE = r"""
CREATE TABLE IF NOT EXISTS public.scheduled_gifts (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  giver_id           UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  recipient_user_id  UUID REFERENCES public.users(id) ON DELETE SET NULL,
  recipient_email    TEXT,
  recipient_name     TEXT NOT NULL,
  asset_type         TEXT NOT NULL,                 -- property_shares | wallet
  property_id        UUID REFERENCES public.properties(id) ON DELETE SET NULL,
  units              INTEGER,                        -- property_shares gifts
  amount             NUMERIC(18,2),                  -- wallet gifts (escrowed at schedule)
  occasion           TEXT,                           -- display only
  message            TEXT,                           -- personal note
  scheduled_for      DATE NOT NULL,                  -- execution date
  recurring          BOOLEAN NOT NULL DEFAULT false, -- yearly
  recurrence_end     DATE,                           -- optional series end
  series_id          UUID NOT NULL,                  -- groups a recurring chain (first row = own id)
  status             TEXT NOT NULL DEFAULT 'scheduled', -- scheduled|pending|executed|cancelled|failed
  failure_reason     TEXT,                           -- real reason on 'failed' (never silent-drop)
  reminder_sent_at   TIMESTAMPTZ,                    -- 7-day reminder idempotency
  idempotency_key    TEXT,
  executed_at        TIMESTAMPTZ,
  materialized_at    TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT scheduled_gifts_asset_check
    CHECK (asset_type IN ('property_shares','wallet')),
  CONSTRAINT scheduled_gifts_amount_check
    CHECK ((units IS NOT NULL AND units > 0) OR (amount IS NOT NULL AND amount > 0))
);
CREATE UNIQUE INDEX IF NOT EXISTS scheduled_gifts_idempotency_key_key
  ON public.scheduled_gifts (idempotency_key);
-- Recurrence idempotency: a re-run can never insert a duplicate next occurrence.
CREATE UNIQUE INDEX IF NOT EXISTS scheduled_gifts_series_date_key
  ON public.scheduled_gifts (series_id, scheduled_for);
CREATE INDEX IF NOT EXISTS scheduled_gifts_giver_idx
  ON public.scheduled_gifts (giver_id);
-- The cron's hot path: due 'scheduled' rows by date (executions + reminders).
CREATE INDEX IF NOT EXISTS scheduled_gifts_due_idx
  ON public.scheduled_gifts (status, scheduled_for);
-- Reservation invariant: scheduled/pending property gifts OUT, per giver+property.
CREATE INDEX IF NOT EXISTS scheduled_gifts_reserve_idx
  ON public.scheduled_gifts (giver_id, property_id, status);
-- Materialization: pending gifts for a recipient (by user or pending email).
CREATE INDEX IF NOT EXISTS scheduled_gifts_recipient_idx
  ON public.scheduled_gifts (recipient_user_id, status);
CREATE INDEX IF NOT EXISTS scheduled_gifts_recipient_email_idx
  ON public.scheduled_gifts (lower(recipient_email));

INSERT INTO public.platform_settings (key, value, description) VALUES
  ('gift_fee_pct', '0',
   'Fee on an inter-vivos gift (percent of the gifted value). Default 0 — a gift is not '
   'a sale (mirrors family_transfer_fee_pct). Admin-editable; charged to the giver at '
   'execution when > 0.')
ON CONFLICT (key) DO NOTHING;
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS public.scheduled_gifts;
DELETE FROM public.platform_settings WHERE key = 'gift_fee_pct';
-- enum value 'gift' remains (Postgres can't drop it); harmless.
"""


def upgrade() -> None:
    op.execute(ENUM_GIFT)
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
