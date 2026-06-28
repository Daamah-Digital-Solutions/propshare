# Phase 14 — Full Frontend Integration, E2E QA & Launch

**Size:** Medium (≈1.5–2 weeks). Frontend wiring happened incrementally per phase; this phase is the final sweep, full multi-role E2E verification, observability, and go-live.

## Goal
Confirm the whole platform works end-to-end for every role, on staging, with observability and runbooks, then launch. Validates that **no mock data and no fake-success buttons remain** anywhere (the audit's core complaint is fully resolved).

## Testable outcome ("done when…")
- A full multi-role click-through passes on staging (scripts below): investor, owner/developer, broker, liquidity_provider, admin — each completes their real journey from [audit/04-role-flows.md](../audit/04-role-flows.md) end to end.
- A repository-wide check confirms: no `sampleProperties`/hardcoded property arrays feeding screens; no `toast.success` without a real backend call; no dead financial buttons; no client role mutation.
- Observability (logs, Sentry, `/healthz`, money-endpoint metrics) and runbooks exist; reconciliation has been green for **7 consecutive nights**; go-live checklist signed.

## Dependencies
All phases (0–13).

## Backend work
- Final OpenAPI accuracy pass; export the Postman/Insomnia collection for the record.
- Production config: env/secrets in a secret manager (not the repo — recall [.env](../.env) is currently committed; the production posture must not repeat that), CORS, HTTPS/HSTS, backups, migration-on-deploy.
- Load/concurrency test the money paths (invest, secondary buy) at expected peak.

## Frontend wiring (final sweep)
- Resolve any remaining mock/dead items flagged across [audit/03-buttons.md](../audit/03-buttons.md): home marketing dead controls ([BenefitsSection.tsx:98,126](../src/components/home/BenefitsSection.tsx:98)), fabricated stats/claims ([HeroSection.tsx:25-30](../src/components/home/HeroSection.tsx:25)), the **"Regulated by Financial Services Authority"** claim ([Footer.tsx:150](../src/components/layout/Footer.tsx:150)) — remove or substantiate (compliance). Footer links to non-existent routes either build the pages or remove.
- Remove the development/demo banner ([DevelopmentNoticeBanner.tsx:26](../src/components/layout/DevelopmentNoticeBanner.tsx:26)) at go-live.
- Confirm every page from [audit/02-pages.md](../audit/02-pages.md) reads live data or is intentionally static (legal/marketing).

## External integrations
- Switch all providers (KYC, payments, payouts, comms, cards) from sandbox to production credentials; verify production webhooks.

## Test plan (E2E scripts — the launch gate)
- **Investor:** register → KYC auto-verify → deposit → invest → see holding + funding decrement → receive a distribution → list on secondary / exit → withdraw. All real, all reconciled.
- **Owner/Developer:** create property → submit → admin approves → it appears in marketplace → funding tracked as investors buy → owner withdraws proceeds.
- **Broker:** issue referral code → referred user invests → commission appears → withdraw.
- **Liquidity provider:** view market → provide liquidity → fund an exit → see position/returns.
- **Admin:** review KYC exceptions, approve a property, grant a role, execute a distribution, review a withdrawal exception, query audit log.
- **Cross-cutting:** concurrency (no oversell), idempotency (no double-charge), reconciliation green, security negative tests pass.

## Risks / watch-outs
- **Sandbox→production cutover** of providers is a common failure point — verify each webhook and key in production before launch.
- **Don't launch on red reconciliation** or with any remaining fake-success/dead money button — that would recreate the exact problem this whole programme set out to fix.
- Confirm all OPEN DECISIONS (D1–D12) are resolved or their features explicitly disabled (not faked) before go-live.
