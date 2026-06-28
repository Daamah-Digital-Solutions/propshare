# Phase 7 — Withdrawals & Payouts (automated)

**Size:** Medium (≈1.5–2 weeks) + **business prerequisite**: payout rails & auto-approval policy (OPEN DECISION **D3**). Delivers automation requirement #4 ([audit/06-automation-gaps.md](../audit/06-automation-gaps.md)).

## Goal
Let users cash out **automatically** within risk limits, debiting the wallet and sending funds via a payout provider, with a flagged **exceptions queue** as the only human path (never the default gate). Replaces dead/fake withdraw buttons across roles.

## Testable outcome ("done when…")
- A withdrawal within policy limits **auto-executes**: wallet debited, payout sent via provider, `transactions(type=withdrawal)` written — **no human step**.
- An over-balance request is rejected `409 INSUFFICIENT_FUNDS`; a request breaching a risk rule lands in the **exceptions queue** for admin review (not all requests).
- Investor/Owner/Broker/LP withdraw buttons — today dead or fake ([InvestorWallet.tsx:234](../src/components/dashboard/InvestorWallet.tsx:234), [OwnerDashboard.tsx:646](../src/pages/OwnerDashboard.tsx:646), [BrokerDashboard.tsx:278](../src/pages/BrokerDashboard.tsx:278), [LiquidityDashboard.tsx:703](../src/pages/LiquidityDashboard.tsx:703)) — perform real withdrawals.

## Dependencies
Phase 4 (wallet/ledger), Phase 6 (so there are returns to withdraw). KYC verified required.

## Backend work
- **`withdrawal_service`** + **payouts integration** (`services/integrations/payouts`): `send()`, `get_status()`.
- New **`withdrawals`** table: `id, user_id, amount, method, destination (tokenized), status[pending|auto_approved|in_review|paid|rejected], provider_payout_id, created_at, resolved_at`.
- Endpoints:
  - `POST /wallet/withdraw` — Auth + `require_kyc_verified` + `Idempotency-Key`. Validate `amount ≤ available (non-held) balance`; move funds to `pending_balance`; apply **auto-approval rules** (limits/velocity/fraud — D3): within rules → execute payout; else → `in_review`. Write ledger + audit.
  - `GET /wallet/withdrawals` — user's withdrawal history.
  - `POST /payments/webhooks/{provider}` (extended) — payout status callbacks → `paid`/`failed`; on fail, return funds to `balance`.
  - Admin exceptions: `GET /admin/withdrawals?status=in_review`, `POST /admin/withdrawals/{id}/approve|reject` — **exception path only**; rejection returns held funds.
- Auto-approval policy engine (configurable thresholds) so the **default is automatic** and humans see only flagged cases (requirement #5).

## DB tables/columns touched / new migrations
- New `withdrawals`. `transaction_type` already has `withdrawal`. `wallets`: debit + pending_balance moves. `transactions`: withdrawal rows. `audit_log`.

## Frontend wiring
- Build the real Withdraw handlers (all currently dead/fake): [InvestorWallet.tsx:234](../src/components/dashboard/InvestorWallet.tsx:234), [OwnerDashboard.tsx:646](../src/pages/OwnerDashboard.tsx:646) (replace fake toast), [BrokerDashboard.tsx:278](../src/pages/BrokerDashboard.tsx:278), [LiquidityDashboard.tsx:703,707](../src/pages/LiquidityDashboard.tsx:703). Wire "Configure Auto-Withdraw" ([OwnerDashboard.tsx:662]) to the policy settings or disable explicitly.
- Show real withdrawal status/history.

## External integrations
- Payout provider (D3): bank transfer / card payout / wallet rails; crypto payout if D4 includes it.

## Test plan
- **Success (automation):** within-limit withdrawal auto-pays; wallet debited once; provider callback marks `paid`.
- **Failure:** over-balance `409`; payout provider failure returns funds to balance; held funds can't be double-withdrawn.
- **Exception path:** a rule-breaching request → `in_review`; admin reject returns funds; approve executes payout. Confirm the **default** path required no human.
- **Idempotency:** replayed withdraw key → one withdrawal; duplicate payout webhook → one settlement.

## Risks / watch-outs
- **Fraud/AML tension with "no humans":** providers/regulators require holds on some payouts; the realistic target is auto-happy-path + exceptions queue (requirement #5's own caveat). Encode limits conservatively.
- **Destination tokenization:** never store raw bank/card data; use the provider's tokenized payout destinations.
- **Double-pay** is catastrophic — idempotency + status reconciliation are mandatory.
