# 99 — Test Strategy

How each phase is proven before the next begins, and the standing checks that must keep passing as later phases land. The governing principle: **no phase starts until the previous one's gate is green**, and the **money-path invariants never regress**.

---

## 1. Environments

- **Local:** docker-compose (app + Postgres + Redis + MinIO). Every engineer runs the full stack and the test suite locally.
- **Staging:** a dedicated **VPS Postgres** + Redis + sandbox provider accounts (KYC, payments, payouts, comms). This is where phase gates are clicked through. Mirrors production config except provider keys are sandbox. (Supabase is not used — DB is self-hosted on the Hostinger VPS, EU.)
- **Production:** separate DB/keys; reached only after Phase 14.

Each phase is verified **on staging** with sandbox providers before sign-off.

---

## 2. Test layers (apply every phase)

1. **Unit tests** — service functions, especially money math (fees, pro-rata, Pronova discount), in `app/tests`. Float-free assertions on `Decimal`/minor units.
2. **Integration tests** — pytest + httpx against a test Postgres: every endpoint, every authorization rule, **positive and negative** (e.g. investor-without-KYC blocked, non-owner can't edit a property, non-admin can't grant a role).
3. **Concurrency tests** ⚠️ — for invest (Phase 5) and secondary buy (Phase 8): N parallel actors at the last units → assert no oversell and a balanced ledger.
4. **Idempotency tests** — replay the same `Idempotency-Key` and the same provider webhook → no double-charge / double-issue / double-credit.
5. **Reconciliation tests** — after a randomized sequence of operations, assert `wallet == sum(ledger)` and `units` reconcile.
6. **Webhook security tests** — forged/altered-signature webhooks are rejected.
7. **Frontend wiring check** — the phase's screens read live data; a grep gate confirms retired mock sources are gone and no new `toast.success` lacks a backing call.

CI gate every merge: ruff + black + mypy + the above suites; coverage bar highest on `services/` (the money code).

---

## 3. Per-phase "passing" definition (who clicks what)

| Phase | Verified by (staging click-through) | "Passing" means |
|---|---|---|
| 0 | Engineer | Alembic diff clean; `/healthz`, `/docs` up; CI green. |
| 1 | Engineer + reviewer | Real login (pwd+OAuth); guest blocked from guarded routes; **role-switcher gone**; non-admin can't grant roles; profile/password persist. |
| 2 | QA | Sandbox identity **auto-verifies via webhook, no human step**; declined → rejected; unverified blocked at a gated endpoint; forged webhook rejected. |
| 3 | QA + owner | Owner→submit→admin-approve makes a property appear in a live Marketplace + detail page; mock arrays gone; `draft` never public. |
| 4 | QA | Card deposit credits wallet **only on verified webhook**; replay doesn't double-credit; balance is the DB balance. |
| 5 ⚠️ | QA + reviewer + load test | Atomic buy; **concurrency → no oversell**; KYC/funds/sold-out rejected; idempotent; reconciliation holds. |
| 6 | QA | Pro-rata distribution credits holders; re-run pays no one twice; totals reconcile. |
| 7 | QA | In-limit withdrawal **auto-pays**; over-balance rejected; flagged → exceptions queue (not default human gate). |
| 8 | QA + load test | List locks units; buy settles atomically; concurrency → one winner; exit store retired. |
| 9 | QA + owner | LP offer deploys capital + funds an exit atomically; positions/returns live. (Gated on D7.) |
| 10 | QA | Transfer moves units; reinvest creates a real investment with discount; scheduled gift executes. |
| 11 | QA | Referred buy → one commission → broker withdraw; cards real or explicitly disabled (no fake PANs). |
| 12 | QA | Events create notifications + real email/SMS; investment contract downloads via signed URL. |
| 13 | QA + security reviewer | All admin actions work + audited; jobs run unattended; **nightly reconciliation green**; rate limits/CORS/secrets pass. |
| 14 | Owner UAT | Full multi-role E2E passes; no mock/fake/dead money controls remain; observability + runbooks; 7 nights green reconciliation. |

A phase is **not** done until: its endpoints are in OpenAPI; authz is enforced + tested (positive & negative); money ops are atomic, idempotent, concurrency-safe, and write ledger + audit; the phase's frontend screens are wired to live data (mock removed) and verified; and reconciliation holds. (This mirrors [BACKEND_SPEC.md](../BACKEND_SPEC.md) §14's Definition of Done.)

---

## 4. Standing regression checks (must keep passing as later phases land)

These run in CI on every change from the phase they're introduced onward — money integrity must never regress:

1. **Ledger integrity:** `wallet.balance == sum(signed transactions)` per user (from Phase 4).
2. **Unit integrity:** `property.total_units == available_units + sum(ownership_ledger issued − transferred-out)` (from Phase 5).
3. **No-oversell concurrency suite:** the Phase 5 and Phase 8 parallel-buyer tests run in CI permanently.
4. **Idempotency suite:** invest/deposit/withdraw/secondary-buy replay + duplicate-webhook tests (cumulative).
5. **Authorization matrix (Scenario B):** every role × every protected endpoint (positive/negative), re-run each phase as new endpoints are added — guards the Phase 1 lockdown. Must include the **active-role tamper test**: `POST /auth/switch-role` (or any crafted request) to a role **not in the user's authorized set** is rejected `403 ROLE_NOT_AUTHORIZED` server-side; a JWT with `active_role ∉ roles` is rejected; protected routes check the *active* role, not a client-claimed one.
6. **Webhook signature suite:** forged webhooks rejected for every provider integrated so far.
7. **Reconciliation job (nightly on staging):** the Phase 13 job; must be green for 7 consecutive nights before launch and stay green after.
8. **No-fakes gate:** repo check that no rendered screen imports the retired mock property data and no money action shows success without a backing API call (guards against regressions into the audited "fake-success" pattern).

---

## 5. Launch gate (Phase 14 sign-off)

All of: KYC auto-gating active · no oversell under concurrency · verified-webhooks-only enforced · reconciliation green 7 consecutive nights · admin can review KYC exceptions, approve properties, execute a distribution, process a withdrawal exception, and manage roles · security review signed off · every OPEN DECISION (D1–D12) resolved or its feature explicitly disabled (never faked) · demo banner removed and no fabricated regulatory/performance claims remain.
