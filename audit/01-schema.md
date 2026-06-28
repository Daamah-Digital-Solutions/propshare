# 01 — Real Database Schema & Backend State

Source of truth: the six SQL files in `supabase/migrations/`, read in chronological order. The generated `src/integrations/supabase/types.ts` (833 lines) matches these migrations exactly (14 tables + the `has_role` function).

## Backend facts established first

- **Edge functions: NONE.** `supabase/functions/` does not exist. **No server-side business logic exists anywhere.** Every database write the app performs comes directly from the browser client under RLS. There is no place today where money-moving logic (debit + invest + decrement units atomically) could run safely.
- **Project wiring:** `.env` sets `VITE_SUPABASE_PROJECT_ID="mgmorbqoljfwyrwxlymd"`, `VITE_SUPABASE_URL="https://mgmorbqoljfwyrwxlymd.supabase.co"`, and `VITE_SUPABASE_PUBLISHABLE_KEY=` an **anon** JWT (role `anon`, exp 2036). `supabase/config.toml` confirms `project_id = "mgmorbqoljfwyrwxlymd"`.
- **Security concern — `.env` is committed.** `.gitignore` only ignores `*.local`, **not `.env`** (verified). The anon publishable key is designed to be public, so this is low-severity *for that key*, but the pattern is unsafe: any future `service_role` key or provider secret placed in `.env` would be committed. Server secrets must never live in this client repo — they belong in Edge Function secrets / a server vault.
- **OAuth** runs through Lovable Cloud's auth wrapper ([src/integrations/lovable/index.ts](src/integrations/lovable/index.ts)), which calls `supabase.auth.setSession()` after the provider round-trip.

## Enums (migration 1, [20260113155950…sql:2-7](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:2))

| Enum | Values |
|---|---|
| `app_role` | investor, owner, broker, liquidity_provider, admin |
| `kyc_status` | pending, submitted, verified, rejected |
| `property_status` | draft, under_review, active, funded, closed |
| `payment_method` | visa, mastercard, apple_pay, google_pay, crypto, pronova_token, nova_sukuk |
| `investment_status` | pending, confirmed, active, completed, cancelled |
| `transaction_type` | investment, withdrawal, return, fee, referral_commission |

> Note: there is a `developer`/`guest` notion in the **frontend** `UserRole` type ([AuthContext.tsx:5](src/contexts/AuthContext.tsx:5)) that does **not** exist in the DB `app_role` enum. `guest` is the default UI state; `developer` has no DB role and the DeveloperDashboard is just the UI shown to an owner.

## Tables (14)

All tables have RLS **enabled**. Columns abbreviated; FKs and key constraints noted.

### `profiles` ([:10-24](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:10))
`id` (PK, FK→auth.users, cascade), email, full_name, phone, avatar_url, created_at, updated_at.
RLS: SELECT/UPDATE/INSERT all gated `auth.uid() = id`. **Read/write: self only.**

### `user_roles` ([:27-37](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:27))
id, user_id (FK→auth.users), role (`app_role`), UNIQUE(user_id, role).
RLS: **SELECT only** ("Users can view own roles"). **No INSERT/UPDATE/DELETE policy → no client can assign roles.** Roles can only be set via the SQL console / a service-role key. There is no admin UI to grant roles (see [02-pages.md](audit/02-pages.md)).

### `kyc_verifications` ([:53-67](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:53))
id, user_id (FK, UNIQUE), status (`kyc_status` default 'pending'), id_type, id_number, id_document_url, address_document_url, selfie_url, submitted_at, verified_at, rejection_reason, timestamps.
RLS: SELECT/INSERT/UPDATE gated to `auth.uid() = user_id`. **Self can move own status to `submitted`; nothing in the policies or code moves it to `verified`** → approval is a manual DB edit. There is **no automated KYC provider** anywhere (see [06-automation-gaps.md](audit/06-automation-gaps.md)).

### `properties` ([:77-101](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:77))
id, owner_id (FK→auth.users, set null), title, description, location, property_type, status (`property_status` default 'draft'), total_value, minimum_investment (default 500), target_yield, **funded_amount** (default 0), total_units (default 100), **available_units** (default 100), unit_price, spv_name, spv_registration, legal_structure, expected_completion, images (text[]), documents (jsonb), fees (jsonb default `{platform_fee:2.5, management_fee:1.0}`), timestamps.
RLS: SELECT "Anyone can view active properties" `USING (status='active' OR status='funded')`; "Owners can manage own properties" `FOR ALL USING (auth.uid()=owner_id)`.
**Consequence:** an owner can insert/update their own property (the form does, with `status:'draft'`), but the public can only ever *see* `active`/`funded`. There is no policy or function that promotes `draft → under_review → active`, and no admin UI to do so. **`funded_amount`/`available_units` are plain client-writable columns with no server logic guarding them** — there are no CHECK constraints for non-negativity and no atomic decrement on investment.

### `investments` ([:109-122](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:109))
id, user_id (FK), property_id (FK), units, amount, status (`investment_status` default 'pending'), payment_method, payment_reference, pronova_discount_applied, timestamps.
RLS: SELECT/INSERT/UPDATE gated `auth.uid() = user_id`. **CRITICAL:** the INSERT policy is `WITH CHECK (auth.uid() = user_id)` only — a client could insert an investment of **any `amount`/`units` for free**, with no wallet debit and no `available_units` decrement, because that logic lives nowhere. (Today no UI does this — investing is entirely mock — but the table is wide open to a crafted client call.) **No code references this table** (grep: zero `from("investments")`).

### `wallets` ([:131-145](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:131))
id, user_id (FK, UNIQUE), balance, pending_balance, total_invested, total_returns, timestamps; all default 0.
RLS originally allowed self-UPDATE; **migration 5 removed it** (see below). **No code references this table** (grep: zero `from("wallets")`). A wallet row is auto-created on signup by the `handle_new_user` trigger, then never read or changed by any code → every user's balance is permanently $0 in the database. (The "$125,000 balance" shown in dashboards is hardcoded UI, e.g. [OwnerDashboard.tsx:472].)

### `transactions` ([:148-158](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:148))
id, user_id (FK), type (`transaction_type`), amount, reference_id, description, payment_method, status (text default 'pending'), created_at.
RLS: SELECT + INSERT gated to self. **No code references it.**

### `secondary_listings` ([:166-175](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:166))
id, seller_id (FK), investment_id (FK), units_for_sale, price_per_unit, status (text default 'active'), created_at, sold_at.
RLS: public SELECT of `active`; seller manages own. **No code references it** — the "Create Listing"/"Buy Units" flows are fake (see [03-buttons.md](audit/03-buttons.md)). No matching/escrow/settlement logic exists.

### `notifications` ([:183-191](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:183))
id, user_id (FK), title, message, type, read, created_at. RLS: self SELECT/UPDATE. **No code references it** — every "notification" in the UI is hardcoded marketing copy, and the bell icons are dead.

### `documents` ([:199-208](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:199))
id, user_id, property_id, investment_id (all FK), title, type, file_url, created_at. RLS tightened in migration 5 (below). **No code references it** — document download buttons are dead/stubs.

### `family_groups`, `family_members`, `family_transfers`, `family_return_allocations` ([20260113174310…sql](supabase/migrations/20260113174310_e8b589fc-2098-4fa0-a40e-0bc4d01c261a.sql))
Full schema for family/beneficiary investing with RLS scoped to the group `owner_id`. **No code references any of these tables** — the entire Family Investment / Beneficiary Gifting UI is in-memory mock ([FamilyInvestment.tsx], [FamilyBeneficiaryGifting.tsx]).

## Functions & triggers (SECURITY DEFINER)

- **`has_role(_user_id, _role)`** — SECURITY DEFINER. Originally a simple existence check ([:40-50](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:40)); **tightened in migration 5** to return false unless the caller is the subject or an admin ([20260511081107…sql:44-64](supabase/migrations/20260511081107_bb7cab96-e838-455e-bb18-495cce4ff231.sql:44)). **Not called anywhere in the frontend** (AuthContext reads `user_roles` directly).
- **`handle_new_user()`** — SECURITY DEFINER trigger on `auth.users` insert; creates `profiles` + `wallets` + `kyc_verifications` rows ([:216-237](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:216)). This is the one piece of automatic server-side provisioning that works.
- **`update_updated_at()`** — timestamp trigger; `search_path` fixed and switched to `SECURITY INVOKER` in migration 2 ([20260113160025…sql](supabase/migrations/20260113160025_cf8d15e3-3784-430d-adf9-db90005ed906.sql)).

## Storage buckets

`documents` (private), `kyc-documents` (private), `property-images` (public), `avatars` (public, added migration 5). Upload/select policies scoped by `auth.uid()` folder prefix ([:256-267](supabase/migrations/20260113155950_46b0f596-a274-4215-9193-049359441a51.sql:256); property-image write policies in [20260113160512…sql](supabase/migrations/20260113160512_278c4530-096a-4572-bc1f-80e1e3a0834d.sql)).
> Minor bug: KYC and avatar code call `getPublicUrl()` on **private** buckets (`kyc-documents`) — e.g. [KYCVerification.tsx:137](src/pages/KYCVerification.tsx:137) — so the stored URL will not resolve without a signed URL. Functionally the upload succeeds; the saved link won't display. NEEDS later fix (not in scope to fix now).

## What the security-tightening migrations changed (migrations 5 & 6)

Migration 5 ([20260511081107…sql](supabase/migrations/20260511081107_bb7cab96-e838-455e-bb18-495cce4ff231.sql)):
1. **Documents SELECT tightened** ([:3-26](supabase/migrations/20260511081107_bb7cab96-e838-455e-bb18-495cce4ff231.sql:3)) — replaced the loose "any row with a property_id is visible" policy with ownership/investment-scoped access.
2. **Wallets: removed client UPDATE entirely** ([:29](supabase/migrations/20260511081107_bb7cab96-e838-455e-bb18-495cce4ff231.sql:29)) and added **non-negative CHECK constraints** on balance/pending/total_invested/total_returns ([:37-41](supabase/migrations/20260511081107_bb7cab96-e838-455e-bb18-495cce4ff231.sql:37)). Good hardening — but it also means **only a SECURITY DEFINER function or service role can ever change a balance, and none exists**, so wallets are now immutable-at-zero until that server logic is built.
3. **`has_role` restricted** to self/admin ([:44-64](supabase/migrations/20260511081107_bb7cab96-e838-455e-bb18-495cce4ff231.sql:44)).
4. **Avatars bucket** added; property-image/avatar **listing** policies narrowed so buckets can't be enumerated ([:102-125](supabase/migrations/20260511081107_bb7cab96-e838-455e-bb18-495cce4ff231.sql:102)).

Migration 6 ([20260511081145…sql](supabase/migrations/20260511081145_e4f21a8d-a980-4ece-b206-e57bec73033b.sql)):
- Dropped broad avatar listing policy; **REVOKEd EXECUTE** on `has_role`, `handle_new_user`, `update_updated_at` from PUBLIC/anon (and granted `has_role` to `authenticated`). Sensible least-privilege hardening.

**Summary of security posture:** RLS is enabled on all 14 tables and the recent migrations show real, competent hardening of *access*. The gap is not RLS coverage — it's that **the money tables (investments, wallets, transactions, secondary_listings) have no server-side logic to enforce financial invariants** (atomic debit/credit, unit inventory, payout integrity). RLS can authorize *who* touches a row; it cannot guarantee *that an investment debits a wallet and decrements units in one transaction*. That requires the Edge Functions that do not yet exist.
