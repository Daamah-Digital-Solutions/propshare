# 01 — Backend Architecture

This is the technical design every phase builds against. It locks the project structure, the DB-adoption strategy, the auth/RBAC model, the cross-cutting money rules, and the external integration seams. Decisions here are the ones referenced (not re-argued) in the phase files.

---

## 1. High-level shape

```
        React SPA (existing, ~35 routes)            <- src/, untrusted client
        Vite · TS · shadcn/ui · TanStack Query
                  │  REST/JSON, Authorization: Bearer <app JWT>
                  ▼
        ┌────────────────────────────────────────┐
        │   Python Backend (NEW) — FastAPI         │  <- the trusted authority
        │   • own auth (JWT issue/verify, OAuth)   │
        │   • RBAC + KYC gating (FastAPI deps)     │
        │   • money/units engine (atomic, locked)  │
        │   • payments + webhooks (idempotent)     │
        │   • admin APIs, background workers        │
        └───────┬───────────────┬──────────────────┘
                │               │                  │
                ▼               ▼                  ▼
     PostgreSQL (self-hosted  Redis (locks,    S3-compatible storage
     on the VPS — Hostinger,  idempotency,     (MinIO/S3 on the VPS)
     EU; via Alembic)         job queue)       + signed URLs
```

**Infra (owner decision): Supabase is dropped entirely** — not just its Auth/Storage/RLS services but its Postgres hosting too. The whole backend + database runs on the owner's **VPS (Hostinger, Europe)**. There is **no live Supabase DB to diff against**; the Alembic `0001` migration is the **source of truth** and builds the schema from scratch on the VPS Postgres. The frontend talks **only** to the Python API after Phase 1; `supabase-js` is removed entirely (see [phase-01](phase-01-identity-access.md)).

> **Why the client must become untrusted:** today the browser "decides" balances, units, and success ([audit/03-buttons.md](../audit/03-buttons.md)). The architecture's job is to move every authoritative decision server-side.

---

## 2. Project structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, router + middleware + exception handlers
│   ├── core/
│   │   ├── config.py            # pydantic-settings; all secrets from env
│   │   ├── db.py                # async SQLAlchemy engine/session; tx helper
│   │   ├── redis.py             # redis client; lock + idempotency helpers
│   │   ├── security.py          # password hashing (argon2), JWT issue/verify, OAuth
│   │   ├── money.py             # Decimal/minor-unit helpers; fee math primitives
│   │   ├── errors.py            # error envelope + handlers
│   │   └── audit.py             # write_audit(actor, action, entity, before, after, ip)
│   ├── models/                  # SQLAlchemy 2.0 models, 1 per table (incl. new tables)
│   ├── schemas/                 # Pydantic v2 request/response DTOs
│   ├── api/
│   │   ├── deps.py              # current_user, require_role(...), require_kyc_verified, require_owner
│   │   └── routes/
│   │       ├── auth.py  profiles.py  kyc.py  properties.py  investments.py
│   │       ├── wallet.py  transactions.py  secondary_market.py  liquidity.py
│   │       ├── family.py  broker.py  cards.py  notifications.py  documents.py
│   │       ├── payments.py            # + /webhooks/{provider}
│   │       └── admin/                 # users, kyc, properties, distributions, withdrawals, audit
│   ├── services/                # ⚠️ the important part — all business logic lives here
│   │   ├── auth_service.py  kyc_service.py  property_service.py
│   │   ├── wallet_service.py  payment_service.py  investment_service.py
│   │   ├── distribution_service.py  withdrawal_service.py
│   │   ├── secondary_market_service.py  liquidity_service.py
│   │   ├── family_service.py  referral_service.py  card_service.py
│   │   ├── notification_service.py  document_service.py  ledger_service.py
│   │   └── integrations/        # kyc_provider/  payments/  payouts/  email/  sms/  storage/
│   ├── workers/                 # ARQ/Celery tasks: reservations, reconciliation, distributions, comms
│   └── tests/                   # unit (services) + integration (endpoints+authz) + concurrency
├── alembic/                     # 0001 = existing schema verbatim; subsequent = new tables/columns
├── scripts/                     # seed_admin.py, reconcile.py
├── docker-compose.yml           # app + postgres + redis + minio (local)
├── Dockerfile
├── pyproject.toml               # ruff + black + mypy config
└── .env.example
```

**Rule:** routes do auth + validation + call a service; **services own all DB writes and money logic**; integrations wrap external providers behind an interface so providers can be swapped (the still-open decisions D1/D3/D5/D7/D8 don't block structure).

---

## 3. Connecting to the existing Postgres & adopting it into Alembic

1. The Python service connects to the **self-hosted VPS Postgres** via `DATABASE_URL` (`postgresql+asyncpg://…`) using a privileged role. (Supabase is gone; there is no anon key and no Supabase project in the server path.)
2. **Alembic baseline (`0001_initial`)** reproduces the schema documented in [audit/01-schema.md](../audit/01-schema.md) — 14 tables, 6 enums, triggers (`handle_new_user`, `update_updated_at`), constraints. **Because Supabase is dropped, `0001` is now the source of truth that builds the DB from scratch** — there is no live Supabase schema to diff against. The migration carries a **portability preamble** that stubs the Supabase-managed `auth`/`storage` schemas, `auth.uid()`, `storage.foldername()` and the `anon`/`authenticated`/`service_role` roles **only if absent**, so it runs clean on a vanilla `postgres:16`. **Phase 0 gate (revised): `alembic upgrade head` runs clean on a fresh Postgres + `verify_migration.py` confirms 14 tables + 6 enums + `alembic downgrade base` is clean** — verified by the CI `migrate-schema` job and the owner's local `docker compose`.
3. **RLS handling.** Python connects with a privileged role and enforces authorization itself, so RLS is not the access boundary. The adopted policies (which reference the stubbed `auth.uid()`, now returning NULL) are retained as inert documentation-of-intent / defense-in-depth; **the app re-implements every rule** (Section 5). Phase 1 re-platforms identity off the `auth.users` stub onto an app-owned `users` table; these legacy policies are revisited/retired as that lands.
4. **Identity ownership migration (Phase 1).** The schema currently FKs to Supabase's `auth.users`. Since auth moves into Python, Phase 1 introduces an app-owned `users` table and re-points the FKs (`profiles.id`, `*.user_id`, `properties.owner_id`, etc.). Because the platform is **pre-launch** with no real customer accounts (demo banner, live 01/07/2026), this is a clean migration, not a data-preserving cutover. The `handle_new_user` trigger is replaced by an application-level `auth_service.register()` that creates the `profiles` + `wallets` + `kyc_verifications` rows in one transaction (preserving the current auto-provisioning behavior).
5. **New tables/columns** (added as later migrations, each in the phase that needs it): `users` + `users.active_role` + `users.referred_by` and **`role_grant_requests`** (Phase 1, Scenario B); `audit_log`, `payments`, `distributions`, `payout_items`, `referrals`, `ownership_ledger`, `property_milestones` (or JSONB), model-term columns on `properties`, `idempotency_keys` (if not Redis-only), `withdrawals`, `liquidity_offers`, **`platform_settings`** (admin-configurable fees, D10). The **`deposit` value is added to the `transaction_type` enum** in Phase 4. *(`cards` is **deferred from v1** — D9 — and not built now.)*

---

## 4. Auth & RBAC design (Scenario B — multi-role with an active role; D12)

**Identity (Python-owned):**
- Email/password: Argon2 hashing; signup/login/refresh/password-reset endpoints.
- OAuth: Google & Apple via Authlib, mapping provider identity → app `users` row (matches the OAuth the frontend already exposes — [Auth.tsx:159](../src/pages/Auth.tsx:159),[193](../src/pages/Auth.tsx:193)).
- Tokens: short-lived access JWT + refresh token; signed with an app secret; verified by `core/security.py` on every request.

**Multi-role model (the core of Scenario B):**
- **Roles are many-to-many.** A user may hold several `app_role`s. The existing `user_roles` table already models this 1:N with `UNIQUE(user_id, role)` ([audit/01-schema.md](../audit/01-schema.md)) — **no schema change needed to support multiple roles**; we only stop assuming a single role (the current frontend takes `roles[0]` — [AuthContext.tsx:41](../src/contexts/AuthContext.tsx:41),[66](../src/contexts/AuthContext.tsx:66)).
- **JWT claims:** `sub` (user id), `roles` (the **authorized-role set**, loaded from `user_roles`), and `active_role` (the currently selected role, which **must** be a member of `roles`). The default `active_role` at login is persisted as `users.active_role` (added in Phase 1) for continuity across sessions; `Guest` is **not** a role — it is the no-session/unauthenticated state.
- **Token storage (owner-mandated):** **httpOnly, Secure, SameSite refresh-token cookie + in-memory access token** (short TTL). **No tokens in `localStorage`** — this is a money platform. The access token never touches JS-readable storage; refresh happens via the cookie.
- **Switch active role:** `POST /auth/switch-role {role}` re-mints the JWT with the new `active_role` **only if `role ∈ roles`**; otherwise `403 ROLE_NOT_AUTHORIZED`. The repurposed sidebar switcher ([AppSidebar.tsx:369](../src/components/layout/AppSidebar.tsx:369)) calls this and renders **only** the user's authorized roles (fetched from the backend) — the old "anyone can assume any role" behavior is gone, and security is enforced server-side, not by hiding the control.

**RBAC dependencies (FastAPI):**
- `current_user` — valid token → loads user + authorized roles + `active_role` + KYC status + wallet summary.
- `require_role("owner")` etc. — passes only if the role is **both** the `active_role` **and** in the authorized set. (Active role gates the *current* action; authorized set bounds what the user could switch to.)
- **`require_active_role_db(...)` — DB re-verification at action time (owner-mandated, money endpoints).** Every financially sensitive endpoint (invest, deposit, withdraw, secondary buy/sell, liquidity deploy, family transfer, payouts, role grants) **re-queries `user_roles` at request time** to confirm the JWT's `active_role` is *still* in the user's authorized set — it does **not** trust the token alone. So a role revoked mid-session cannot act even within a still-valid access token's TTL. (Read-only endpoints may rely on the token; money/privileged ones must re-check.)
- `require_kyc_verified` — 403 `KYC_REQUIRED` unless `kyc_verifications.status = 'verified'` (invest / secondary-buy / withdraw).
- `require_owner(resource)` — resource-ownership check (replaces the RLS `auth.uid() = owner_id` rules).

**Gaining a new role (D12 sub-decision, adopted):**
- **Self-serve:** a user may add `investor` or `owner` themselves (`POST /roles/request {role}` inserts directly into `user_roles`). *(`developer` is a frontend alias of `owner` — D6 — so "become a developer/lister" = gaining `owner`.)*
- **Admin-approved:** `broker`, `liquidity_provider`, and `admin` require admin approval — `POST /roles/request` creates a row in a new **`role_grant_requests`** table (`pending`); an admin approves/rejects via `POST /admin/role-requests/{id}/approve|reject`, which inserts into `user_roles` on approval. The first `admin` is seeded via `scripts/seed_admin.py`; **`admin` is never self-grantable.**
- All role grants/switches are audit-logged. There is and will be no client path to grant oneself an unauthorized role.

---

## 5. Cross-cutting rules every financial endpoint MUST follow

These are non-negotiable and are re-stated as test requirements in each money phase and in [99-test-strategy.md](99-test-strategy.md).

1. **Atomic transaction.** The whole operation runs in one DB transaction; partial failure rolls back entirely.
2. **Server-authoritative amounts.** The client sends *intent* (property_id, units, listing_id) — **never** a price, fee, or balance. The backend computes money via `core/money.py` + `properties.fees`.
3. **Decimal/minor-units, never float.** Integers in minor units internally; decimal strings at the API boundary.
4. **Row locking to prevent oversell/double-spend.** `SELECT … FOR UPDATE` on the contended rows (property, listing, wallet) + a Redis advisory lock keyed by the hot entity (e.g. `lock:property:{id}`). Reject with `409 INSUFFICIENT_UNITS` / `409 INSUFFICIENT_FUNDS`.
5. **Idempotency.** Money mutations require an `Idempotency-Key` header; replays return the original result. Webhooks de-dupe on `provider_payment_id`. Backed by Redis + a unique constraint on `payments.idempotency_key`.
6. **Ledger + audit are mandatory.** No wallet mutation without a matching append-only `transactions` row; every privileged/state-changing action writes an immutable `audit_log` entry (before/after). `ownership_ledger` records every unit movement.
7. **Reconciliation invariants** (checked nightly, Phase 13): `wallet.balance == sum(signed transactions)` per user; `property.total_units == available_units + units issued in ownership_ledger`.
8. **Webhooks are the source of truth, not browser redirects.** A payment is `succeeded` only on a signature-verified webhook; the SPA polls `/payments/{id}`.
9. **Fees are read from an admin-configurable settings store, never hardcoded (D10).** A `platform_settings` (fee-settings) store holds platform/management/resale/transfer fees, seeded with defaults (`platform 2.5% / management 1.0%`); per-property overrides may still live in `properties.fees`. All pricing (invest quote — Phase 5; resale fee — Phase 8) reads the effective fee at transaction time; the admin edits it in Phase 13. No money flow embeds a fee constant.

---

## 6. External integration points (seams)

Each provider sits behind an interface in `services/integrations/` so the concrete vendor (the OPEN DECISIONs) can be chosen/swapped without touching business logic.

| Seam | Interface | Plugs in at | Owner decision |
|---|---|---|---|
| **KYC/AML** | `kyc_provider.create_applicant()/get_status()` + inbound `verification` webhook | Phase 2 | D1 (Sumsub/Onfido/Persona) |
| **Payments (pay-in)** | `payments.create_intent()/verify_webhook()` | Phase 4 (deposits), reused Phase 5 (gateway-funded invest) | **D2 = Stripe** (cards); **D4 = OnePayments** (crypto, in v1); D5 (pronova/sukuk as methods) — two concrete adapters behind one interface |
| **Payouts (pay-out)** | `payouts.send()/get_status()` | Phase 7 (withdrawals: Stripe + OnePayments crypto), Phase 6 (if paying to bank vs wallet) | D3 (limits/rails); ⚠️ verify Stripe payouts available in target GCC region (Phase 4/7) |
| **Email** | `email.send(template, to, ctx)` | Phase 12 (helper seeded Phase 2) | provider choice (Resend/Postmark/SES) |
| **SMS / WhatsApp** | `sms.send()` / `whatsapp.send()` | Phase 12 | provider choice (Twilio/Meta) |
| **Card issuing** | *(deferred — D9)* | post-launch | **Not in v1** — no issuing integration built |
| **Storage** | `storage.put()/signed_url()` | Phase 1 (avatars, KYC paths), Phase 12 (documents) | S3-compatible target |
| **Document/PDF generation** | *(deferred — D11)* | post-launch | **Not in v1** — Phase 12 serves *uploaded* docs via signed URLs only |

Notifications are an **internal** seam: `notification_service.notify(user_id, type, title, message)` writes a `notifications` row (the table the frontend bell will read) and optionally fans out to email/SMS. The helper is introduced in Phase 2 (first events) and the external comms providers are wired in Phase 12.

---

## 7. API conventions (applies to all phases)

- Base path `/api/v1`. `Authorization: Bearer <app JWT>` on all non-public routes.
- Error envelope: `{ "error": { "code", "message", "details" } }` with correct HTTP status.
- Pagination: `?page=&limit=` → `{ "data": [...], "meta": { total, page, limit } }`.
- OpenAPI at `/docs` + `/openapi.json` is **the frontend contract** — kept accurate every phase; a Postman/Insomnia collection is exported for the frontend dev.
- CORS locked to the known frontend origin(s); HTTPS/HSTS/secure headers; rate limiting on auth + money endpoints (Phase 13 hardens, basics from Phase 1).
