"""0036 — a closed account, and the wallet share of a beneficiary.

Decided for the open points of 0035 (2026-10-11):

  * ``users.closed_at`` / ``closed_reason`` / ``closed_by`` — a closed account cannot sign in
    or act, and nothing it holds is touched. Staff close and reopen an account; an approved
    claim about a holder's death, or about a holder who can no longer manage the account,
    closes the holder's, so that what remains in it waits for the other claims whoever knows
    its password. (``closed_by`` has no foreign key: the record of who closed an account must
    survive that staff account.)
  * ``estate_transfers.amount`` — a beneficiary's share of the holder's wallet balance, when
    their record covers the wallet. A row with an amount is a money share (no property, no
    units); it waits and is paid exactly like a share of units.
  * ``estate_events.wallet_base`` — the balance the percentages were applied to on the day
    of the event (the holder's balance less what they still owed relatives).
  * ``transaction_type`` gains ``estate_transfer``: the two wallet ledger rows of such a
    share. Added here and first used at runtime later (a new enum value cannot be used in
    the transaction that adds it).

Additive; raw SQL like 0029-0035.
"""

from __future__ import annotations

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute("ALTER TYPE public.transaction_type ADD VALUE IF NOT EXISTS 'estate_transfer'")
    op.execute(
        """
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS closed_reason TEXT,
            ADD COLUMN IF NOT EXISTS closed_by UUID;

        ALTER TABLE estate_transfers ADD COLUMN IF NOT EXISTS amount NUMERIC(15, 2);
        ALTER TABLE estate_events ADD COLUMN IF NOT EXISTS wallet_base NUMERIC(15, 2);
        """
    )


def downgrade() -> None:
    # the enum value stays: PostgreSQL cannot drop one, and nothing reads it by position
    op.execute(
        """
        ALTER TABLE estate_events DROP COLUMN IF EXISTS wallet_base;
        ALTER TABLE estate_transfers DROP COLUMN IF EXISTS amount;
        ALTER TABLE users
            DROP COLUMN IF EXISTS closed_by,
            DROP COLUMN IF EXISTS closed_reason,
            DROP COLUMN IF EXISTS closed_at;
        """
    )
