# CapiMax PropShare — Resolved Open Decisions (Owner Sign-off)

This memo resolves the OPEN DECISIONS from `plan/00-overview.md`. Update the affected plan files accordingly — most importantly `plan/01-architecture.md` and `plan/phase-01-*.md` (identity/auth/RBAC) and `plan/phase-04-*.md` (payments). Where a decision changes a locked architectural assumption, note the change explicitly in `00-overview.md`.

## Resolved

**D2 — Payment provider (deposits/charges):** Use **Stripe** for traditional card/payment rails. Wire deposits via Stripe in Phase 4. Balance changes occur ONLY on a verified Stripe webhook (no client-confirmed payments).
> Watch-out to verify in Phase 4: confirm Stripe supports the target market for both charges AND payouts (Stripe payouts are not available in every GCC country — if not, Phase 7 withdrawals need an alternate rail). Flag as a Phase-4/Phase-7 verification item, not a blocker.

**D4 — Crypto as a v1 payment method:** YES. Crypto is a core part of v1. Use **OnePayments** as the crypto payment/withdrawal provider. Integrate in Phase 4 (deposits) and Phase 7 (crypto withdrawals — note the UI already shows a "Crypto Withdrawals" item under the LP wallet).
> Watch-out to verify in Phase 4: confirm the exact OnePayments product and that it exposes webhooks for deposit confirmation and withdrawal status (the whole money model depends on webhook-driven, server-authoritative balance changes). Treat as a verification item.

**D6 — `developer` vs `owner`:** They are the **same backend role**. `developer` is a frontend label/alias of `owner`; `app_role` gains no new `developer` value. Reconcile the owner/developer listing UX in Phase 3 (the working create flow currently lives on the Developer dashboard's `PropertyCreationForm`; the Owner dashboard's own "List a Property" form is dead and must be wired to the same endpoint).

**D9 — Virtual cards:** **Deferred out of v1.** Phase 11 keeps referral/commission logic but drops card issuing from v1 scope. Hide or disable the "Virtual Cards" tab in the UI for v1 (do not leave a fake-success surface). Revisit post-launch.

**D10 — Fee schedule:** Fees must be **admin-configurable from the admin panel**, not hardcoded. Introduce a fee-settings store the admin can edit (platform fee, management fee, resale/transfer fees). Phases 5 (investment) and 8 (secondary market) must READ fees from this setting, not a constant. Ship with sensible defaults (platform 2.5% / management 1.0%) so nothing blocks on a pending number. Build the admin editing UI in Phase 13; seed the setting + read-path earlier where fees are first used.

**D11 — Contract/SPV document templates:** **Deferred out of v1** (tied to deferred document generation). Phase 12 scope drops generated contracts from v1; keep the notifications/comms parts. Revisit post-launch.

**D12 — Multi-role users & active-role switching:** **Scenario B.** A user may hold MORE THAN ONE role and may switch between **only the roles they are actually authorized for**. This changes the identity model and must be reflected in Phase 1 and the architecture:

1. **Roles are many-to-many.** `user_roles` represents a set of authorized roles per user (not one role). The JWT/session carries the authorized-role set.
2. **"Active role" concept.** The session has a current active role chosen from the authorized set. All authorization checks evaluate against the active role AND verify it is within the authorized set.
3. **The existing UI role-switcher dropdown (`AppSidebar.tsx:369`) is repurposed, not kept as-is.** It must (a) display ONLY the roles the user is authorized for, fetched from the backend; (b) call a backend "switch active role" endpoint; (c) the backend MUST reject any switch to a role not in the user's authorized set, even if the request is tampered with. Security lives in the backend, not in hiding the dropdown. The current "anyone can assume any role" behavior is removed entirely.
4. **Guest** is not a real authenticated role — it is the unauthenticated/public browsing state. Treat it as "no session," not as a switchable role.
5. **Granting a new role** to an existing user (e.g. an investor who also wants to become an owner): define how this happens. OPEN SUB-DECISION — is it automatic on first use, or admin-approved? Default recommendation: self-serve for `owner`/`investor`, admin-approved for `broker`/`liquidity_provider`/`admin`. Confirm before Phase 1 build.

> Impact: Phase 1 grows beyond a single-role auth system. The sidebar's per-role menu (shown in the owner's screenshots: Guest / Investor / Property Owner / Broker / Liquidity Provider each render a different menu) is driven by the active role, gated by the authorized set. This is more work than single-role; size Phase 1 accordingly.

## Still open (not blocking now; resolve before the noted phase)

- **D1 — KYC/AML provider:** still to confirm (Sumsub was the owner's earlier preference). Needed by Phase 2.
- **D3 — Payout rails + auto-approval limits + fraud-hold thresholds:** needed by Phase 7. (Tied to the Stripe-payouts-in-region check above.)
- **D5 — Pronova token & Nova Sukuk mechanics:** needed by Phase 5 (discount) / Phase 4 (as a method). Business/economics decision — owner to supply.
- **D7 — Liquidity-provider economics (buyback rules, pricing, returns):** needed by Phase 9. Business decision — owner to supply.
- **D8 — Secondary-market pricing bounds & lock-up/holding period:** needed by Phase 8. Business decision — owner to supply.

Scaffold anything dependent on D5/D7/D8 as `NOT_YET_ENABLED` rather than guessing the economics.
