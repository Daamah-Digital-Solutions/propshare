# Phase 4 — Wallet & Deposits

**Size:** Large (≈2.5 weeks) — **two pay-in rails in v1**: **Stripe** for cards (D2) and **OnePayments** for crypto (D4, core to v1). + **business prerequisite**: a Stripe merchant account and a OnePayments account. Engineering is bounded; the merchant/underwriting onboarding is the long-pole and is a business/legal task.

## Goal
Stand up the real internal wallet and the first money-in paths: deposits funded by **Stripe** (cards) and **OnePayments** (crypto), credited **only on a verified webhook**, with an append-only ledger. This is the foundation every later money phase (invest, returns, withdraw, secondary) depends on.

## Testable outcome ("done when…")
- A test-card deposit moves through the provider and **credits the wallet only after a signature-verified webhook** (not on browser redirect); the SPA shows the DB balance.
- A **replayed webhook does not double-credit** (idempotent).
- Every balance change has a matching `transactions` row; `wallet.balance == sum(ledger)` holds.
- The investor wallet's Deposit button — currently **dead, no handler** ([InvestorWallet.tsx:190](../src/components/dashboard/InvestorWallet.tsx:190)) — performs a real deposit.

## Dependencies
Phases 1 (auth) and 3 (so the app has real users/data). KYC (2) recommended before allowing deposits, per business policy.

## Backend work
- **`wallet_service`** (the only code allowed to mutate balances; recall the client UPDATE policy was removed — [audit/01-schema.md](../audit/01-schema.md)): credit/debit always inside a tx with a matching ledger row; honors the non-negative CHECKs.
- **`payment_service` + two payments adapters behind one interface** (`services/integrations/payments`): `stripe` (cards — D2) and `onepayments` (crypto — D4), each implementing `create_intent()`, `verify_webhook()`. The `payment_method` enum already distinguishes `visa`/`mastercard`/`apple_pay`/`google_pay` (Stripe) from `crypto` (OnePayments).
- Endpoints:
  - `GET /wallet/me` — balance, pending, total_invested, total_returns. Replaces hardcoded balances ([InvestorWallet.tsx:38](../src/components/dashboard/InvestorWallet.tsx:38), [OwnerDashboard.tsx:472]).
  - `POST /wallet/deposit` — create a deposit intent (purpose=deposit); returns provider checkout/redirect. Requires `Idempotency-Key`.
  - `GET /wallet/transactions` — paginated ledger.
  - `POST /payments/intent` — generic intent creation (reused by Phase 5 gateway-funded invest).
  - `POST /payments/webhooks/{provider}` — **Public, signature-verified.** One route per provider (`/payments/webhooks/stripe`, `/payments/webhooks/onepayments`). Update `payments`; on `succeeded` for a deposit → credit wallet + write `transactions(type=deposit)` + notify + audit. Idempotent on `provider_payment_id`. (Stripe: verify the `Stripe-Signature` HMAC; OnePayments: verify per its webhook scheme — see watch-out.)
  - `GET /payments/{id}` — status (SPA polls after redirect).
- **`payments` table** (new): `id, user_id, provider, provider_payment_id, amount, currency, status, purpose, related_investment_id, idempotency_key (unique), raw_payload, timestamps`.
- **Migration: add `deposit` to the `transaction_type` enum** (confirmed gap — [BACKEND_SPEC.md](../BACKEND_SPEC.md) §6.2; the enum currently has only investment/withdrawal/return/fee/referral_commission — [audit/01-schema.md](../audit/01-schema.md)).

## DB tables/columns touched / new migrations
- New `payments` table; new `idempotency_keys` (if not Redis-only).
- `transaction_type` enum: add `deposit`.
- `wallets`: balance/pending/total_invested mutations (server-only).
- `transactions`: append-only writes.

## Frontend wiring
- [InvestorWallet.tsx](../src/components/dashboard/InvestorWallet.tsx): build the Deposit handler ([:190](../src/components/dashboard/InvestorWallet.tsx:190)) → `POST /wallet/deposit` → redirect → poll `/payments/{id}`; show real balance + transaction history from `/wallet/me` + `/wallet/transactions` (retire mock arrays [:38-99](../src/components/dashboard/InvestorWallet.tsx:38)). (Withdraw stays disabled until Phase 7.)
- Retire hardcoded balances anywhere they appear (owner/broker/LP wallet cards) — those withdraw/deposit actions are wired in their own phases, but balances become live now.

## External integrations
- **Stripe** (D2) — cards/Apple Pay/Google Pay; requires merchant account + webhook secret.
- **OnePayments** (D4) — crypto deposits (and withdrawals in Phase 7); requires account + webhook configuration.

## Test plan
- **Success:** deposit intent → sandbox success webhook → balance credited exactly once; ledger row written; `/wallet/me` reflects it.
- **Failure:** webhook `failed`/`cancelled` → no credit; over-... n/a for deposit; balance never goes negative (CHECK).
- **Idempotency/security:** duplicate webhook (same `provider_payment_id`) credits once; forged webhook rejected; client cannot set its own amount (server/intent authoritative).
- **Reconciliation:** after a batch of deposits, `wallet == sum(ledger)` for every user.

## Risks / watch-outs
- ⚠️ **Verify (per resolved-decisions): Stripe coverage in the target GCC market for both charges AND payouts.** Stripe payouts are not available in every GCC country — if charges work but payouts don't, **Phase 7 withdrawals need an alternate fiat rail** (OnePayments covers crypto out, not fiat). Confirm in this phase; flag to Phase 7. Not a blocker for deposits.
- ⚠️ **Verify (per resolved-decisions): the exact OnePayments product exposes webhooks** for deposit confirmation AND withdrawal status — the whole money model depends on webhook-driven, server-authoritative balance changes. If OnePayments lacks reliable webhooks, the crypto path must be redesigned.
- **Merchant/account onboarding is the long pole** (weeks, underwriting; handled by business per the constraint, but the accounts must exist to test live).
- **Currency/FX** must be decided before storing amounts; pick the minor-unit convention now (crypto adds decimals/precision considerations beyond fiat cents).
- **Webhook security** is critical — verify signatures for both providers; never credit on redirect.
- `pronova_token`/`nova_sukuk` as deposit methods depend on D5 (mechanics, still open) — model as internal balances or scaffold `NOT_YET_ENABLED`.
