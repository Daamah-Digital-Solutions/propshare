# 00 — Master Execution Plan: Overview

**What this is:** the dependency-ordered plan to take CapiMax PropShare from *"a finished-looking website on mock data + a partial Postgres schema"* (see [audit/00-summary.md](../audit/00-summary.md)) to a **fully functional, automated investment platform** with a dedicated **Python (FastAPI)** backend. Every role, page, and function the frontend already shows must end up working for real — nothing is cut.

**Read this first if you are the project owner.** The plan is a sequence of phases. Each phase ends in *something you can actually test by clicking through the site*. No phase starts until the previous one is verified ([99-test-strategy.md](99-test-strategy.md)). The order is deliberate: we build identity → trust (KYC) → the catalog → the money plumbing → buying → returns → cashing out → trading → the remaining roles → automation & launch. You do not get a half-working money feature in an early phase; you get a fully-working *slice* each time.

---

## The phases at a glance

| Phase | Goal (one line) | Testable outcome ("done when…") |
|---|---|---|
| **0 — Foundation** | Stand up the FastAPI service against the existing Postgres DB, under Alembic. | A fresh DB migrates to the *current* schema via Alembic; `/healthz` and `/openapi.json` respond; CI is green. |
| **1 — Identity, Auth & Access Control** ⚠️ | Re-implement auth in Python, real RBAC, and **lock down the frontend**. | A real user logs in via the backend; a guest is bounced from `/dashboard`; **the role-switcher is gone** and roles can no longer be changed from the UI. |
| **2 — KYC Automation & Gating** | Automatic KYC via a provider; block investing until verified. | A test identity auto-verifies through the provider webhook with **no human step**; an unverified user is refused at the invest endpoint. |
| **3 — Property Catalog & Live Marketplace** | Properties come from the DB; owners create, admin approves, they go live. | An owner-created, admin-approved property appears in the Marketplace and on its detail page; **all hardcoded property arrays are retired**. |
| **4 — Wallet & Deposits** | Real internal wallet credited by a real payment provider. | A test card deposit credits the wallet **only after a verified webhook**; a replayed webhook does not double-credit; balance shown is the DB balance. |
| **5 — Investment Engine** ⚠️ (highest risk) | The core atomic "buy units" transaction. | Buying units debits the wallet, creates the investment, decrements `available_units`, and writes the ledger **atomically**; concurrent buyers cannot oversell; insufficient funds and sold-out are rejected. |
| **6 — Returns & Distributions** | Automated pro-rata rental/appreciation payouts. | An admin/scheduled distribution credits each holder pro-rata by units; totals reconcile; re-running the same distribution pays no one twice. |
| **7 — Withdrawals & Payouts** | Automated cash-out, with an exceptions path only. | A withdrawal within limits auto-pays via the payout provider and debits the wallet; an over-balance request is rejected; a flagged request lands in an exceptions queue (not a default human gate). |
| **8 — Secondary Market** | List and buy held units with real settlement. | Listing locks the seller's units; a buy transfers ownership and moves money atomically (buyer debited, seller credited, fee taken); the localStorage exit store is retired. |
| **9 — Liquidity Provider Module** | LP market + offers + positions, for real. | An LP makes a real offer that deploys capital against an exit/buyback and shows in their positions; dashboards read live data. |
| **10 — Family Groups & Gifting** | Real sub-accounts, transfers, allocations, reinvest. | A unit transfer between members actually moves `allocated_units` and records it; a scheduled gift persists and executes; reinvest creates a real investment with the discount applied. |
| **11 — Broker & Referrals** (virtual cards **deferred from v1**, D9) | Referral attribution → commissions. | A referred investor's purchase creates a broker commission the broker can see and withdraw; the Virtual Cards tab is hidden/disabled (no fake surface), revisited post-launch. |
| **12 — Notifications, Comms & Documents** | Real in-app/email/SMS/WhatsApp + generated contracts. | Platform events generate notifications and a real email/SMS; an investment produces a downloadable signed contract document. |
| **13 — Admin, Jobs, Reconciliation & Hardening** | The automation/ops backbone and security sign-off. | Admin can run every privileged action; nightly reconciliation is green; rate limits, audit-log queries, and a security review pass. |
| **14 — Frontend Integration & Launch** | Everything wired, E2E-verified, observable, live. | Full multi-role click-through passes on staging; observability and runbooks exist; go-live checklist signed. |

> **Effort honesty:** the reference [BACKEND_SPEC.md](../BACKEND_SPEC.md) §13 estimates ~8–10 weeks for one engineer. **That is optimistic for the scope the owner has mandated.** This plan re-implements auth *and* storage in Python (an owner decision the spec advised against — see Divergences), retires a much larger mock surface than one file, and builds *every* role to completion (LP, family, broker, cards, comms) rather than an MVP. A realistic range is **~16–22 weeks** and the money/identity phases (1, 5) warrant **more than one engineer + a reviewer**. See each phase file for per-phase sizing.

---

## Dependency graph

```
0 Foundation
└─> 1 Identity/Auth/Guards ⚠️ (security: role-switcher removal + route guards land HERE)
     ├─> 2 KYC Automation & Gating
     │    └─> (gates) ──────────────┐
     └─> 3 Property Catalog & Marketplace
          └─> 4 Wallet & Deposits
               └─> 5 Investment Engine ⚠️  [requires 2's KYC gate]
                    ├─> 6 Returns & Distributions
                    │    └─> 7 Withdrawals & Payouts
                    ├─> 8 Secondary Market
                    │    └─> 9 Liquidity Provider Module
                    ├─> 10 Family Groups & Gifting
                    └─> 11 Broker, Referrals & Virtual Cards   [referral capture starts in 1]
6,7,8,9,10,11 ──> 12 Notifications, Comms & Documents  (notify() helper seeded from Phase 2)
ALL ───────────> 13 Admin, Jobs, Reconciliation & Hardening
ALL ───────────> 14 Frontend Integration & Launch
```

Critical path: **0 → 1 → 3 → 4 → 5**. Everything financially meaningful is downstream of Phase 5, which is downstream of the wallet (4), the catalog (3), and KYC gating (2). Phases 6/8/10/11 can run in parallel once 5 is verified, given enough people.

---

## Key architectural decisions (locked) — with one-line rationale

1. **Auth: Python-owned identity (re-implemented), not Supabase Auth — with a multi-role / active-role model (Scenario B, per [capimax-resolved-decisions.md](capimax-resolved-decisions.md) D12).** FastAPI issues and verifies its own JWTs; OAuth (Google/Apple) via Authlib; passwords hashed with Argon2. **A user may hold several roles; the JWT carries the *authorized-role set* plus a chosen *active role*; every authorization check verifies the active role is within the authorized set; `Guest` is the unauthenticated state, not a role.** *Rationale: the owner has decided auth moves into the application layer and that users can switch between only the roles they are authorized for; the platform is pre-launch (demo banner says live 01/07/2026, [DevelopmentNoticeBanner.tsx:26](../src/components/layout/DevelopmentNoticeBanner.tsx:26)), so migrating identity now is safe.* (Diverges from spec; **changed locked-decision** — was single-role at first authoring, now multi-role under D12. See below.)
2. **Database: self-hosted Postgres on the owner's VPS (Hostinger, EU); adopt the existing schema into Alembic as `0001`. CHANGED LOCKED-DECISION — Supabase is dropped entirely, including its Postgres hosting.** *Rationale: the owner has moved all infra to their own VPS; `0001` (with a portability preamble that stubs the old Supabase `auth`/`storage` objects) is now the source of truth that builds the DB from scratch — there is no live Supabase DB to diff against, so the Phase 0 gate becomes "migrates clean on a fresh Postgres," see [phase-00](phase-00-foundation.md).*
3. **Storage: app-mediated (S3-compatible — MinIO/S3 on the VPS) with Python-issued signed URLs.** *Rationale: storage moves into the app layer per the owner's decision; Supabase Storage is gone; Python is the single authority that authorizes every file read/write.*
4. **Money rule: server-authoritative, integer minor units internally, `Decimal` at the boundary, never floats; the client never sends a price or a balance.** *Rationale: a money platform cannot trust the browser ([audit/03-buttons.md](../audit/03-buttons.md) shows the client currently "decides" everything).*
5. **Atomicity: every money flow is one DB transaction with `SELECT … FOR UPDATE` row locks (property/listing/wallet) + a Redis advisory lock on hot rows; oversell/over-debit rejected with `409`.** *Rationale: prevents the double-spend / oversell that the current schema has no protection against (investments INSERT is unconstrained — [audit/01-schema.md](../audit/01-schema.md)).*
6. **Idempotency: `Idempotency-Key` required on all money mutations; provider webhooks de-duped on `provider_payment_id`; enforced by Redis + a unique constraint on `payments`.** *Rationale: gateways retry; processing twice must never double-charge or double-issue.*
7. **Audit log: an append-only `audit_log` (actor, action, entity, before/after, ip, ts); never updated or deleted; written on every privileged/state-changing action.** *Rationale: compliance and reconciliation require a tamper-evident trail; AML is handled by the business but the technical record is ours to keep.*
8. **Ledger: `transactions` is append-only and the source of truth; `wallets` balances are derived/cached and reconciled nightly; `ownership_ledger` is the source of truth for units.** *Rationale: balances must always be provable from immutable entries (`sum(ledger) == wallet`, `units sold + available == total`).*

---

## Where this plan diverges from the reference roadmap ([BACKEND_SPEC.md](../BACKEND_SPEC.md))

The spec is a strong starting hypothesis. Full-codebase analysis changes these points:

1. **Auth & Storage are re-implemented, not reused.** Spec §3.2/§5.2 strongly recommends keeping Supabase Auth + Storage "to save weeks." The **owner's hard constraint overrides this**: auth/RLS/storage move into Python. *Impact: Phase 1 is larger (full auth incl. OAuth + identity migration off `auth.users`), and storage re-platforming is scheduled (Phase 1 for avatars/KYC paths, completed in Phase 12 for documents). This is the single biggest divergence and the main reason the timeline exceeds the spec's estimate.*
2. **The mock surface is far larger than "the static `sampleProperties.ts` file" (spec §2.2).** The Marketplace renders a **hardcoded inline array** ([Marketplace.tsx:44-297](../src/pages/Marketplace.tsx:44)) *plus* sampleProperties; PropertyDetails uses **two hardcoded objects** keyed by `id ∈ {4,5,6}`, ignoring the DB entirely ([PropertyDetails.tsx:38-188](../src/pages/PropertyDetails.tsx:38)); and **every dashboard has its own inline mock arrays** (e.g. [OwnerDashboard.tsx:64-126](../src/pages/OwnerDashboard.tsx:64), [LiquidityDashboard.tsx:62-146](../src/pages/LiquidityDashboard.tsx:62)). Retiring mock data is spread across ~20 files, not one. *Impact: each phase carries a real frontend-wiring cost; Phase 3 is bigger than the spec implies.*
3. **Many financial buttons have NO handler at all** — they are not "fake reads to swap," they are *unbuilt*. Investor Deposit/Withdraw ([InvestorWallet.tsx:190](../src/components/dashboard/InvestorWallet.tsx:190),[234](../src/components/dashboard/InvestorWallet.tsx:234)), installment "Pay Now" ([InstallmentSchedule.tsx:134](../src/components/dashboard/InstallmentSchedule.tsx:134),[284](../src/components/dashboard/InstallmentSchedule.tsx:284)), secondary "Confirm Purchase" ([SecondaryMarket.tsx:326](../src/pages/SecondaryMarket.tsx:326)), broker "Withdraw" ([BrokerDashboard.tsx:278](../src/pages/BrokerDashboard.tsx:278)). *Impact: front-end work in the money phases includes building handlers + forms, not just changing a data source.*
4. **Owner listing is broken in a way the spec doesn't note.** The Owner dashboard's own "List Property" form is **DEAD** (uncontrolled inputs, no submit — [OwnerDashboard.tsx:704-769](../src/pages/OwnerDashboard.tsx:704)); the *only* working create flow is the embedded `PropertyCreationForm` on the **Developer** dashboard ([PropertyCreationForm.tsx:167](../src/components/developer/PropertyCreationForm.tsx:167)). *Impact: Phase 3 must reconcile the owner/developer listing UX, not just wire an endpoint.*
5. **`developer` is not a DB role — RESOLVED (D6): it is a frontend alias of `owner`.** It stays a frontend `UserRole` label only ([AuthContext.tsx:5](../src/contexts/AuthContext.tsx:5)); `app_role` gains no `developer` value. Phase 3 reconciles the owner/developer listing UX (the working create flow on the Developer dashboard and the dead Owner "List a Property" form point at the same endpoint).
6. **Confirmed agreements with the spec** (adopted, not divergent): the `transactions` enum has **no `deposit` value** (spec §6.2) — we add it in Phase 4; wallet direct-UPDATE was removed and non-negative CHECKs exist (spec §4.2, [audit/01-schema.md](../audit/01-schema.md)); role assignment must remain admin-only (spec §5.15).
7. **Exit flow is localStorage-only** ([exitStore.ts](../src/components/exit/exitStore.ts) via [ExitFlowDialog.tsx:91](../src/components/exit/ExitFlowDialog.tsx:91)) — the spec doesn't mention exits; this is folded into Phase 8 (secondary market / exits) as a client-store retirement.

---

## Decisions status (updated per [capimax-resolved-decisions.md](capimax-resolved-decisions.md))

**Resolved (folded into the affected phase files):**

| # | Decision | Resolution | Lands in |
|---|---|---|---|
| D2 | Payment provider (cards) | **Stripe**; balance changes only on verified Stripe webhook | Phase 4 (verify Stripe payouts in-region → Phase 7) |
| D4 | Crypto in v1? | **YES** — core to v1, via **OnePayments** (crypto deposits + withdrawals) | Phase 4 (deposits) / Phase 7 (withdrawals) |
| D6 | `developer` vs `owner` | **Same role** — `developer` is a frontend alias of `owner`; no new enum value | Phase 1 (label), Phase 3 (listing UX) |
| D9 | Virtual cards | **Deferred out of v1** — keep referral/commission; hide/disable cards UI (no fake surface) | Phase 11 |
| D10 | Fee schedule | **Admin-configurable** fee-settings store (defaults platform 2.5% / mgmt 1.0%); flows READ from it | Phases 5 & 8 (read), Phase 13 (admin edit UI), seed early |
| D11 | SPV/contract document templates | **Deferred out of v1** (with generated docs); keep notifications/comms | Phase 12 |
| D12 | Multi-role users & active role | **Scenario B** — many-to-many roles, active-role in JWT, server-enforced switch, Guest = unauthenticated. Role-grant sub-decision adopted: **self-serve for `investor`/`owner`, admin-approved for `broker`/`liquidity_provider`/`admin`** | Phase 1 + architecture |

**Still open (not blocking now; resolve before the noted phase; scaffold dependents as `NOT_YET_ENABLED`):**

| # | Decision | Needed by |
|---|---|---|
| D1 | KYC/AML provider (Sumsub is the owner's earlier preference) | Phase 2 |
| D3 | Payout rails + auto-approval limits + fraud-hold thresholds (tied to Stripe-in-region check) | Phase 7 |
| D5 | **Pronova token** & **Nova Sukuk** mechanics (issuance, pricing, discount/bonus, redemption) | Phase 5 (discount) / Phase 4 (as method) |
| D7 | Liquidity-provider economics (buyback rules, pricing, returns) | Phase 9 |
| D8 | Secondary-market pricing bounds & lock-up/holding period | Phase 8 |

See [01-architecture.md](01-architecture.md) for the technical design, the per-phase files for specs, and [99-test-strategy.md](99-test-strategy.md) for how each phase is verified before the next begins.
