"""0025 — users.must_change_password (staff-provisioned one-time passwords).

When an operator provisions a panel account (e.g. the content editor) the holder gets a
one-time password out of band. The flag forces them to choose their own password at the
first admin-panel login and blocks API login until then, so the shared password stops
working after first use. Additive, default false for every existing account.
"""

from __future__ import annotations

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE public.users "
        "ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE public.users DROP COLUMN IF EXISTS must_change_password")
