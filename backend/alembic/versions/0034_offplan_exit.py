"""0034 — exit for properties under construction: a unit price that moves, and selling a
position that is still on its installment plan.

Client (meeting 2026-10-01): a holder of an under-construction property must be able to exit
at any time, "the feature we compete with". The platform gives every such property a new
price each month (and at each sales phase); a fully paid unit sells at it like a ready one;
a position on an installment plan sells as a whole: the buyer pays the seller what was paid
plus the increase on the whole position, and carries on with the remaining installments.

  * ``property_prices`` — the history of a listing's unit price after launch. Append-only:
    one row per change (the price before it, the new price, an optional phase name and note,
    who recorded it). ``properties.unit_price`` stays the current price everything reads.
  * ``properties.offplan_payment`` — how an under-construction listing is bought:
    ``installments`` (the plan, as until now), ``full`` (paid in full at the phase's price) or
    ``both``. Ready listings ignore it.
  * ``properties.launch_price`` — the price the listing was launched at, written at its first
    price change (NULL until then), so a listing says how far its price has moved without a
    second query.
  * ``secondary_listings.plan_id`` — the listing offers a whole installment plan position
    (one active listing per plan).
  * ``secondary_trades.plan_id`` + the position's figures at the trade (its value, what had
    been paid, the principal and fees the buyer took over), so the sale can always be read
    back exactly as it happened.

Additive; raw SQL like 0029-0033.
"""

from __future__ import annotations

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # every statement here is quick, but each needs the table for an instant: if a long
    # transaction holds one, fail (nothing changed) instead of queueing the whole site behind it
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS property_prices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            previous_price NUMERIC(15, 2) NOT NULL CHECK (previous_price > 0),
            price NUMERIC(15, 2) NOT NULL CHECK (price > 0),
            -- a sales phase or stage this price opens ("Phase 2"), when it is one
            label TEXT,
            note TEXT,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (price <> previous_price)
        );
        CREATE INDEX IF NOT EXISTS property_prices_property_idx
            ON property_prices (property_id, created_at);

        ALTER TABLE properties
            ADD COLUMN IF NOT EXISTS offplan_payment TEXT NOT NULL DEFAULT 'installments',
            ADD COLUMN IF NOT EXISTS launch_price NUMERIC(15, 2)
                CHECK (launch_price IS NULL OR launch_price > 0);
        -- a database that already has price history (a re-run): its first recorded price
        UPDATE properties p SET launch_price = first.previous_price
          FROM (
            SELECT DISTINCT ON (property_id) property_id, previous_price
              FROM property_prices ORDER BY property_id, created_at, id
          ) AS first
         WHERE first.property_id = p.id AND p.launch_price IS NULL;
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'properties_offplan_payment_check'
          ) THEN
            ALTER TABLE properties ADD CONSTRAINT properties_offplan_payment_check
              CHECK (offplan_payment IN ('installments', 'full', 'both'));
          END IF;
        END $$;

        ALTER TABLE secondary_listings
            ADD COLUMN IF NOT EXISTS plan_id UUID
                REFERENCES installment_plans(id) ON DELETE CASCADE;
        CREATE UNIQUE INDEX IF NOT EXISTS secondary_listings_active_plan_key
            ON secondary_listings (plan_id) WHERE plan_id IS NOT NULL AND status = 'active';

        ALTER TABLE secondary_trades
            ADD COLUMN IF NOT EXISTS plan_id UUID
                REFERENCES installment_plans(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS position_value NUMERIC(15, 2),
            ADD COLUMN IF NOT EXISTS paid_principal NUMERIC(15, 2),
            ADD COLUMN IF NOT EXISTS assumed_principal NUMERIC(15, 2),
            ADD COLUMN IF NOT EXISTS assumed_fees NUMERIC(15, 2);
        CREATE INDEX IF NOT EXISTS secondary_trades_plan_idx
            ON secondary_trades (plan_id, created_at) WHERE plan_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        -- A position listing is not a listing of loose units: without plan_id the code before
        -- 0034 would sell every unit of the plan, paid for or not. Close them first.
        UPDATE secondary_listings SET status = 'cancelled', cancelled_at = now()
         WHERE plan_id IS NOT NULL AND status = 'active';
        DROP INDEX IF EXISTS secondary_trades_plan_idx;
        ALTER TABLE secondary_trades
            DROP COLUMN IF EXISTS assumed_fees,
            DROP COLUMN IF EXISTS assumed_principal,
            DROP COLUMN IF EXISTS paid_principal,
            DROP COLUMN IF EXISTS position_value,
            DROP COLUMN IF EXISTS plan_id;
        DROP INDEX IF EXISTS secondary_listings_active_plan_key;
        ALTER TABLE secondary_listings DROP COLUMN IF EXISTS plan_id;
        ALTER TABLE properties DROP CONSTRAINT IF EXISTS properties_offplan_payment_check;
        ALTER TABLE properties DROP COLUMN IF EXISTS offplan_payment;
        ALTER TABLE properties DROP COLUMN IF EXISTS launch_price;
        DROP TABLE IF EXISTS property_prices;
        """
    )
