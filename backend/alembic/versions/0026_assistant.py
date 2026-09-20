"""0026 — AI assistant foundation: conversations, consents, tickets, knowledge base.

Plan Phase 1, §3. Additive and idempotent (IF NOT EXISTS), in the raw-SQL style of 0023.

Notes that matter for safety and privacy:
  * conversation text is stored ENCRYPTED (BYTEA, AES-256-GCM in the application), so
    database dumps and the nightly backups never contain readable chat;
  * ``assistant_messages.usage`` holds token COUNTS only, never content;
  * support tickets stay plaintext because staff read them, and by design they carry a
    structured summary only, never message bodies;
  * consent is recorded per user per policy version, so a privacy-policy change re-asks.

Nothing here turns the assistant on: every platform setting seeded below is off or empty.
"""

from __future__ import annotations

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


UPGRADE = r"""
-- conversations -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.assistant_conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,   -- NULL => visitor
  visitor_key TEXT,
  active_role TEXT,
  lang TEXT NOT NULL DEFAULT 'en',
  title TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  ticket_id UUID,
  message_count INTEGER NOT NULL DEFAULT 0,
  total_input_tokens BIGINT NOT NULL DEFAULT 0,
  total_cached_input_tokens BIGINT NOT NULL DEFAULT 0,
  total_output_tokens BIGINT NOT NULL DEFAULT 0,
  total_reasoning_tokens BIGINT NOT NULL DEFAULT 0,
  est_cost_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
  model TEXT,
  provider TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_message_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS assistant_conversations_user_idx
  ON public.assistant_conversations (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS assistant_conversations_visitor_idx
  ON public.assistant_conversations (visitor_key, created_at DESC);

-- messages (content columns are ciphertext) -----------------------------------
CREATE TABLE IF NOT EXISTS public.assistant_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL
    REFERENCES public.assistant_conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL,                     -- user | assistant | system_note
  text_enc BYTEA,
  content_enc BYTEA,
  tool_calls_enc BYTEA,
  cards_enc BYTEA,
  enc_key_id TEXT,
  usage JSONB NOT NULL DEFAULT '{}'::jsonb,   -- token counts only, never content
  latency_ms INTEGER,
  first_token_ms INTEGER,
  confidence TEXT,
  guardrail_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
  feedback TEXT,
  lang TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS assistant_messages_conversation_idx
  ON public.assistant_messages (conversation_id, created_at);
-- review queue: low-confidence or flagged answers first
CREATE INDEX IF NOT EXISTS assistant_messages_review_idx
  ON public.assistant_messages (created_at DESC)
  WHERE confidence = 'low' OR feedback = 'down';

-- proposed actions (the model proposes; a separate authenticated call executes) --
CREATE TABLE IF NOT EXISTS public.assistant_action_proposals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL
    REFERENCES public.assistant_conversations(id) ON DELETE CASCADE,
  message_id UUID REFERENCES public.assistant_messages(id) ON DELETE SET NULL,
  user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
  action TEXT NOT NULL,
  params JSONB NOT NULL DEFAULT '{}'::jsonb,
  summary TEXT,
  token_hash TEXT NOT NULL,               -- one-time confirmation token (hash only)
  status TEXT NOT NULL DEFAULT 'awaiting_user_confirmation',
  result JSONB,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS assistant_proposals_conversation_idx
  ON public.assistant_action_proposals (conversation_id, created_at DESC);

-- consent, per user per policy version ---------------------------------------
CREATE TABLE IF NOT EXISTS public.assistant_consents (
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  policy_version TEXT NOT NULL,
  accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ip TEXT,
  PRIMARY KEY (user_id, policy_version)
);

-- support tickets (staff-facing, plaintext, NEVER chat bodies) ----------------
CREATE SEQUENCE IF NOT EXISTS public.support_ticket_no_seq START 1001;
CREATE TABLE IF NOT EXISTS public.support_tickets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_no TEXT NOT NULL UNIQUE
    DEFAULT ('CPX-' || lpad(nextval('public.support_ticket_no_seq')::text, 6, '0')),
  kind TEXT NOT NULL DEFAULT 'support',     -- support | knowledge_gap
  user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
  contact_email TEXT,
  conversation_id UUID REFERENCES public.assistant_conversations(id) ON DELETE SET NULL,
  category TEXT,
  priority TEXT NOT NULL DEFAULT 'normal',
  status TEXT NOT NULL DEFAULT 'open',
  subject TEXT,
  summary TEXT,                              -- rendered from a structured handoff object
  context JSONB NOT NULL DEFAULT '{}'::jsonb,
  source TEXT NOT NULL DEFAULT 'assistant',
  assigned_to UUID REFERENCES public.users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ,
  csat SMALLINT
);
CREATE INDEX IF NOT EXISTS support_tickets_status_idx
  ON public.support_tickets (status, created_at DESC);
CREATE INDEX IF NOT EXISTS support_tickets_user_idx
  ON public.support_tickets (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.support_ticket_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id UUID NOT NULL REFERENCES public.support_tickets(id) ON DELETE CASCADE,
  author_type TEXT NOT NULL,                 -- user | staff | system
  author_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
  body TEXT NOT NULL,
  internal BOOLEAN NOT NULL DEFAULT false,   -- internal notes are never shown to the user
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS support_ticket_messages_ticket_idx
  ON public.support_ticket_messages (ticket_id, created_at);

-- the conversation's ticket link (added after support_tickets exists)
ALTER TABLE public.assistant_conversations
  DROP CONSTRAINT IF EXISTS assistant_conversations_ticket_fk;
ALTER TABLE public.assistant_conversations
  ADD CONSTRAINT assistant_conversations_ticket_fk
  FOREIGN KEY (ticket_id) REFERENCES public.support_tickets(id) ON DELETE SET NULL;

-- approved knowledge base (versioned; the agent reads approved rows only) -----
CREATE TABLE IF NOT EXISTS public.kb_articles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL,
  lang TEXT NOT NULL DEFAULT 'en',
  title TEXT NOT NULL,
  body_md TEXT NOT NULL,
  category TEXT,
  audience TEXT NOT NULL DEFAULT 'all',
  status TEXT NOT NULL DEFAULT 'draft',      -- draft | approved | retired
  version INTEGER NOT NULL DEFAULT 1,
  source_ref TEXT,
  priority INTEGER NOT NULL DEFAULT 100,
  approved_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
  approved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT kb_articles_slug_lang_version_key UNIQUE (slug, lang, version)
);
CREATE INDEX IF NOT EXISTS kb_articles_approved_idx
  ON public.kb_articles (lang, status, priority);

-- settings seeds: everything off / empty until the owner decides ---------------
INSERT INTO public.platform_settings (key, value) VALUES
  ('assistant_enabled', 'false'),
  ('assistant_visitor_enabled', 'false'),
  ('assistant_provider', 'openai'),
  ('assistant_model', ''),
  ('assistant_reasoning_effort', 'low'),
  ('assistant_max_output_tokens', '2048'),
  ('assistant_disabled_tools', ''),
  ('assistant_daily_message_cap', '200'),
  ('assistant_daily_token_budget', '20000000'),
  ('assistant_retention_days', '180'),
  ('assistant_rollout', 'admins'),
  ('assistant_model_pricing', '{}')
ON CONFLICT (key) DO NOTHING;
"""

DOWNGRADE = r"""
DELETE FROM public.platform_settings WHERE key LIKE 'assistant\_%';
DROP TABLE IF EXISTS public.kb_articles;
DROP TABLE IF EXISTS public.support_ticket_messages;
ALTER TABLE IF EXISTS public.assistant_conversations
  DROP CONSTRAINT IF EXISTS assistant_conversations_ticket_fk;
DROP TABLE IF EXISTS public.support_tickets;
DROP SEQUENCE IF EXISTS public.support_ticket_no_seq;
DROP TABLE IF EXISTS public.assistant_consents;
DROP TABLE IF EXISTS public.assistant_action_proposals;
DROP TABLE IF EXISTS public.assistant_messages;
DROP TABLE IF EXISTS public.assistant_conversations;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
