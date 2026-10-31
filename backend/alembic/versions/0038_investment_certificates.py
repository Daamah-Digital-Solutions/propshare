"""0038 — investment certificates that can be verified by their QR code.

Client (2026-10-28): every Investment Certificate carries a QR code, as on Capimax BRX; scanning
it opens the certificate's verification page on PropShare, which confirms it is authentic and
shows its data and status. Until now a certificate was drawn on demand and nothing was kept, and
its reference ("CMX-" and eight characters of two ids) was neither unique nor secret.

``investment_certificates`` keeps every certificate issued:

  * ``number`` — the certificate's number (``PSC-2026-XXXXXXXX``), unique.
  * ``verification_code`` — the secret printed beside the QR and inside it (22 URL-safe
    characters, as on BRX); the public page is ``/verify/{verification_code}``.
  * a snapshot of what it states: holder, property, units, share, unit price and value, SPV,
    jurisdiction, issue date; and a signature over those values.
  * ``status`` — ``valid``; ``superseded`` when the holder's units in that property changed
    (a new certificate states the new count) or are gone; ``revoked`` by the platform.
    One valid certificate per holder and property at a time (a unique index).
  * how often it was checked (``verification_count``, ``last_verified_at``).

Additive; raw SQL like 0029-0037.
"""

from __future__ import annotations

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute("""
        CREATE TABLE IF NOT EXISTS investment_certificates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            number TEXT NOT NULL,
            verification_code TEXT NOT NULL,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'valid'
                CHECK (status IN ('valid', 'superseded', 'revoked')),
            holder_name TEXT NOT NULL,
            holder_ref TEXT NOT NULL,
            property_title TEXT NOT NULL,
            location TEXT,
            spv_name TEXT,
            jurisdiction TEXT,
            units INTEGER NOT NULL CHECK (units > 0),
            total_units INTEGER,
            ownership TEXT NOT NULL,
            unit_price NUMERIC(15, 2) NOT NULL,
            value NUMERIC(15, 2) NOT NULL,
            signature TEXT NOT NULL,
            issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            superseded_at TIMESTAMPTZ,
            superseded_by UUID REFERENCES investment_certificates(id) ON DELETE SET NULL,
            revoked_at TIMESTAMPTZ,
            revoked_by UUID,
            revocation_reason TEXT,
            verification_count INTEGER NOT NULL DEFAULT 0,
            last_verified_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS investment_certificates_number_key "
        "ON investment_certificates (number)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS investment_certificates_code_key "
        "ON investment_certificates (verification_code)"
    )
    # one valid certificate per holder and property
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS investment_certificates_one_valid "
        "ON investment_certificates (user_id, property_id) WHERE status = 'valid'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS investment_certificates_user "
        "ON investment_certificates (user_id, property_id, issued_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS investment_certificates")
