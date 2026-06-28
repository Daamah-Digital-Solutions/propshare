# Phase 9 — Liquidity Provider Module

**Size:** Medium (≈1.5–2 weeks), **gated on OPEN DECISION D7** (LP economics). Engineering is moderate; the *rules* must be specified by the owner first.

## Goal
Make the liquidity-provider role real: an LP market of buyback/exit opportunities, the ability to deploy capital against them, and live LP positions/returns dashboards. Replaces fully-mock LP screens and fake "Provide Liquidity"/"Confirm Allocation" toasts ([audit/04-role-flows.md](../audit/04-role-flows.md); [LiquidityDashboard.tsx:159](../src/pages/LiquidityDashboard.tsx:159), [LiquidityProviderMarket.tsx:208](../src/pages/LiquidityProviderMarket.tsx:208)).

## Testable outcome ("done when…")
- An LP views real opportunities (exit requests / units needing liquidity), makes an offer that **deploys capital** (wallet debit + position created), and sees it in their positions.
- When an LP funds an exit, the exiting investor is actually paid and ownership transfers (ties into Phase 8 exits).
- LP dashboard returns/exposure are computed from real positions, not hardcoded.

## Dependencies
Phase 5 (units/ownership), Phase 8 (exits/secondary), Phase 4 (wallet). **D7 resolved.**

## Backend work
- **`liquidity_service`** implementing the agreed economics (D7): how LPs price buybacks, what return/yield they earn, exposure limits.
- New **`liquidity_offers`** / **`liquidity_positions`** tables (shape depends on D7).
- Endpoints:
  - `GET /liquidity/market` — Role:liquidity_provider. Opportunities (exit requests, under-funded units). Replaces [LiquidityProviderMarket.tsx:73](../src/pages/LiquidityProviderMarket.tsx:73) mock.
  - `POST /liquidity/offers` — deploy capital against an opportunity (atomic: debit wallet, create position, fund the exit/transfer ownership). Idempotent. Replaces [LiquidityProviderMarket.tsx:208](../src/pages/LiquidityProviderMarket.tsx:208).
  - `GET /liquidity/dashboard` — positions, returns, exposure. Replaces [LiquidityDashboard.tsx:62](../src/pages/LiquidityDashboard.tsx:62) mock.
  - `POST /liquidity/offers/{id}/withdraw` (if positions are exitable per D7).
- LP "Provide Liquidity" (deposit-then-deploy) reuses Phase 4 deposits + Phase 5/8 settlement primitives.

## DB tables/columns touched / new migrations
- New `liquidity_offers`/`liquidity_positions`. `wallets`/`transactions`: capital deploy + returns. `ownership_ledger`/`exit_requests`: when an LP funds an exit.

## Frontend wiring
- [LiquidityDashboard.tsx](../src/pages/LiquidityDashboard.tsx): real positions/returns; wire "Provide Liquidity" ([:159](../src/pages/LiquidityDashboard.tsx:159)) and the dead withdraw buttons ([:703,707](../src/pages/LiquidityDashboard.tsx:703)) (withdraw via Phase 7).
- [LiquidityProviderMarket.tsx](../src/pages/LiquidityProviderMarket.tsx): real opportunities; wire "Confirm Allocation" ([:208](../src/pages/LiquidityProviderMarket.tsx:208)) and dead "Deploy Liquidity"/"Manage" buttons.

## External integrations
- None new (wallet-funded). 

## Test plan
- **Success:** LP offer deploys capital, funds an exit, transfers ownership atomically; position + returns visible.
- **Failure/authz:** non-LP blocked; insufficient LP balance `409`; can't over-commit beyond exposure limits (D7).
- **Idempotency/reconciliation:** replayed offer → one position; ledger + units reconcile after LP-funded exits.

## Risks / watch-outs
- **D7 is a hard gate** — without confirmed economics this phase can't be built correctly; surface early.
- Interplay with Phase 8 exits must be consistent (an exit funded by an LP vs. by a secondary buyer).
