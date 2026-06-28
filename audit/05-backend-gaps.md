# 05 — Backend Gap Analysis (prioritized)

The schema exists and is reasonably well-designed; the **server-side logic and the frontend-to-DB wiring are what's missing.** Organized by priority.

---

## P1 — Frontend-to-DB wiring gaps (tables exist, UI ignores them)

These need no new backend service — just connecting existing tables to the UI (plus the P2 functions for writes). Each is a page showing mock data that should read live tables.

| # | Page / component | Currently | Should read/write |
|---|---|---|---|
| 1 | **Marketplace** [Marketplace.tsx:44](src/pages/Marketplace.tsx:44) | hardcoded `allProperties` array | `properties WHERE status IN ('active','funded')` |
| 2 | **PropertyDetails** [PropertyDetails.tsx:38](src/pages/PropertyDetails.tsx:38) | 2 hardcoded objects by id | `properties WHERE id = :id` (+ its documents) |
| 3 | **Developer "Projects"** [DeveloperDashboard.tsx:63](src/pages/DeveloperDashboard.tsx:63) | hardcoded projects | `properties WHERE owner_id = auth.uid()` |
| 4 | **Investor dashboard / ActiveInvestments / Portfolio** | hardcoded holdings & $125,000 | `investments` + `wallets` for the user |
| 5 | **InvestorWallet / transaction history** | hardcoded balance & tx list | `wallets` + `transactions` |
| 6 | **ReturnsTracker** | hardcoded returns | `transactions WHERE type='return'` |
| 7 | **Secondary market (page + tab)** | hardcoded listings | `secondary_listings WHERE status='active'` |
| 8 | **Notifications (bell + NotificationsSection)** | hardcoded marketing copy; bells dead | `notifications WHERE user_id = auth.uid()` |
| 9 | **Family Investment / Beneficiary** | in-memory mock | `family_groups/_members/_transfers/_return_allocations` |
| 10 | **Documents / certificates** | `documentUrl:'#'`, console.log | `documents` + signed storage URLs |
| 11 | **AccountSettings notification prefs** | local state + fake toast | needs a prefs column/table (none exists) |

Also needed at this layer: **route guards** (`<ProtectedRoute requiredRole>`), **removal of the client role-switcher** ([AppSidebar.tsx:369](src/components/layout/AppSidebar.tsx:369)) from production, and a **property review/promotion** path so created drafts can become `active`.

---

## P2 — Missing server-side logic (must be Edge Functions; RLS alone cannot do these safely)

There are **zero edge functions** today (`supabase/functions/` doesn't exist). Each operation below moves money or inventory and must run atomically server-side with the service role, because the client cannot be trusted to debit itself and the steps must all-succeed-or-all-fail.

| # | Operation | Tables touched | Why it MUST be server-side |
|---|---|---|---|
| 1 | **Execute investment** | `wallets` (debit) + `investments` (insert) + `properties.available_units`/`funded_amount` (decrement/increment) + `transactions` (insert) | Atomicity across 4 tables; client must not set its own `amount`/units (today `investments` INSERT only checks `user_id` — [01-schema.md](audit/01-schema.md)); inventory must not oversell |
| 2 | **Wallet deposit (capture)** | `wallets.balance` (credit) + `transactions` | Balance is now client-immutable (UPDATE policy removed, migration 5); only a trusted function/webhook may credit it. Must be driven by a verified payment-gateway webhook, not a client claim |
| 3 | **Wallet withdrawal / payout** | `wallets` (debit) + `transactions` (withdrawal) + payout-provider call | Real money out; needs balance check, idempotency, AML/limit checks, provider settlement |
| 4 | **Returns / payout distribution** | `transactions` (type `return`) + `wallets.total_returns`/`balance` per investor, pro-rata by units | Bulk, money-creating; must be authoritative and auditable; cannot originate from a client |
| 5 | **Secondary-market matching & settlement** | `secondary_listings` + `investments` (transfer units) + `wallets` (buyer debit/seller credit) + `transactions` (fees) | Two-party atomic swap with fees; double-spend/oversell protection |
| 6 | **Referral commissions** | `transactions` (type `referral_commission`) + a (missing) referral model + `wallets` | Money creation tied to verified events; needs a referral table that doesn't exist yet |
| 7 | **Family transfers / allocations** | `family_transfers`, `family_return_allocations`, `family_members.allocated_units` | Moves owned units between sub-accounts; must keep balances consistent |
| 8 | **KYC status callback** | `kyc_verifications.status → verified/rejected` | Must be set by a trusted provider webhook, never the user |
| 9 | **Property promotion** | `properties.status draft→under_review→active` | Governance/compliance gate; not owner-self-serviceable |

Supporting needs: a **financial audit/ledger** approach (append-only `transactions` as the source of truth, with non-negative CHECKs already present on `wallets`), **idempotency keys** on all money endpoints, and **webhook-signature verification** for every provider callback.

---

## P3 — Integrations not yet present (confirmed absent)

None of these exist anywhere in the code (no SDKs in [package.json], no API calls, no edge functions):

| Integration | Evidence of absence | Needed for |
|---|---|---|
| **Payment gateway** (cards/Apple/Google Pay/crypto) | The `payment_method` enum lists visa/mastercard/apple_pay/google_pay/crypto/pronova_token/nova_sukuk, but **no Stripe/PSP/crypto SDK or call exists**; PaymentSection is marketing only ([PaymentSection.tsx:4](src/components/home/PaymentSection.tsx:4)) | deposits, investment charges |
| **Payout / disbursement** | none | withdrawals, returns, commissions |
| **KYC/AML provider** (Sumsub/Onfido/etc.) | KYC only uploads files + sets `submitted`; no provider, no webhook ([KYCVerification.tsx](src/pages/KYCVerification.tsx)) | instant identity verification |
| **Card issuing** (Marqeta/Stripe Issuing) | virtual cards are fabricated in local state ([ProShareCards.tsx:180](src/components/dashboard/ProShareCards.tsx:180)) | real virtual cards |
| **Notifications/email/SMS/WhatsApp** | toggles are cosmetic; "live chat" simulated ([Support.tsx:74](src/pages/Support.tsx:74)); WhatsApp is a `wa.me` link | transactional comms |
| **Document AI / e-sign** | certificates are `#` links | contracts, statements |

---

## P4 — Security review items

What's good already: RLS is **enabled on all 14 tables**; recent migrations removed client wallet-writes, added non-negative wallet CHECKs, tightened `documents` SELECT, restricted `has_role`, and revoked function EXECUTE from anon (see [01-schema.md](audit/01-schema.md)).

Items to address before going live:

1. **`investments` INSERT is unconstrained** — policy is `WITH CHECK (auth.uid() = user_id)` only ([20260113155950…sql:127](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:127)). A crafted client call could insert any `amount`/`units` with no payment. Once investing is built, **revoke direct client INSERT and route through the execute-investment function.** Same logic for `transactions`, `secondary_listings`, `family_*` writes.
2. **`properties` financial columns are client-writable by the owner** — `funded_amount`, `available_units`, `status` have no server guard; an owner could self-mark a property `active`/`funded` or edit funding. Promotion and funding fields should move to server control.
3. **No route guards / client role-switcher** — [App.tsx:72](src/App.tsx:72) (all public) + [AppSidebar.tsx:369](src/components/layout/AppSidebar.tsx:369) (`setUserRole` lets anyone pick a role). Remove the switcher in prod; gate routes by the DB role.
4. **`user_roles` has no INSERT/UPDATE policy** — good (clients can't self-grant), but it means role assignment is a manual SQL task with no admin tooling. Build an admin path (server-side) for granting roles.
5. **`.env` committed** — only `*.local` is gitignored. The anon key is public-by-design, but no `service_role` key or provider secret may ever be added to this client repo; server secrets belong in Edge Function secrets.
6. **Private-bucket `getPublicUrl`** — KYC/avatar URLs are built with `getPublicUrl` against private buckets ([KYCVerification.tsx:137](src/pages/KYCVerification.tsx:137)); use signed URLs. Also confirm KYC documents (sensitive PII) retention/encryption policy.
7. **Audit trail** — once money moves, every wallet/transaction/investment change needs an immutable, server-written ledger entry and webhook verification; today nothing is logged because nothing happens.
8. **Fabricated regulatory claim** — "Regulated by Financial Services Authority" ([Footer.tsx:150](src/components/layout/Footer.tsx:150)) and fake AUM/returns figures must be removed or substantiated before live operation (compliance exposure).
