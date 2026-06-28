# Phase 8 — Secondary Market & Exits

**Size:** Medium-Large (≈2 weeks). A two-party atomic swap — similar correctness bar to Phase 5.

## Goal
Let investors list held units for resale and let buyers purchase them with real settlement (ownership transfer + money movement + fees), and replace the localStorage-only exit flow with real exit/buyback requests. Replaces fake "List"/"Buy" toasts and the dead "Confirm Purchase" ([audit/03-buttons.md](../audit/03-buttons.md) §B; [SecondaryMarket.tsx:326](../src/pages/SecondaryMarket.tsx:326)).

## Testable outcome ("done when…")
- Listing units **locks** the seller's units (can't be double-listed or sold elsewhere); listing appears in the public market.
- A buy **atomically**: debits buyer, credits seller (net of resale fee), transfers ownership in `ownership_ledger` (split the investment as needed), closes the listing (`sold`), writes ledger rows for buyer/seller/platform.
- Concurrent buyers on one listing → exactly one succeeds; the other gets `409`.
- The localStorage exit store ([exitStore.ts](../src/components/exit/exitStore.ts)) is retired; exit requests persist server-side.

## Dependencies
Phase 5 (holdings + ownership ledger), Phase 4 (wallet). KYC required to buy.

## Backend work
- **`secondary_market_service`**: validate seller holdings, lock units, settle atomically.
- Endpoints:
  - `GET /secondary/listings` — Public. Active listings joined to property/units/price. Replaces mock ([SecondaryMarket.tsx:40](../src/pages/SecondaryMarket.tsx:40), [SecondaryMarketTab.tsx:36](../src/components/dashboard/SecondaryMarketTab.tsx:36)).
  - `POST /secondary/listings` — Role:investor. Validate seller actually holds `units_for_sale` unsold units; lock them. Replaces fake [SellUnitsForm.tsx:101](../src/components/marketplace/SellUnitsForm.tsx:101) and [ActiveInvestments.tsx:117](../src/components/dashboard/ActiveInvestments.tsx:117).
  - `DELETE /secondary/listings/{id}` — Owner. Cancel + unlock units.
  - `POST /secondary/listings/{id}/buy` — Role:investor + KYC + `Idempotency-Key`. Lock listing (`FOR UPDATE`); compute price + **resale fee read from the `platform_settings` store (D10), not a constant**; debit buyer; credit seller net; transfer ownership; close listing; ledger + audit. Replaces dead [SecondaryMarket.tsx:326](../src/pages/SecondaryMarket.tsx:326) and fake [SecondaryMarketTab.tsx:117](../src/components/dashboard/SecondaryMarketTab.tsx:117).
- **Exits:** `POST /exits` + `GET /exits/me` to replace [exitStore.ts](../src/components/exit/exitStore.ts) (localStorage). An exit can route to a secondary listing or a liquidity buyback (Phase 9).
- Pricing bounds / lock-up enforcement per **D8**.

## DB tables/columns touched / new migrations
- `secondary_listings`: real lifecycle (active/sold/cancelled, lock units). New `exit_requests` table (replaces localStorage).
- `investments`: split/transfer units. `ownership_ledger`: transfer entries. `wallets`/`transactions`: buyer debit, seller credit, platform fee.

## Frontend wiring
- [SecondaryMarket.tsx](../src/pages/SecondaryMarket.tsx): fetch `/secondary/listings`; build the real "Confirm Purchase" handler ([:326](../src/pages/SecondaryMarket.tsx:326)); apply the (currently unused) search/sort over real data ([:118-119](../src/pages/SecondaryMarket.tsx:118)).
- [SellUnitsForm.tsx](../src/components/marketplace/SellUnitsForm.tsx) + [SecondaryMarketTab.tsx](../src/components/dashboard/SecondaryMarketTab.tsx) + [ActiveInvestments.tsx](../src/components/dashboard/ActiveInvestments.tsx): wire list/sell/buy to real endpoints; retire mock holdings.
- Exit components ([ExitFlowDialog.tsx:91](../src/components/exit/ExitFlowDialog.tsx:91), [ExitRequestsPanel.tsx](../src/components/exit/ExitRequestsPanel.tsx)): replace localStorage store with `/exits`.

## External integrations
- None new (wallet-funded). Redis lock per listing.

## Test plan
- **Success:** list → buy → ownership moves, money moves net-of-fee, listing closes; seller's remaining units correct.
- **Concurrency:** two buyers, one listing → one `sold`, one `409`; no unit duplication.
- **Failure/authz:** can't list units you don't hold; can't buy your own listing (if disallowed by D8); unverified buyer `403`; over-list rejected.
- **Idempotency/reconciliation:** replayed buy → one settlement; units + ledger reconcile after trades.

## Risks / watch-outs
- **Unit accounting under split sells** is fiddly — `ownership_ledger` must remain the single source of truth.
- **Pricing policy (D8)** — free vs bounded, lock-up period — affects validation; resolve before building.
- Same oversell/double-spend class of risk as Phase 5; load-test.
