"""0014 phase14 — reinvest discount setting (real, admin-configurable, server-applied).

The investor "reinvest your returns" path now applies a GENUINE discount server-side
(the 2nd narrow D5 exception, alongside the family reinvest subsidy): the user buys units
at an effective price = unit_price × (1 − reinvest_discount_pct/100). The rate is an
admin-editable platform_settings value (NOT a code literal); the engine honors it and the
client never computes the final price.

Schema: seed the platform_settings key only (no tables; the reinvest path reuses the
ownership_ledger + wallet like the family reinvest). Mirrors settings_service.DEFAULTS.
"""

from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


UPGRADE = r"""
INSERT INTO public.platform_settings (key, value, description) VALUES
  ('reinvest_discount_pct', '5.0',
   'Investor reinvest discount (percent). Reinvesting returns buys units at an effective '
   'price = unit_price x (1 - this/100), server-applied (units = floor(amount/effective_price)). '
   'A real subsidy — the 2nd narrow D5 exception alongside the family reinvest discount; '
   'standard (non-reinvest) investment stays at the direct price with no discount.')
ON CONFLICT (key) DO NOTHING;
"""

DOWNGRADE = "DELETE FROM public.platform_settings WHERE key = 'reinvest_discount_pct';"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
