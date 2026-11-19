"""0047 — a certificate states whether its units are fully paid.

Client (2026-11-18, applied to every Capimax platform): a certificate reads
"FINAL · FULLY PAID", or "PROVISIONAL · INSTALLMENTS OUTSTANDING" while the holder still pays an
installment plan on the property. ``investment_certificates.payment_status`` keeps which one was
issued ('final' | 'provisional'); certificates issued before it keep NULL and read as they did.

Additive; raw SQL like 0029-0046.
"""

from __future__ import annotations

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute("ALTER TABLE investment_certificates ADD COLUMN IF NOT EXISTS payment_status TEXT")
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_certificate_payment_status') THEN
            ALTER TABLE investment_certificates ADD CONSTRAINT ck_certificate_payment_status
              CHECK (payment_status IS NULL OR payment_status IN ('final', 'provisional'));
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE investment_certificates DROP CONSTRAINT IF EXISTS ck_certificate_payment_status"
    )
    op.execute("ALTER TABLE investment_certificates DROP COLUMN IF EXISTS payment_status")
