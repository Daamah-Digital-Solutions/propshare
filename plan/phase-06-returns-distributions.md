# Phase 6 — Returns & Distributions

**Size:** Medium-Large (≈2 weeks). Money-creating and bulk — high correctness bar, but bounded once the ledger/ownership primitives from Phase 5 exist.

## Goal
Distribute returns (rental yield, capital appreciation) **automatically and pro-rata by units held**, crediting investor wallets, writing the ledger, and supporting scheduled recurring payouts. Replaces hardcoded returns displays ([ReturnsTracker.tsx:27,74](../src/components/dashboard/ReturnsTracker.tsx:27)).

## Testable outcome ("done when…")
- An admin (or scheduled job) runs a distribution for a property/period → each holder is credited **exactly their pro-rata share by units held during the period**; `wallet.total_returns` and `balance` increase; `transactions(type=return)` written.
- **Re-running the same distribution pays no one twice** (idempotent per distribution).
- Totals reconcile: `sum(payout_items.net) + fees == distribution.total_amount`.
- The Returns screen shows real distribution history.

## Dependencies
Phase 5 (holdings + `ownership_ledger` + wallet/ledger).

## Backend work
- **`distribution_service`** computing pro-rata shares from an `ownership_ledger` snapshot for the period (handles mid-period buys correctly).
- New tables: **`distributions`** (`id, property_id, period_start, period_end, total_amount, type[rental_yield|capital_appreciation], status, executed_at`) and **`payout_items`** (`id, distribution_id, investment_id, user_id, units, gross_amount, fees, net_amount, status`).
- Endpoints:
  - `POST /admin/distributions` — Admin. Create + execute a distribution (idempotent per distribution id). Body: property_id, period, total_amount, type.
  - `GET /admin/distributions`, `GET /admin/distributions/{id}`.
  - `GET /investments/me/returns` (or extend `/investments/me`) — investor's return history.
- For each holder: `net = gross − applicable fees`; credit wallet; increment `total_returns`; write `transactions(type=return)`; apply Pronova/family bonus rates where relevant (D5; family interplay finalized Phase 10).
- **Scheduled distributions** (job defined Phase 13, logic here): recurring rental-yield payouts per a property schedule.

## DB tables/columns touched / new migrations
- New `distributions`, `payout_items`.
- `wallets`: credit balance + total_returns. `transactions`: return rows. `ownership_ledger`: read snapshot.

## Frontend wiring
- [ReturnsTracker.tsx](../src/components/dashboard/ReturnsTracker.tsx): retire mock ([:27-71](../src/components/dashboard/ReturnsTracker.tsx:27)); read real return history; wire the dead "Export"/"Download Statement" buttons ([:134](../src/components/dashboard/ReturnsTracker.tsx:134),[225](../src/components/dashboard/ReturnsTracker.tsx:225)) to a real statement (statement generation Phase 12).
- Wallet/portfolio totals reflect real `total_returns`.
- Admin UI (built fully Phase 13) gets the distribution trigger.

## External integrations
- None new (payouts to *external* bank accounts are Phase 7; here returns land in the internal wallet).

## Test plan
- **Success:** distribution credits each holder pro-rata; partial-period holdings weighted correctly; totals reconcile to the distributable amount.
- **Idempotency:** re-execute same distribution → no double credit.
- **Failure:** distribution on a property with zero holders → no-op, clean; rounding handled so `sum(net)+fees == total` exactly (no lost/created cents).
- **Reconciliation:** post-distribution, every credited wallet still equals its ledger sum.

## Risks / watch-outs
- **Rounding/remainder allocation** must be deterministic (assign the residual cent by a fixed rule) or reconciliation drifts.
- **Snapshot correctness** for mid-period buys/sells — define the holding-period rule with the owner.
- Capital-appreciation realization rules differ from rental yield — confirm with owner (relates to D7/model economics).
