"""0002 phase1 — app-owned identity (replace Supabase auth.users).

Introduces the Phase-1 identity tables and re-platforms identity off the
Supabase ``auth.users`` stub created by 0001's portability preamble:

  * NEW tables: users, oauth_identities, refresh_tokens, email_tokens,
    role_grant_requests.
  * RE-POINT FKs: every column that referenced ``auth.users(id)`` now references
    ``public.users(id)`` (same ON DELETE behaviour).
  * DROP the ``on_auth_user_created`` trigger — provisioning of
    profiles/wallets/kyc moves into the application (auth_service.register).

CLEAN CUTOVER (owner-confirmed): there are no real users to preserve, so this
simply repoints the FK target; no data migration. After this revision the
Supabase ``auth``/``storage`` stubs are unused by the app (Phase 1 identity is
fully app-owned); they are dropped in a later cleanup once nothing references them.

⚠️ Requires a live Postgres to validate (FK constraint names follow Postgres'
default ``<table>_<column>_fkey`` convention from 0001's inline REFERENCES);
verified by the CI ``migrate-schema`` job and local ``docker compose``.
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


# Columns that referenced auth.users(id) in 0001, with their ON DELETE action.
# (table, column, ondelete) — default Postgres constraint name is f"{table}_{column}_fkey".
_FK_REPOINTS: list[tuple[str, str, str]] = [
    ("profiles", "id", "CASCADE"),
    ("user_roles", "user_id", "CASCADE"),
    ("kyc_verifications", "user_id", "CASCADE"),
    ("properties", "owner_id", "SET NULL"),
    ("investments", "user_id", "CASCADE"),
    ("wallets", "user_id", "CASCADE"),
    ("transactions", "user_id", "CASCADE"),
    ("secondary_listings", "seller_id", "CASCADE"),
    ("notifications", "user_id", "CASCADE"),
    ("documents", "user_id", "CASCADE"),
    ("family_members", "user_id", "SET NULL"),
]


CREATE_IDENTITY = r"""
CREATE TABLE public.users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT,
  full_name TEXT,
  phone TEXT,
  email_verified BOOLEAN NOT NULL DEFAULT false,
  active_role public.app_role,
  referred_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX users_email_idx ON public.users (lower(email));

CREATE TABLE public.oauth_identities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  provider_subject TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT oauth_identities_provider_subject UNIQUE (provider, provider_subject)
);

CREATE TABLE public.refresh_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  user_agent TEXT,
  ip TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX refresh_tokens_user_idx ON public.refresh_tokens (user_id);

CREATE TABLE public.email_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('verify','reset')),
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.role_grant_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  role public.app_role NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  decided_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
  decided_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX role_grant_requests_pending_idx
  ON public.role_grant_requests (status) WHERE status = 'pending';

-- Provisioning moves into the app (auth_service.register); drop the auth trigger.
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

-- family_groups.owner_id had no FK in 0001; add one to public.users for integrity.
ALTER TABLE public.family_groups
  ADD CONSTRAINT family_groups_owner_id_fkey
  FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE CASCADE;
"""


def upgrade() -> None:
    op.execute(CREATE_IDENTITY)
    for table, column, ondelete in _FK_REPOINTS:
        constraint = f"{table}_{column}_fkey"
        op.execute(
            f'ALTER TABLE public.{table} DROP CONSTRAINT IF EXISTS "{constraint}";'
            f'ALTER TABLE public.{table} ADD CONSTRAINT "{constraint}" '
            f"FOREIGN KEY ({column}) REFERENCES public.users(id) ON DELETE {ondelete};"
        )


def downgrade() -> None:
    # Re-point FKs back to the auth.users stub, then drop identity tables.
    for table, column, ondelete in _FK_REPOINTS:
        constraint = f"{table}_{column}_fkey"
        op.execute(
            f'ALTER TABLE public.{table} DROP CONSTRAINT IF EXISTS "{constraint}";'
            f'ALTER TABLE public.{table} ADD CONSTRAINT "{constraint}" '
            f"FOREIGN KEY ({column}) REFERENCES auth.users(id) ON DELETE {ondelete};"
        )
    op.execute(r"""
        ALTER TABLE public.family_groups DROP CONSTRAINT IF EXISTS family_groups_owner_id_fkey;
        DROP TABLE IF EXISTS public.role_grant_requests CASCADE;
        DROP TABLE IF EXISTS public.email_tokens CASCADE;
        DROP TABLE IF EXISTS public.refresh_tokens CASCADE;
        DROP TABLE IF EXISTS public.oauth_identities CASCADE;
        DROP TABLE IF EXISTS public.users CASCADE;
        """)
