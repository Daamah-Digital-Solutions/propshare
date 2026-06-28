"""Verify that `alembic upgrade head` produced the expected schema.

Run AFTER `alembic upgrade head` against the target DB (uses ALEMBIC_DATABASE_URL
or DATABASE_URL). Asserts the 14 public tables + 6 enum types exist. This is the
CI gate for Phase 0's "schema reproduced" outcome on a fresh Postgres.

For the stronger "identical to the LIVE Supabase schema" check, run a structural
diff (e.g. `migra`/`pg_dump --schema-only`) against the live DB — that requires a
privileged connection string to the owner's Supabase project (not available in
this environment); see backend/README.md.
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from app.core.config import get_settings

EXPECTED_TABLES = {
    "profiles",
    "user_roles",
    "kyc_verifications",
    "properties",
    "investments",
    "wallets",
    "transactions",
    "secondary_listings",
    "notifications",
    "documents",
    "family_groups",
    "family_members",
    "family_transfers",
    "family_return_allocations",
}
EXPECTED_ENUMS = {
    "app_role",
    "kyc_status",
    "property_status",
    "payment_method",
    "investment_status",
    "transaction_type",
}


def _sync_url() -> str:
    s = get_settings()
    return s.alembic_database_url or s.database_url.replace("+asyncpg", "+psycopg")


def main() -> int:
    engine = create_engine(_sync_url())
    with engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
        enums = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT t.typname FROM pg_type t "
                    "JOIN pg_namespace n ON n.oid=t.typnamespace "
                    "WHERE n.nspname='public' AND t.typtype='e'"
                )
            )
        }

    missing_tables = EXPECTED_TABLES - tables
    missing_enums = EXPECTED_ENUMS - enums
    if missing_tables or missing_enums:
        print(f"FAIL: missing tables={sorted(missing_tables)} enums={sorted(missing_enums)}")
        return 1
    print(f"OK: {len(EXPECTED_TABLES)} tables + {len(EXPECTED_ENUMS)} enums present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
