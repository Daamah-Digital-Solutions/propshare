# CapiMax PropShare — Backend Build Roadmap

**Goal:** Turn the existing React/TypeScript frontend (currently running mostly on mock data) into a fully functional, automated investment platform with a dedicated Python backend. **Nothing in the existing frontend scope is to be removed** — every role, page, and function must end up working for real.

**Stack decision (set by the project owner):** A standalone Python backend (FastAPI recommended for async + automatic OpenAPI docs). **Reuse the existing Supabase Postgres database** — it is a standard Postgres instance, and the schema + migrations already built are valuable. Connect Python to it directly (e.g. via SQLAlchemy + Alembic for future migrations). Supabase Auth, RLS, and Storage will be *replaced* by Python-side equivalents; the developer should be aware this is deliberate and is re-implementation work.

**Sequencing principle:** The full platform is the target, but it is built in phases so that each phase produces something testable end-to-end. This is not a reduction of scope — it is an ordering of scope to reduce risk. Do not move to the next phase until the current one is verified working.

> **Prerequisite:** Run the audit prompt first (`capimax-audit-prompt.md`). The roadmap below assumes the audit's findings are in hand, especially the page/button/role-flow reports.

---

## Phase 0 — Foundations & Decisions (before any feature code)

These are blockers. Several are commercial/legal, not technical, and must be decided by the business, not the developer.

1. **Confirm the database strategy.** Point the Python backend at the existing Supabase Postgres. Export the current schema (the 14 tables) and bring it under Alembic so future changes are version-controlled. Decide what to do with the existing RLS policies (in a Python API model, authorization moves into the application layer — RLS becomes a defense-in-depth layer, not the primary gate).
2. **Choose and open accounts for external providers** (these cost money and require business verification — owner action):
   - **KYC/AML:** Sumsub (owner's stated preference) or equivalent.
   - **Payments / payouts:** Stripe (or a provider that supports the target market and instant payouts).
   - **Crypto wallets/payments:** a regulated provider if crypto is in scope — confirm whether it actually needs to be in v1.
   - **Notifications:** email (e.g. Resend/SendGrid) and WhatsApp (e.g. Twilio) if required.
3. **Resolve the legal/licensing question.** Fractional real-estate investment handling client funds (and crypto) commonly requires financial licensing and AML compliance depending on jurisdiction. This must be confirmed with a qualified lawyer in the target country **before** money flows. This is outside the developer's scope but blocks go-live.
4. **Define the security model:** JWT-based auth, password hashing (argon2/bcrypt), role-based access control mapping to the existing `app_role` enum (`investor`, `owner`, `broker`, `liquidity_provider`, `admin`), and a mandatory **audit log** for every financial state change.
5. **Environment & secrets:** rotate the Supabase keys currently committed in `.env`, move all secrets to a proper secrets manager, and set up dev/staging/prod environments.

---

## Phase 1 — Core Identity & Account (testable: a user can register, log in, and have a profile + empty wallet)

- Auth endpoints: register, login, refresh token, logout, password reset.
- On registration: create `profiles` row, assign default `investor` role in `user_roles`, and create an empty `wallets` row (balance 0).
- Profile read/update (maps to the existing `AccountSettings` page).
- RBAC middleware enforcing roles on every protected endpoint.
- Wire the frontend `AuthContext` and `AccountSettings` to the new API.
- **Audit log table** created and writing from day one.

**Done when:** a real user can sign up, log in, edit their profile, and see a (zero-balance) wallet — all persisted.

---

## Phase 2 — KYC Automation (testable: a user submits KYC and gets an automatic decision)

- Integrate the chosen KYC provider (Sumsub). Use their hosted/SDK flow so document capture and liveness happen provider-side.
- Endpoint to initiate a KYC session; **webhook** endpoint to receive the provider's automatic decision and update `kyc_verifications.status` (`pending` → `submitted` → `verified`/`rejected`) with no manual step.
- Gate investment actions on `verified` status.
- Wire the `KYCVerification` page to the provider flow.

**Done when:** a user completes KYC and the status flips automatically via webhook, with no back-office action.

---

## Phase 3 — Properties: Real Data End-to-End (testable: an owner creates a property and it appears live in the marketplace)

This closes the **single biggest gap** found in the audit: the marketplace currently reads mock data (`sampleProperties.ts`) while property creation writes to the real `properties` table — they are disconnected.

- CRUD endpoints for `properties` with status workflow (`draft` → `under_review` → `active` → `funded` → `closed`).
- Owner/developer property-creation endpoint (wire `PropertyCreationForm` to it) including image upload to storage.
- **Replace mock data:** rewrite `Marketplace`, `PropertyDetails`, and the property pages to fetch from the live `properties` endpoint. Retire `sampleProperties.ts`.
- Admin moderation endpoint to move properties between statuses.

**Done when:** an owner creates a property, an admin activates it, and it shows up in the marketplace for investors — all real.

---

## Phase 4 — Wallet, Payments & Deposits (testable: a user deposits real (test-mode) money and balance updates)

- Integrate the payment provider (Stripe) for **deposits**: create payment intent, handle the **webhook** to credit `wallets.balance` and write a `transactions` row (`type=investment`/deposit, `status` tracked).
- Never trust client-reported payment success — balance changes happen **only** on verified provider webhooks. This is the cardinal rule of the whole system.
- All wallet mutations go through server-side transactions with the non-negative constraints already in the DB enforced.

**Done when:** a deposit via the provider's test mode reliably and atomically updates the wallet, evidenced in `transactions` and the audit log.

---

## Phase 5 — Investment Execution (testable: a verified, funded user invests in a property)

The most safety-critical operation. Must be a single atomic server-side transaction:

1. Verify user is KYC-`verified` and has sufficient `wallets.balance`.
2. Verify property is `active` and has enough `available_units`.
3. In one DB transaction: debit `wallets.balance`, create `investments` row (amount, units, status `confirmed`), decrement `properties.available_units`, increment `properties.funded_amount`, write a `transactions` row and an audit-log entry.
4. If property reaches full funding, transition status to `funded`.

- Wire the invest button on property pages to this endpoint.
- Wire `InvestorDashboard` to show real holdings, wallet, and transaction history.

**Done when:** investing moves real balance, creates a real holding, updates the property, and is fully traceable — with all the dashboards showing live numbers.

---

## Phase 6 — Returns / Payout Distribution (testable: a payout run credits investors)

- Admin-triggered (or scheduled) payout run that, for a given property/period, distributes returns proportionally to each investor's units.
- Each payout: credit `wallets.balance` + `total_returns`, write `transactions` (`type=return`) and audit entries, all atomic.
- Handle the family-group allocation logic (the `family_*` tables exist for sub-account distribution).

**Done when:** a payout run correctly and atomically credits all investors of a property, reflected in their dashboards.

---

## Phase 7 — Withdrawals (testable: a user withdraws to their payout method automatically)

- Withdrawal request endpoint with server-side checks (sufficient available balance, not pending elsewhere).
- Automated payout via the provider (Stripe payouts or equivalent) — the owner's requirement is **automatic** processing with no manual approval except in genuinely flagged cases.
- Hold/anti-fraud rules and an admin-review path **only** for flagged transactions (so "no human in the loop" is the default, not the absence of safety).

**Done when:** an approved-by-rules withdrawal executes automatically and updates wallet + transactions + audit log.

---

## Phase 8 — Secondary Market & Liquidity (testable: an investor lists units and another buys them)

- List units for sale (`secondary_listings`: units_for_sale, price_per_unit, status).
- Browse listings (wire `SecondaryMarket` / `LiquidityProviderMarket` pages).
- Purchase flow: atomic transfer of units from seller's investment to buyer's, balance settlement, platform fee, status → sold, audit entries.
- Wire the liquidity-provider and broker dashboards to real data.

**Done when:** a full secondary-market trade completes between two real users with correct fees and unit transfer.

---

## Phase 9 — Remaining Roles, Notifications & Polish (testable: every role's dashboard is real)

- Complete `OwnerDashboard`, `DeveloperDashboard`, `BrokerDashboard`, `LiquidityDashboard` against real data (the audit will list exactly what each currently fakes).
- `notifications` table wired to email/WhatsApp for key events (KYC result, investment confirmed, payout received, withdrawal processed).
- Referral commission logic (`transaction_type` includes `referral_commission`).
- Documents flow (`documents` table) for property/investment paperwork.

**Done when:** no page in the audit's inventory is still classified MOCK or FAKE-SUCCESS.

---

## Cross-Cutting Requirements (apply to every phase)

- **Atomicity:** every multi-step financial operation is one DB transaction; partial failure rolls back fully.
- **Server-authoritative money:** the client never sets a balance or confirms a payment; only verified provider webhooks and server logic do.
- **Audit trail:** every financial state change writes an immutable audit-log entry (who, what, when, before/after).
- **Idempotency:** webhook and payment handlers must be idempotent (providers retry).
- **Tests:** each financial endpoint ships with tests for the success path and the key failure paths (insufficient funds, sold-out property, duplicate webhook).
- **No feature removed:** if the audit shows a function exists in the frontend, it must end up working — not deleted to simplify.

---

## Suggested Deliverables from the Developer

1. OpenAPI/Swagger docs auto-generated by FastAPI.
2. Alembic migrations for any schema change.
3. A short README per phase: what was built, how to test it, what env vars it needs.
4. A staging environment the owner can click through at the end of each phase.
