"""0027 — extracted text of uploaded property documents (assistant document search).

Batch D (client doc §3, §18): the assistant can search INSIDE a property's public documents
(SPV papers, valuations, agreements) and quote the matching passage. Text is extracted from
PDFs by a cron job into this side table; the original files stay where they are. Only
documents attached to a property (never user-scoped documents) are ever indexed.

Additive and idempotent, raw SQL like 0023/0026.
"""

from __future__ import annotations

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE IF NOT EXISTS public.document_texts (
  document_id UUID PRIMARY KEY REFERENCES public.documents(id) ON DELETE CASCADE,
  property_id UUID REFERENCES public.properties(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'indexed',          -- indexed | empty | unsupported | failed
  pages INTEGER NOT NULL DEFAULT 0,
  chars INTEGER NOT NULL DEFAULT 0,
  body TEXT NOT NULL DEFAULT '',
  error TEXT,
  extracted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS document_texts_property_idx ON public.document_texts (property_id);
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS public.document_texts;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
