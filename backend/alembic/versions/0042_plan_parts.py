"""0042 — a part of a running installment plan changes hands.

Client (2026-11-08): an investor on an installment plan can sell or send part of it (one unit,
two, any number) on the secondary market, to a liquidity provider, or to another person; the
rest stays theirs. The part becomes a plan of its own in the new holder's name, with the same
dates and the same share of every payment (``installment_service.split_plan``).

  * ``installment_plans.parent_plan_id`` — the plan a part was taken from.
  * ``installment_plans.holder_since`` / ``entry_price`` — when the current holder took the
    plan (or the part) over and the price per unit they got in at. Empty for a plan its holder
    started (their price is the one it locked) and for plans taken over before 0042 (the
    secondary trade still tells).
  * ``lp_exit_requests.plan_id`` — an exit request for units of a running plan.
  * ``lp_positions.plan_id`` — the plan a liquidity provider took (a new part, or the whole).
  * ``transfers`` — asset ``plan``: ``plan_id`` the sender's plan, ``new_plan_id`` the plan the
    recipient got.

Additive; raw SQL like 0029-0041.
"""

from __future__ import annotations

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute("""
        ALTER TABLE installment_plans
            ADD COLUMN IF NOT EXISTS parent_plan_id UUID
                REFERENCES installment_plans(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS holder_since TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS entry_price NUMERIC(15, 2)
                CHECK (entry_price IS NULL OR entry_price >= 0);
        CREATE INDEX IF NOT EXISTS installment_plans_parent_idx
            ON installment_plans (parent_plan_id) WHERE parent_plan_id IS NOT NULL;

        ALTER TABLE lp_exit_requests
            ADD COLUMN IF NOT EXISTS plan_id UUID REFERENCES installment_plans(id);
        CREATE INDEX IF NOT EXISTS lp_exit_requests_open_plan_idx
            ON lp_exit_requests (plan_id) WHERE plan_id IS NOT NULL AND status = 'open';

        ALTER TABLE lp_positions
            ADD COLUMN IF NOT EXISTS plan_id UUID REFERENCES installment_plans(id);

        ALTER TABLE transfers
            ADD COLUMN IF NOT EXISTS plan_id UUID REFERENCES installment_plans(id),
            ADD COLUMN IF NOT EXISTS new_plan_id UUID REFERENCES installment_plans(id);
        ALTER TABLE transfers DROP CONSTRAINT IF EXISTS transfers_asset_check;
        ALTER TABLE transfers ADD CONSTRAINT transfers_asset_check
            CHECK (asset IN ('units', 'balance', 'plan'));
        ALTER TABLE transfers DROP CONSTRAINT IF EXISTS transfers_what_check;
        ALTER TABLE transfers ADD CONSTRAINT transfers_what_check CHECK (
            (asset = 'units' AND property_id IS NOT NULL AND units > 0)
            OR (asset = 'balance' AND units IS NULL AND amount > 0)
            OR (asset = 'plan' AND property_id IS NOT NULL AND plan_id IS NOT NULL AND units > 0)
        );
        """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM transfers WHERE asset = 'plan';
        ALTER TABLE transfers DROP CONSTRAINT IF EXISTS transfers_what_check;
        ALTER TABLE transfers ADD CONSTRAINT transfers_what_check CHECK (
            (asset = 'units' AND property_id IS NOT NULL AND units > 0)
            OR (asset = 'balance' AND units IS NULL AND amount > 0)
        );
        ALTER TABLE transfers DROP CONSTRAINT IF EXISTS transfers_asset_check;
        ALTER TABLE transfers ADD CONSTRAINT transfers_asset_check
            CHECK (asset IN ('units', 'balance'));
        ALTER TABLE transfers DROP COLUMN IF EXISTS new_plan_id, DROP COLUMN IF EXISTS plan_id;
        ALTER TABLE lp_positions DROP COLUMN IF EXISTS plan_id;
        DROP INDEX IF EXISTS lp_exit_requests_open_plan_idx;
        ALTER TABLE lp_exit_requests DROP COLUMN IF EXISTS plan_id;
        DROP INDEX IF EXISTS installment_plans_parent_idx;
        ALTER TABLE installment_plans
            DROP COLUMN IF EXISTS entry_price,
            DROP COLUMN IF EXISTS holder_since,
            DROP COLUMN IF EXISTS parent_plan_id;
        """)
