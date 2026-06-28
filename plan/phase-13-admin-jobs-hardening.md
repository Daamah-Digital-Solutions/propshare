# Phase 13 — Admin Console, Background Jobs, Reconciliation & Security Hardening

**Size:** Medium-Large (≈2 weeks). This is the automation/ops backbone that makes the "no human-in-the-loop by default" promise real and provable, plus the security sign-off.

## Goal
Deliver the admin surface (the role that today **does not exist** — [audit/04-role-flows.md](../audit/04-role-flows.md)), the scheduled jobs that run automation unattended, the nightly reconciliation that proves money integrity, and the security hardening the platform launch gate requires.

## Testable outcome ("done when…")
- An admin can, from a real UI/API: review the KYC exceptions queue, approve/close properties, grant/revoke roles, view the global ledger, execute/schedule distributions, review the withdrawal exceptions queue, and query the audit log.
- **Background jobs run unattended:** expired unit reservations released, stuck payments reconciled, scheduled distributions executed, KYC reminders sent, property lifecycle advanced (option/future deadlines).
- **Nightly reconciliation is green:** `wallet == sum(ledger)` for all users and `total_units == available + issued` for all properties; drift raises an alert.
- Security review passes: rate limits, CORS lockdown, secret hygiene, signed-webhook enforcement, RBAC negative tests.

## Dependencies
All prior phases (it operates over their data). Tightest links: 2 (KYC), 5/6/7/8 (money flows), 12 (notifications for reminders).

## Backend work
- **Admin APIs** ([BACKEND_SPEC.md](../BACKEND_SPEC.md) §5.15): `GET /admin/users`, `POST /admin/users/{id}/roles`, **`GET /admin/role-requests` + `POST /admin/role-requests/{id}/approve|reject`** (the Scenario-B approval path for `broker`/`liquidity_provider`/`admin` — D12), `GET /admin/dashboard` (KPIs: AUM, funded volume, active investors, pending KYC, pending withdrawals), `GET /admin/transactions`, `POST /admin/distributions`, `GET /admin/withdrawals`, `GET /admin/audit-log`, plus the KYC/property exception endpoints from earlier phases consolidated.
- **Fee settings (D10):** `GET /admin/settings/fees` + `PUT /admin/settings/fees` — edit the `platform_settings` fee store (platform/management/resale/transfer fees) seeded in Phase 5. All money flows already READ from this store; this phase adds the **editing** capability + audit-logs every change.
- **Background workers** (ARQ/Celery beat) — the jobs from [BACKEND_SPEC.md](../BACKEND_SPEC.md) §9:
  - release expired unit reservations (every 1–5 min) — closes the Phase 5 gateway-path leak.
  - payment/payout reconciliation (every 5–15 min) — resolve stuck `pending`.
  - **ledger/balance reconciliation (nightly)** ⚠️ — assert invariants, alert on drift.
  - scheduled distributions; KYC reminders; property lifecycle (option-activation/future-settlement); monthly statement generation.
- **`scripts/reconcile.py`** runnable on demand; alerting hook (Sentry/email) on failure.
- **Security hardening:** rate limiting (SlowAPI/gateway) on auth + money endpoints; CORS to known origins; secret scanning in CI; verify all webhook signatures; full RBAC negative-test sweep; confirm RLS still present as defense-in-depth.

## DB tables/columns touched / new migrations
- Reads across all tables; `audit_log` querying. No major new tables (uses `audit_log`, `payments`, `withdrawals`, `distributions` from earlier). Possibly indexes for admin queries.

## Frontend wiring
- **Build the admin console** (new pages/routes, admin-gated via Phase 1 guards) — there is no admin UI today. Surfaces: users/roles, **role-grant request approvals (D12)**, **fee settings editor (D10)**, KYC exceptions, property approvals, distributions, withdrawals exceptions, audit log, KPI dashboard.
- Wire previously-dead role-dashboard ops buttons that need admin backing (e.g. owner "Configure Auto-Withdraw", report exports) where applicable.

## External integrations
- Alerting (Sentry), the comms providers (for reminders), the payment/payout providers (for reconciliation polling).

## Test plan
- **Success:** each admin action works and is audit-logged; jobs run on schedule and are idempotent (re-running a distribution job pays no one twice; reservation release frees only truly-expired holds).
- **Reconciliation:** seed a random sequence of deposits/invests/returns/withdrawals/secondary trades → nightly job reports all invariants hold; inject a deliberate drift → job alerts.
- **Security:** rate limit triggers under burst; forged webhook rejected; non-admin blocked from every admin route; expired token `401`.

## Risks / watch-outs
- **Reconciliation is the safety net for every prior phase** — if it can't be made green, an earlier money flow has a bug; treat red reconciliation as a release blocker.
- **Job idempotency** is as critical as endpoint idempotency (jobs retry).
- Admin is powerful — every admin action must be authz-checked and audited; consider admin 2FA.
