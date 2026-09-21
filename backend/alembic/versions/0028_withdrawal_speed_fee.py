"""0028 — withdrawal speed + fee (Stripe Instant Payouts).

The owner enabled instant bank withdrawals for US investors: the money reaches the
investor's debit card in minutes instead of 1-2 business days. Stripe charges the platform
1% per instant payout, so a withdrawal now records which speed the customer chose and the
fee that was taken out of it.

  * ``speed`` — ``standard`` (default, existing behaviour) or ``instant``.
  * ``fee``   — deducted from the requested amount; the customer receives ``amount - fee``.
    The wallet is still debited the full ``amount`` once at hold time, so
    ``balance == SUM(ledger)`` is untouched; this column is what statements and the admin
    queue show.

Additive and idempotent, raw SQL like 0023/0026/0027.
"""

from __future__ import annotations

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE withdrawals
            ADD COLUMN IF NOT EXISTS speed TEXT NOT NULL DEFAULT 'standard',
            ADD COLUMN IF NOT EXISTS fee NUMERIC(15,2) NOT NULL DEFAULT 0;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'withdrawals_speed_check'
            ) THEN
                ALTER TABLE withdrawals
                    ADD CONSTRAINT withdrawals_speed_check
                    CHECK (speed IN ('standard','instant'));
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'withdrawals_fee_check'
            ) THEN
                ALTER TABLE withdrawals
                    ADD CONSTRAINT withdrawals_fee_check
                    CHECK (fee >= 0 AND fee < amount + 1);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE withdrawals
            DROP CONSTRAINT IF EXISTS withdrawals_speed_check,
            DROP CONSTRAINT IF EXISTS withdrawals_fee_check,
            DROP COLUMN IF EXISTS speed,
            DROP COLUMN IF EXISTS fee;
        """
    )
