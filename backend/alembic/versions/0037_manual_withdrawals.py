"""0037 — manual withdrawals beside the automatic ones.

Owner's brief (2026-10-20): an investor asks for a withdrawal, the team pays it by hand (bank or
crypto wallet) and closes it in the admin panel; the automatic Stripe payouts stay as they are,
on the same table.

  * ``withdrawals.reference`` — the request's number the investor and the team quote,
    ``WD-`` and ten characters. Existing rows get one from their id.
  * ``withdrawals.destination_label`` — the destination as text when it was asked for
    ("CIB · ****4321"), so the request still says where to pay after the saved account is
    deleted. Existing rows get one from their destination snapshot.
  * ``withdrawals.transfer_reference`` — the bank transfer number or crypto transaction hash
    the team enters when it marks a request paid.
  * one refund per withdrawal: a withdrawal's hold can be reversed into the wallet once only,
    whatever presses the button (a unique index on the reversal row, keyed by the withdrawal).
  * a paid withdrawal's hold row reads ``completed``, a refunded one's ``returned`` (both read
    ``pending`` for ever, so statements showed them "in progress").

Additive; raw SQL like 0029-0036.
"""

from __future__ import annotations

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute(
        """
        ALTER TABLE withdrawals
            ADD COLUMN IF NOT EXISTS reference TEXT,
            ADD COLUMN IF NOT EXISTS destination_label TEXT,
            ADD COLUMN IF NOT EXISTS transfer_reference TEXT
        """
    )
    op.execute(
        """
        UPDATE withdrawals
           SET reference = 'WD-' || upper(substr(replace(id::text, '-', ''), 1, 10))
         WHERE reference IS NULL
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS withdrawals_reference_key ON withdrawals (reference)"
    )
    op.execute(
        """
        UPDATE withdrawals
           SET destination_label = CASE
                 WHEN destination ? 'connect_account_id' THEN 'Bank linked through Stripe'
                 WHEN destination->>'type' = 'bank' THEN
                      coalesce(nullif(destination->>'bank_name', ''), 'Bank')
                      || ' · ****' || right(replace(coalesce(nullif(destination->>'iban', ''),
                                                             destination->>'account_number', ''),
                                                    ' ', ''), 4)
                 WHEN destination ? 'address' THEN
                      coalesce(nullif(destination->>'network', ''), 'Crypto')
                      || ' · ****' || right(destination->>'address', 4)
                 ELSE NULL
               END
         WHERE destination_label IS NULL
        """
    )
    # A withdrawal reversed into the wallet twice would be money out of nowhere: stop here
    # rather than build the index on top of it.
    op.execute(
        """
        DO $$
        DECLARE twice integer;
        BEGIN
            SELECT count(*) INTO twice FROM (
                SELECT reference_id FROM transactions
                 WHERE type = 'withdrawal' AND status = 'reversed' AND reference_id IS NOT NULL
                 GROUP BY reference_id HAVING count(*) > 1) d;
            IF twice > 0 THEN
                RAISE EXCEPTION '% withdrawal(s) were refunded twice: fix them first', twice;
            END IF;
        END $$
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS transactions_withdrawal_refund_once
            ON transactions (reference_id)
         WHERE type = 'withdrawal' AND status = 'reversed'
        """
    )
    op.execute(
        """
        UPDATE transactions t
           SET status = 'completed'
          FROM withdrawals w
         WHERE t.reference_id = w.id AND t.type = 'withdrawal' AND t.status = 'pending'
           AND t.amount < 0 AND w.status = 'completed'
        """
    )
    op.execute(
        """
        UPDATE transactions t
           SET status = 'returned'
         WHERE t.type = 'withdrawal' AND t.status = 'pending' AND t.amount < 0
           AND EXISTS (SELECT 1 FROM transactions r
                        WHERE r.reference_id = t.reference_id AND r.type = 'withdrawal'
                          AND r.status = 'reversed')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS transactions_withdrawal_refund_once")
    op.execute("DROP INDEX IF EXISTS withdrawals_reference_key")
    op.execute(
        """
        ALTER TABLE withdrawals
            DROP COLUMN IF EXISTS transfer_reference,
            DROP COLUMN IF EXISTS destination_label,
            DROP COLUMN IF EXISTS reference
        """
    )
