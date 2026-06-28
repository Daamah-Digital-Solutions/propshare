# Phase 0 — Foundation & Schema Adoption

**Size:** Small (≈1 week, 1 engineer). Low risk, but everything depends on it.

## Goal
Stand up the FastAPI service connected to the existing Supabase Postgres, with the current schema brought under Alembic, CI, and the cross-cutting plumbing (config, error envelope, OpenAPI, health) that every later phase reuses.

## Testable outcome ("done when…") — REVISED for the no-Supabase / VPS infra decision
> Supabase is dropped entirely (incl. its Postgres hosting); the DB is self-hosted on the VPS. There is **no live Supabase schema to diff against** — `0001` is the source of truth that builds the DB from scratch. The gate is therefore "**migrates clean on a fresh Postgres**", not "identical to live".
- **`alembic upgrade head` runs clean on a fresh `postgres:16`**, `scripts/verify_migration.py` confirms the 14 tables + 6 enums, and **`alembic downgrade base` is clean** — all in the CI `migrate-schema` job and reproducible via local `docker compose`.
- `GET /healthz` returns 200 when DB + Redis are reachable (503 + valid JSON otherwise); `GET /openapi.json` and `/docs` load.
- CI runs ruff + black + mypy + pytest, all green.
- ~~privileged Supabase connection-string gate~~ **removed** — no Supabase in the server path.

## Dependencies
None.

## Backend work
- FastAPI skeleton per [01-architecture.md](01-architecture.md) §2: `main.py`, `core/{config,db,redis,security,money,errors,audit}.py`, router registration, exception handlers, the error envelope, request-id + structured logging middleware.
- `core/db.py`: async SQLAlchemy 2.0 engine + session + a `transaction()` context helper (used by every money service later).
- **Alembic `0001_initial`**: translate the 6 SQL migrations verbatim — enums (`app_role`, `kyc_status`, `property_status`, `payment_method`, `investment_status`, `transaction_type`), all 14 tables, FKs, the `wallets` non-negative CHECKs, `handle_new_user` + `update_updated_at` triggers, storage-bucket rows. Keep RLS policies (defense-in-depth, §3 of architecture).
- SQLAlchemy models for all 14 existing tables (no new tables yet).
- Endpoints: `GET /healthz` only. (Domain endpoints start Phase 1.)
- `.env.example` with placeholders: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, app secrets — **no real secrets committed** (note: [.env](../.env) is currently committed and not gitignored — see [audit/01-schema.md](../audit/01-schema.md); the new backend repo must gitignore `.env`).
- Docker: `Dockerfile` + `docker-compose.yml` (app + postgres + redis + minio for local parity).
- CI: lint → typecheck → test → build image.

## DB tables/columns touched / new migrations
- New migration `0001_initial` (reproduces existing schema). No new tables/columns in this phase.

## Frontend wiring
None yet. (The SPA continues to run on mock data; no screens are connected in Phase 0.)

## External integrations
None. (Integration *interfaces* are stubbed empty in `services/integrations/` so later phases drop in providers.)

## Test plan
- **Success:** `alembic upgrade head` on a clean DB → schema-diff against a dump of the live schema shows no differences. `/healthz` 200. Lint/type/test green in CI.
- **Failure:** bad `DATABASE_URL` → `/healthz` returns 503 (not a crash); missing required env var → app refuses to boot with a clear error.

## Risks / watch-outs
- **Schema fidelity:** the `handle_new_user` trigger and enum definitions must be reproduced exactly or Phase 1's identity migration will drift. Diff-check is the guard.
- **Connection role:** ensure the server uses a privileged Postgres role; do not reuse the anon publishable key server-side.
- Decide async stack (asyncpg + SQLAlchemy async) now; switching later is costly.
