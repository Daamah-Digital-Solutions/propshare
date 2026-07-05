"""0020 group6 — installment plans (progressive-vesting, under-construction properties).

Owner decisions (recorded in DECISIONS.md):
  * **Progressive-vesting model** (owner-confirmed as licensed): the investor commits to a
    fixed unit allocation at today's locked ``unit_price`` and pays a down payment + N monthly
    installments. Ownership **vests proportionally** into ``ownership_ledger`` with each PAID
    payment; full ownership transfers at the final payment (handover). NAV appreciation is
    inherent (vested units are real ledger rows valued by the milestone value_index); rental
    yield is **excluded until handover** (distribution excludes vested units of active plans).
  * **Installment fee** (owner-accepted, admin-configurable): a fee on the down payment AND on
    each installment, at ``platform_settings.installment_fee_pct`` (default 4.0), SNAPSHOTTED
    onto the plan at creation so an admin rate change never rewrites existing schedules.

Tables:
  * installment_plans     — one commitment (investor + property; units_total at a locked price;
    down_payment_pct/duration; fee_rate + management_fee_rate snapshots; vested_units; status).
  * installment_payments  — the schedule rows (seq 0 = down payment; due_date, base/fee/total,
    vest_units, status scheduled|paid|overdue, paid_at, reminder_sent_at, idempotency_key).

No new enum: base principal reuses transaction_type 'investment', the fee reuses 'fee', and
vested units are ownership_ledger rows with reason 'installment_vest'. Reservation +
reconciliation account for a plan's not-yet-vested units (see reserved_units / reconciliation).
"""

from __future__ import annotations

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE IF NOT EXISTS public.installment_plans (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  investor_id          UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  property_id          UUID NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
  units_total          INTEGER NOT NULL,
  unit_price           NUMERIC(15,2) NOT NULL,          -- locked price at plan creation
  down_payment_pct     INTEGER NOT NULL,
  duration_months      INTEGER NOT NULL,                -- total payments (down + installments)
  fee_rate             NUMERIC(6,3) NOT NULL,           -- installment_fee_pct snapshot
  management_fee_rate  NUMERIC(6,3) NOT NULL,           -- stamped on vested ledger rows (Decision-2)
  vested_units         INTEGER NOT NULL DEFAULT 0,
  status               TEXT NOT NULL DEFAULT 'active',  -- active | completed
  idempotency_key      TEXT,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at         TIMESTAMPTZ,
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT installment_plans_units_check CHECK (units_total > 0),
  CONSTRAINT installment_plans_vested_check CHECK (vested_units >= 0 AND vested_units <= units_total)
);
CREATE UNIQUE INDEX IF NOT EXISTS installment_plans_idempotency_key_key
  ON public.installment_plans (idempotency_key);
CREATE INDEX IF NOT EXISTS installment_plans_investor_idx
  ON public.installment_plans (investor_id);
CREATE INDEX IF NOT EXISTS installment_plans_property_status_idx
  ON public.installment_plans (property_id, status);

CREATE TABLE IF NOT EXISTS public.installment_payments (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id           UUID NOT NULL REFERENCES public.installment_plans(id) ON DELETE CASCADE,
  seq               INTEGER NOT NULL,                    -- 0 = down payment
  kind              TEXT NOT NULL,                       -- downpayment | installment | final
  due_date          DATE NOT NULL,
  base_amount       NUMERIC(18,2) NOT NULL,              -- principal portion (locked price)
  fee_amount        NUMERIC(18,2) NOT NULL,              -- installment fee at the snapshot rate
  total_amount      NUMERIC(18,2) NOT NULL,              -- base + fee (what the wallet is charged)
  vest_units        INTEGER NOT NULL,                    -- units vested when this payment is paid
  status            TEXT NOT NULL DEFAULT 'scheduled',   -- scheduled | paid | overdue
  paid_at           TIMESTAMPTZ,
  reminder_sent_at  TIMESTAMPTZ,
  idempotency_key   TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT installment_payments_plan_seq_key UNIQUE (plan_id, seq)
);
CREATE UNIQUE INDEX IF NOT EXISTS installment_payments_idempotency_key_key
  ON public.installment_payments (idempotency_key);
CREATE INDEX IF NOT EXISTS installment_payments_due_idx
  ON public.installment_payments (status, due_date);
CREATE INDEX IF NOT EXISTS installment_payments_plan_idx
  ON public.installment_payments (plan_id);

INSERT INTO public.platform_settings (key, value, description) VALUES
  ('installment_fee_pct', '4.0',
   'Fee (percent) applied to the down payment and to EACH installment on the under-construction '
   'installment path. Owner-accepted, admin-configurable; snapshotted onto a plan at creation so '
   'a later rate change never rewrites existing schedules. Server-applied (client never computes).')
ON CONFLICT (key) DO NOTHING;
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS public.installment_payments;
DROP TABLE IF EXISTS public.installment_plans;
DELETE FROM public.platform_settings WHERE key = 'installment_fee_pct';
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
