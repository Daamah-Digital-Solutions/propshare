# CapiMax PropShare — Backend (Python / FastAPI)

Phase 0: **Foundation & Schema Adoption**. This is the standalone Python service
that will own all business logic (see `../plan/`). Phase 0 stands up the app
skeleton, connects to the existing Postgres, and brings the current schema under
Alembic. No domain/feature endpoints yet (those start in Phase 1).

> This folder is intended to be its **own git repository**. `.env` is gitignored
> here (the frontend repo committed its `.env` — we do not repeat that).

## What Phase 0 delivers
- FastAPI app (`app/main.py`) with CORS, error envelope, request-id logging.
- `GET /` (liveness) and `GET /healthz` (DB + Redis readiness; 200 up / 503 down).
- OpenAPI at `/openapi.json` and Swagger UI at `/docs` — the frontend contract.
- SQLAlchemy 2.0 models for all 14 existing tables (`app/models/`).
- **Alembic `0001`** reproducing the live Supabase schema verbatim, runnable on a
  vanilla Postgres via a guarded `auth`/`storage` portability preamble.
- Dockerfile + docker-compose (api + postgres + redis + minio).
- CI (`.github/workflows/ci.yml`): ruff + black + mypy + pytest, plus a job that
  applies migrations to a fresh Postgres and verifies the schema.

## Run locally (with Docker)
```bash
cp .env.example .env          # adjust if needed
docker compose up --build     # api on http://localhost:8000
curl localhost:8000/healthz   # {"status":"ok", dependencies all "up"}
open http://localhost:8000/docs
```

## Run locally (without Docker)
```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows; use bin/activate on *nix
pip install ".[dev]"
# Point DATABASE_URL/REDIS_URL at running services, then:
alembic upgrade head            # applies 0001 to a fresh DB
python scripts/verify_migration.py
uvicorn app.main:app --reload   # /healthz returns 503 until DB+Redis are reachable
pytest -q                       # tests pass with or without datastores
```

## Migrations
- `alembic upgrade head` — apply (on a **fresh** DB, `0001` builds the full schema).
- Against the **live Supabase** DB the schema already exists, so you would
  `alembic stamp 0001` instead of upgrading.
- New schema changes from Phase 1 onward are added as `0002+` revisions.

## Verifying "schema identical to live" (the full Phase 0 gate)
`scripts/verify_migration.py` checks the 14 tables + 6 enums exist on a fresh DB
(run in CI). A byte-level diff against the **live** Supabase schema needs a
privileged connection string to the owner's project (not available in this
environment) — run `migra`/`pg_dump --schema-only` against both and diff. **This
is the one Phase 0 check that must be run by the owner against their DB.**

## Layout
```
app/
  main.py            # FastAPI app factory + middleware
  core/              # config, db, redis, errors (audit/security/money land later)
  api/routes/        # health.py (domain routers from Phase 1)
  models/            # SQLAlchemy models for the 14 existing tables
  tests/             # health + openapi tests
alembic/             # env.py + versions/0001_initial.py
scripts/             # verify_migration.py
```
