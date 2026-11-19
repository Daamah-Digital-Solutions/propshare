"""0043 — a property document says who issued it and when.

Client letter (2026-11-18): valuations, insurance and the legal due diligence are shown on the
property page with who issued them, their dates and a download. A document keeps:

  * ``documents.issuer``    — who issued it (the valuer, the insurer, the law firm); optional.
  * ``documents.issued_on`` — the date on the document itself (not the upload date); optional.

Existing documents keep both empty and show as before. Additive; raw SQL like 0029-0042.
"""

from __future__ import annotations

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS issuer TEXT")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS issued_on DATE")


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS issued_on")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS issuer")
