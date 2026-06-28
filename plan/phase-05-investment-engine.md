# Phase 5 — Investment Engine ⚠️ (the core money transaction; highest risk)

**Size:** Large (≈3 weeks). This is the heart of the platform and the riskiest phase. It cannot be split smaller without leaving a half-built money path — the atomic flow (lock → validate → charge → decrement → record → issue → audit) is one indivisible unit. Allocate the most senior engineer + a dedicated reviewer; tests are written first.

## Goal
Implement "buy units" as a single atomic, idempotent, concurrency-safe server transaction, funded by wallet balance or a fresh gateway payment, KYC-gated, with ownership issuance and the full ledger. Replaces the current behavior where investing is an `alert()` or a fake toast and the `investments` table is never written ([audit/03-buttons.md](../audit/03-buttons.md) §B; [audit/01-schema.md](../audit/01-schema.md)).

## Testable outcome ("done when…")
- Buying N units **atomically**: debits the wallet (or confirms a gateway payment), creates the `investments` row, decrements `available_units`, increments `funded_amount` (sets `status=funded` at 0 units), writes ledger rows, and appends to `ownership_ledger`.
- **Concurrency:** firing many parallel buyers at the last available units results in **no oversell** and a balanced ledger; losers get `409 INSUFFICIENT_UNITS`.
- **Guards:** unverified KYC → `403 KYC_REQUIRED`; insufficient funds → `409 INSUFFICIENT_FUNDS`; below-minimum or sold-out → rejected.
- **Idempotency:** replaying the same `Idempotency-Key` returns the original investment, not a second one.
- The portfolio shows the real holding; the property's funding bar reflects the real decrement.

## Dependencies
Phases 2 (KYC gate), 3 (real properties), 4 (wallet + payments + ledger).

## Backend work
- **`/investments/quote`** — Auth. Given `property_id` + `units`, return server-computed breakdown: subtotal (`units × unit_price`), platform fee + management fee **read from the admin-configurable `platform_settings` fee store (D10), with any per-property `properties.fees` override**, Pronova discount (if applicable, D5), total. **No state change. No fee is hardcoded.** (The client never computes price — replaces the client-side calculators [InvestmentCalculator.tsx](../src/components/property/InvestmentCalculator.tsx), [InstallmentCalculator.tsx](../src/components/property/InstallmentCalculator.tsx).)
- **`POST /investments`** — Role:investor + `require_kyc_verified` + `Idempotency-Key`. The atomic flow ([01-architecture.md](01-architecture.md) §5; [BACKEND_SPEC.md](../BACKEND_SPEC.md) §6.1):
  1. Idempotency check (return prior result if replayed).
  2. Authorize (investor + KYC verified).
  3. `SELECT … FOR UPDATE` the property row (+ Redis lock `lock:property:{id}`).
  4. Validate `0 < units ≤ available_units` and `units × unit_price ≥ minimum_investment`.
  5. Price it server-side (fees from the `platform_settings` store + Pronova discount). **This phase seeds `platform_settings` with the default fees (platform 2.5% / mgmt 1.0%) and the read-path; the admin editing UI is built in Phase 13 (D10).**
  6. **Take money:** *wallet path* → ensure `balance ≥ total`, debit; *gateway path* → create `payments` intent, investment `status=pending`, **reserve units with a TTL** and finalize on webhook (release via Phase 13 job if unpaid).
  7. Decrement `available_units`, increment `funded_amount`; set `funded` at 0.
  8. Insert `investments` (`confirmed` for wallet path; `pending` for gateway until webhook).
  9. Write `transactions` (type `investment`) + separate `fee` rows; update `wallet.total_invested`.
  10. Append `ownership_ledger`.
  11. Trigger **broker referral** hook (full logic Phase 11) if `users.referred_by` set.
  12. Side effects: notify + (Phase 12) contract doc.
  13. Audit. Commit.
- **`GET /investments/me`** — portfolio (holdings, status, current value, returns).
- **`GET /investments/{id}`**, **`POST /investments/{id}/cancel`** (cancel a `pending`, release reserved units).
- **Gateway-funded path** reuses Phase 4 `payments` webhook: on `succeeded` for purpose=investment → flip investment `pending→confirmed`, finalize the unit decrement, write ledger.
- **Model-specific investing (the 7 models, D5/D10):** ready-income/portfolio = straight unit buy; **installment** = down payment now + schedule (wire the dead "Pay Now" buttons later); **option** = premium payment + activation deadline; **future** = forward settlement. Implement straight-buy fully here; gate the installment/option/future term-handling on D5 and the model fields from Phase 3 — build the ones whose economics are confirmed, scaffold the rest behind clear `NOT_YET_ENABLED` rather than fake success.
- **`ownership_ledger`** (new, immutable): every unit issuance/transfer/sale, so units always reconcile.

## DB tables/columns touched / new migrations
- New `ownership_ledger`.
- New `platform_settings` (fee store, D10), seeded with default fees + read-path (admin edit UI in Phase 13).
- `investments`: real inserts/updates (status lifecycle).
- `properties`: `available_units`/`funded_amount`/`status` (server-only).
- `wallets`: debit + `total_invested`.
- `transactions`: investment + fee rows.
- `payments`: gateway-funded investments.
- **Lock down direct writes:** revoke/неutralize the unconstrained client `investments` INSERT ability noted in [audit/01-schema.md](../audit/01-schema.md) — all writes go through this service.

## Frontend wiring
- [InvestmentCalculator.tsx:94](../src/components/property/InvestmentCalculator.tsx:94) (`alert(...)`) and [InstallmentCalculator.tsx:181](../src/components/property/InstallmentCalculator.tsx:181) (fake toast): replace with `/investments/quote` (live breakdown) then `POST /investments` with an idempotency key; on gateway path, redirect + poll.
- Sample/advanced "Invest" buttons that are **dead** ([SamplePropertyDetails.tsx:343](../src/pages/SamplePropertyDetails.tsx:343), [AdvancedPropertyPage.tsx:1287](../src/pages/AdvancedPropertyPage.tsx:1287)): wire to the real flow (or `NOT_YET_ENABLED` for unconfirmed models).
- Portfolio/ActiveInvestments/PortfolioOverview: read `/investments/me` (retire mock arrays [ActiveInvestments.tsx:31](../src/components/dashboard/ActiveInvestments.tsx:31), [PortfolioOverview.tsx:21](../src/components/dashboard/PortfolioOverview.tsx:21)).
- Reinvest flow ([ReinvestReturns.tsx:50](../src/components/dashboard/ReinvestReturns.tsx:50), currently in-memory context) re-points to a real investment funded from returns (full reinvest economics with Phase 6/10).

## External integrations
- Payment provider (reused from Phase 4) for gateway-funded purchases. Redis for the per-property advisory lock.

## Test plan ⚠️ (most coverage of any phase)
- **Success:** wallet-funded buy debits + issues + decrements atomically; gateway-funded buy stays `pending` until webhook, then confirms exactly once.
- **Concurrency (must pass):** N parallel buyers vs. the last K units → exactly K units sold, no negative `available_units`, ledger balanced, losers `409`.
- **Failure paths:** unverified KYC `403`; insufficient funds `409`; units > available `409`; amount < minimum `422`; cancel of a confirmed investment rejected; cancel of pending releases units.
- **Idempotency:** same key twice → one investment; duplicate gateway webhook → one confirmation.
- **Reconciliation:** post-run, `property.total_units == available_units + sum(ownership_ledger issued)` and `wallet == sum(ledger)`.

## Risks / watch-outs
- **Oversell / double-spend** is the cardinal risk — locking + idempotency are mandatory and must be load-tested, not just unit-tested.
- **Reserve-with-TTL** for gateway path needs the release job (Phase 13) or units leak; track this dependency.
- **Model economics (D5 still open)**: don't fake unconfirmed models — scaffold and disable. **Fees (D10 — resolved)**: read from the `platform_settings` store (seeded here), never a constant.
- **Float bugs**: enforce Decimal/minor-units in fee math; a single float rounding error compounds across the ledger.
