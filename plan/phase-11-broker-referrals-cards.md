# Phase 11 — Broker & Referrals (Virtual Cards deferred from v1 — D9)

**Size:** Medium (≈1.5 weeks). **D9 resolved: virtual cards are deferred out of v1** — this phase is broker/referral logic only; the Virtual Cards UI is hidden/disabled (no fake surface), revisited post-launch.

## Goal
Make the broker role real: referral attribution → commissions → withdrawable balance. Replaces the all-mock broker dashboard ([audit/04-role-flows.md](../audit/04-role-flows.md)). **Virtual cards are explicitly out of v1** — the fabricated-card UI ([ProShareCards.tsx:180](../src/components/dashboard/ProShareCards.tsx:180)) is disabled rather than wired.

## Testable outcome ("done when…")
- A user who signed up with a broker's referral code, on making a confirmed investment, generates a **broker commission** (`transactions(type=referral_commission)`); the broker sees it and can withdraw it (Phase 7).
- Broker dashboard referrals/commission figures are live, not hardcoded ([BrokerDashboard.tsx:34-71](../src/pages/BrokerDashboard.tsx:34)).
- The **Virtual Cards tab/feature is hidden or disabled** with a clear "coming after launch" state — **no fabricated PANs or fake-success card actions remain anywhere** ([ProShareCards.tsx](../src/components/dashboard/ProShareCards.tsx), [VirtualCardRequest.tsx](../src/components/dashboard/VirtualCardRequest.tsx)).

## Dependencies
Phase 1 (referral capture at signup — `users.referred_by`), Phase 5 (commission triggered on invest), Phase 7 (broker withdrawal). (Cards: deferred — D9.)

## Backend work
- **`referral_service`**:
  - Referral capture: `users.referred_by` set at registration (Phase 1) via referral code; `GET /broker/referral-code` to issue a broker's code.
  - On confirmed investment (Phase 5 hook), compute commission (rate per D10) → create `referrals` row + `transactions(type=referral_commission)` → credit broker wallet. Idempotent per investment.
  - Endpoints: `GET /broker/dashboard` (referrals, pending/earned commission), `GET /broker/referrals`.
- New **`referrals`** table: `id, broker_id, referred_user_id, investment_id, commission_rate, commission_amount, status, created_at`. Commission rate read from the `platform_settings` store (D10).
- **Cards: NOT built in v1 (D9).** No `card_service`, no issuing integration, no `cards` table. If any `/cards` route is wanted as a placeholder it returns `NOT_ENABLED`; otherwise the feature is simply absent and hidden in the UI. Revisit post-launch.

## DB tables/columns touched / new migrations
- New `referrals`; `transaction_type` already has `referral_commission`. `wallets`/`transactions`: commission credit. `users.referred_by` (added Phase 1). **No `cards` table (deferred — D9).**

## Frontend wiring
- [BrokerDashboard.tsx](../src/pages/BrokerDashboard.tsx): real referrals/commission from `/broker/dashboard`; wire dead "New Referral" (share referral code), "Download Commission Report", and "Withdraw Funds" ([:278](../src/pages/BrokerDashboard.tsx:278)) buttons.
- [ProShareCards.tsx](../src/components/dashboard/ProShareCards.tsx) + [VirtualCardRequest.tsx](../src/components/dashboard/VirtualCardRequest.tsx): **hide/disable the Virtual Cards tab** (e.g. behind a "coming after launch" placeholder) and **remove the fabricated PAN reveal** ([ProShareCards.tsx:180](../src/components/dashboard/ProShareCards.tsx:180)) — no fake-success card surface ships.

## External integrations
- None in v1 (card issuer deferred — D9).

## Test plan
- **Success:** referred investor's confirmed buy creates exactly one commission; broker balance increases; broker can withdraw.
- **Failure/idempotency:** non-referred buy creates no commission; re-processing an investment doesn't double-pay commission; self-referral blocked.
- **Cards:** verify the Virtual Cards UI is hidden/disabled and that **no fabricated card numbers or fake card actions exist anywhere** in the build.

## Risks / watch-outs
- **Commission timing:** define whether commission is on confirmed investment vs. funded vs. first return — affects when/if it's clawed back on cancellation (relates to the fee/commission settings, D10).
- **Cards deferral must be clean:** disable, don't fake. Leaving the current fabricated-PAN UI live would recreate exactly the audited problem.
