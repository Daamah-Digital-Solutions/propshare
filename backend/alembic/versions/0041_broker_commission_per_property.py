"""0041 — the broker's commission is a percentage of the investment, set per property.

Client (2026-10-28): the commission was "10% of the platform fee", the same on every property,
and too small to start the platform with brokers. It becomes a percentage of what the referred
client invests:

  * ``properties.broker_commission_pct`` — the rate of this property, set in the Listing Editor;
    empty means the general rate.
  * ``platform_settings.broker_commission_investment_pct`` — the general rate (the client's
    1.5%), set in Admin -> Platform Settings. It replaces ``broker_commission_pct``, which meant
    a percentage of the platform fee: that row is removed, never reinterpreted (10 would have
    become 10% of every investment).

Commissions already paid keep their rate and amount. Additive; raw SQL like 0029-0040.
"""

from __future__ import annotations

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute("""
        ALTER TABLE properties ADD COLUMN IF NOT EXISTS broker_commission_pct NUMERIC(6, 3)
            CHECK (broker_commission_pct IS NULL
                   OR (broker_commission_pct >= 0 AND broker_commission_pct <= 100))
        """)
    op.execute("DELETE FROM platform_settings WHERE key = 'broker_commission_pct'")
    op.execute(
        "INSERT INTO platform_settings (key, value, description) VALUES "
        "('broker_commission_investment_pct', '1.5', "
        "'Broker commission, percent of the investment, for a property without its own rate') "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM platform_settings WHERE key = 'broker_commission_investment_pct'")
    op.execute(
        "INSERT INTO platform_settings (key, value, description) VALUES "
        "('broker_commission_pct', '10.0', 'Broker commission, percent of the platform fee') "
        "ON CONFLICT (key) DO NOTHING"
    )
    op.execute("ALTER TABLE properties DROP COLUMN IF EXISTS broker_commission_pct")
