"""0045 — new trading and liquidity fees, with a share for the liquidity provider.

Client (2026-11-18, "Capimax Market Fees", PropShare): fees that encourage liquidity providers
to buy units from investors and put them back on the market. All rates are of the value of
the units sold:

  deal                                   seller   buyer   platform   liquidity provider
  ordinary secondary-market sale          0.5%     1.5%     2%         —
  a provider buys through the LP market   1.5%     0%       1%         0.5% (of the seller fee)
  a provider resells those units          0%       1.5%     1%         0.5% (of the buyer fee)

  * ``platform_settings``: ``secondary_seller_fee_pct`` (0.5) and ``lp_fee_share_pct`` (0.5)
    are added; ``secondary_resale_fee_pct`` (the buyer's fee) goes from 1.0 to 1.5 and
    ``liquidity_fee_pct`` (the seller's fee in the LP market) from 2.0 to 1.5, and
    ``liquidity_discount_pct`` from 3.0 to 0 (the provider pays the units' value; owner,
    2026-11-18) — only where they still hold the old defaults: a rate the team changed is kept.
  * ``secondary_listings.lp_units``: how many of a listing's units the provider bought through
    the LP market (they sell under the provider's rules, first).
  * ``secondary_trades``: ``seller_fee``, ``lp_units`` and ``lp_fee_share`` per trade.
  * ``lp_positions``: ``liquidity_fee`` (the seller's fee of this fill) and ``lp_fee_share``.
  * ``transaction_type`` gains ``lp_fee_share``: the provider's share, credited to its wallet
    once per completed deal, in the same transaction as the deal.

Existing trades keep zeros. Additive; raw SQL like 0029-0044.
"""

from __future__ import annotations

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # a new enum value is committed on its own before anything uses it
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE public.transaction_type ADD VALUE IF NOT EXISTS 'lp_fee_share'")
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute("ALTER TABLE secondary_listings ADD COLUMN IF NOT EXISTS lp_units INTEGER NOT NULL DEFAULT 0")
    op.execute("""
        ALTER TABLE secondary_trades
          ADD COLUMN IF NOT EXISTS seller_fee NUMERIC(15, 2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS lp_units INTEGER NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS lp_fee_share NUMERIC(15, 2) NOT NULL DEFAULT 0
    """)
    op.execute("""
        ALTER TABLE lp_positions
          ADD COLUMN IF NOT EXISTS liquidity_fee NUMERIC(15, 2) NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS lp_fee_share NUMERIC(15, 2) NOT NULL DEFAULT 0
    """)
    op.execute("""
        INSERT INTO platform_settings (key, value, description) VALUES
          ('secondary_seller_fee_pct', '0.5',
           'Secondary-market seller fee (percent of the sale), taken from what an ordinary seller '
           'receives. A liquidity provider reselling units it bought through the LP market pays none.'),
          ('lp_fee_share_pct', '0.5',
           'The liquidity provider''s share (percent of the deal) of the fees of its deals: of the '
           'seller''s fee when it buys through the LP market, and of the buyer''s fee when it resells '
           'those units on the secondary market. Credited to its wallet once per completed deal.')
        ON CONFLICT (key) DO NOTHING
    """)
    op.execute("""
        UPDATE platform_settings SET value = '1.5',
          description = 'Secondary-market buyer fee (percent of the sale), charged on top of the price.'
        WHERE key = 'secondary_resale_fee_pct' AND value IN ('1', '1.0', '1.00')
    """)
    op.execute("""
        UPDATE platform_settings SET description =
          'Secondary-market buyer fee (percent of the sale), charged on top of the price.'
        WHERE key = 'secondary_resale_fee_pct'
    """)
    op.execute("""
        UPDATE platform_settings SET value = '1.5'
        WHERE key = 'liquidity_fee_pct' AND value IN ('2', '2.0', '2.00')
    """)
    # the provider pays the value of the units (owner, 2026-11-18): no discount any more
    op.execute("""
        UPDATE platform_settings SET value = '0'
        WHERE key = 'liquidity_discount_pct' AND value IN ('3', '3.0', '3.00')
    """)
    op.execute("""
        UPDATE platform_settings SET description =
          'Seller fee (percent of the deal) when a liquidity provider buys units through the LP '
          'market; the provider pays no purchase fee and gets lp_fee_share_pct of the deal from it.'
        WHERE key = 'liquidity_fee_pct'
    """)


def downgrade() -> None:
    op.execute("DELETE FROM platform_settings WHERE key IN ('secondary_seller_fee_pct', 'lp_fee_share_pct')")
    op.execute("ALTER TABLE lp_positions DROP COLUMN IF EXISTS lp_fee_share, DROP COLUMN IF EXISTS liquidity_fee")
    op.execute(
        "ALTER TABLE secondary_trades DROP COLUMN IF EXISTS lp_fee_share, "
        "DROP COLUMN IF EXISTS lp_units, DROP COLUMN IF EXISTS seller_fee"
    )
    op.execute("ALTER TABLE secondary_listings DROP COLUMN IF EXISTS lp_units")
    # an enum value cannot be dropped; 'lp_fee_share' stays unused
