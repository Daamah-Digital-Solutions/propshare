"""0024 — `content_editor` value on the app_role enum (admin-panel listings-only role).

The platform owner manages listings through the admin panel without full admin power:
a content editor can only reach the Listing Editor (properties, photos, documents,
milestones, publish/unpublish). Enforced in app code (SQLAdmin `is_accessible` + guards);
this migration only adds the enum value. Adding an enum value cannot run inside the
migration transaction, hence the autocommit block. Additive; idempotent.
"""

from __future__ import annotations

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE public.app_role ADD VALUE IF NOT EXISTS 'content_editor'")


def downgrade() -> None:
    # PostgreSQL cannot drop a single enum value; the value is harmless when unused.
    pass
