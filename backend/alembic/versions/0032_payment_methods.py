"""0032 — the same payment methods on every property: installment down payments by card,
crypto or Pronova, and Nova Sukuk certificates.

Client feedback: every property must offer the same methods — wallet, card / Apple Pay /
Google Pay, crypto, Pronova and Nova Sukuk. A ready property took card, crypto and Pronova;
an off-plan one took only the wallet.

  * ``installment_plans`` — how the down payment is paid (``payment_method``), the hosted
    checkout behind it (``payment_id``), how long the plan's units stay held while that
    checkout is open (``reservation_expires_at``), the Pronova discount on the down payment
    (``discount_amount``), and why a plan ended before it started (``failure_reason``,
    ``cancelled_at``). New statuses: pending_payment (checkout open), pending_review (a Nova
    certificate with staff), cancelled | expired (never started; its units are back on sale).
  * ``payments.related_plan_id`` — the plan a down-payment checkout pays for
    (purpose 'installment').
  * ``sukuk_certificates`` — a Nova Sukuk certificate an investor submits to pay for a
    purchase (``investment_id``) or a down payment (``plan_id``): the PDF in object storage,
    what it states (number, issuer, value, validity), what it must cover (``amount_due``) and
    staff's decision. Approved = the units are the investor's and stay pledged to Nova Finance
    (not sellable or transferable) until staff release the pledge (``released``).
  * ``wallets.total_invested`` — a purchase paid by card, crypto or Pronova never counted toward
    the buyer's invested cost basis (only wallet purchases did), so the portfolio showed its
    units' value as a gain. The code counts them from now on; this adds the ones confirmed
    before, and the downgrade takes them out again (the previous code does not count them),
    so a downgrade and upgrade never count one twice.

Additive (new columns, one new table) plus that one correction; raw SQL like 0029-0031.
"""

from __future__ import annotations

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE installment_plans
            ADD COLUMN IF NOT EXISTS payment_method TEXT,
            ADD COLUMN IF NOT EXISTS payment_id UUID,
            ADD COLUMN IF NOT EXISTS reservation_expires_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(15, 2) NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS failure_reason TEXT,
            ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;
        CREATE INDEX IF NOT EXISTS installment_plans_pending_payment_idx
            ON installment_plans (reservation_expires_at) WHERE status = 'pending_payment';

        ALTER TABLE payments
            ADD COLUMN IF NOT EXISTS related_plan_id UUID
                REFERENCES installment_plans(id) ON DELETE SET NULL;

        CREATE TABLE IF NOT EXISTS sukuk_certificates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            investment_id UUID REFERENCES investments(id) ON DELETE CASCADE,
            plan_id UUID REFERENCES installment_plans(id) ON DELETE CASCADE,
            units INTEGER NOT NULL CHECK (units >= 0),
            amount_due NUMERIC(15, 2) NOT NULL CHECK (amount_due > 0),
            certificate_no TEXT,
            issuer TEXT,
            certificate_value NUMERIC(15, 2),
            valid_until DATE,
            file_key TEXT NOT NULL,
            file_name TEXT NOT NULL,
            content_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected', 'released')),
            review_note TEXT,
            reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at TIMESTAMPTZ,
            released_by UUID REFERENCES users(id) ON DELETE SET NULL,
            released_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT sukuk_certificates_one_target
                CHECK ((investment_id IS NULL) <> (plan_id IS NULL))
        );
        CREATE INDEX IF NOT EXISTS sukuk_certificates_review_idx
            ON sukuk_certificates (status, created_at DESC);
        CREATE INDEX IF NOT EXISTS sukuk_certificates_pledge_idx
            ON sukuk_certificates (user_id, property_id) WHERE status = 'approved';
        CREATE UNIQUE INDEX IF NOT EXISTS sukuk_certificates_investment_key
            ON sukuk_certificates (investment_id) WHERE investment_id IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS sukuk_certificates_plan_key
            ON sukuk_certificates (plan_id) WHERE plan_id IS NOT NULL;

        UPDATE wallets w
           SET total_invested = w.total_invested + paid.amount
          FROM (SELECT user_id, SUM(amount) AS amount
                  FROM investments
                 WHERE status = 'confirmed' AND confirmed_via IN ('card', 'crypto', 'pronova')
                 GROUP BY user_id) paid
         WHERE paid.user_id = w.user_id;
        """
    )


def downgrade() -> None:
    # The previous code knows neither a plan waiting for its down payment / a Nova review nor a
    # pledge: it would credit a paid down payment to the wallet and keep the plan's units, and
    # let pledged units be sold. Refuse until none is left.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM installment_plans
                        WHERE status IN ('pending_payment', 'pending_review'))
               OR EXISTS (SELECT 1 FROM sukuk_certificates
                           WHERE status IN ('pending', 'approved')) THEN
                RAISE EXCEPTION '0032 downgrade refused: installment plans are waiting for a '
                    'down payment or a Nova review, or Nova certificates are pending or '
                    'pledged. Settle them first.';
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        UPDATE wallets w
           SET total_invested = GREATEST(w.total_invested - paid.amount, 0)
          FROM (SELECT user_id, SUM(amount) AS amount
                  FROM investments
                 WHERE status = 'confirmed' AND confirmed_via IN ('card', 'crypto', 'pronova')
                 GROUP BY user_id) paid
         WHERE paid.user_id = w.user_id;

        DROP TABLE IF EXISTS sukuk_certificates;
        ALTER TABLE payments DROP COLUMN IF EXISTS related_plan_id;
        DROP INDEX IF EXISTS installment_plans_pending_payment_idx;
        ALTER TABLE installment_plans
            DROP COLUMN IF EXISTS cancelled_at,
            DROP COLUMN IF EXISTS failure_reason,
            DROP COLUMN IF EXISTS discount_amount,
            DROP COLUMN IF EXISTS reservation_expires_at,
            DROP COLUMN IF EXISTS payment_id,
            DROP COLUMN IF EXISTS payment_method;
        """
    )
