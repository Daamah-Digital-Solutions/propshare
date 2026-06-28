# 04 — Multi-Role Flow Walkthroughs

For each role, the intended end-to-end journey is traced against the actual code, with the exact step where it stops being real. Reminder: there are **no route guards** and a **client-side role-switcher** ([AppSidebar.tsx:369](src/components/layout/AppSidebar.tsx:369)), so "role" today is a UI selection, not an enforced identity.

---

## Investor — **~15% real**. Breakpoint: the moment you try to invest.

Intended: sign up → KYC → browse marketplace → view property → invest → see it in dashboard/wallet → receive returns → exit via secondary market.

| Step | Reality | Real? |
|---|---|---|
| Sign up | `supabase.auth.signUp`; trigger creates profile + wallet(0) + kyc(pending) ([Auth.tsx:110](src/pages/Auth.tsx:110)) | ✅ REAL |
| KYC | Uploads docs, sets status `submitted` ([KYCVerification.tsx:173](src/pages/KYCVerification.tsx:173)) | 🟡 Upload real; **approval never happens** (no automation, no admin to set `verified`) |
| Browse marketplace | Hardcoded array, not the DB ([Marketplace.tsx:44](src/pages/Marketplace.tsx:44)) | ❌ MOCK |
| View property | Hardcoded objects by id ([PropertyDetails.tsx:38](src/pages/PropertyDetails.tsx:38)) | ❌ MOCK |
| **Invest** | `alert("Payment flow would proceed here")` ([InvestmentCalculator.tsx:96](src/components/property/InvestmentCalculator.tsx:96)) or fake toast ([InstallmentCalculator.tsx:181](src/components/property/InstallmentCalculator.tsx:181)) | ❌ **BREAKPOINT — nothing is created or charged** |
| See in dashboard/wallet | Dashboard numbers hardcoded; wallet row in DB is permanently $0 (no code reads/writes `wallets`/`investments`) | ❌ MOCK |
| Receive returns | Hardcoded `monthlyReturns`/`totalReturns=19000` ([ReturnsTracker.tsx:27,74](src/components/dashboard/ReturnsTracker.tsx:27)) | ❌ MOCK |
| Exit via secondary market | "List"/"Buy" are fake toasts; exit writes localStorage only ([ExitFlowDialog.tsx:91](src/components/exit/ExitFlowDialog.tsx:91)) | ❌ MOCK / local-only |

**Verdict:** Real through **account creation + KYC upload**. Everything from "browse" onward is mock; the journey dies at **Invest**, which performs no transaction.

---

## Owner / Developer — **~50% real on the create step, then disconnected**. Breakpoint: the listing never reaches the marketplace.

Intended: create a property → it appears in the live marketplace → track funding.

| Step | Reality | Real? |
|---|---|---|
| Create property (Developer dashboard) | `properties.insert({…})` + image upload ([PropertyCreationForm.tsx:167](src/components/developer/PropertyCreationForm.tsx:167)) | ✅ REAL write |
| …but status | Inserted as `status:'draft'` ([:184](src/components/developer/PropertyCreationForm.tsx:184)) | 🟡 stuck — no review/approval path or admin to promote to `active` |
| Appears in marketplace | **No** — Marketplace renders a hardcoded array and never queries `properties` ([Marketplace.tsx:44](src/pages/Marketplace.tsx:44)) | ❌ **BREAKPOINT — created listing is invisible** |
| Appears in own dashboard | **No** — Developer "Projects" tab is hardcoded mock, not the user's rows ([DeveloperDashboard.tsx:63](src/pages/DeveloperDashboard.tsx:63)) | ❌ MOCK |
| Track funding / payouts | Hardcoded $45.2M etc.; Owner withdraw is a fake toast ([OwnerDashboard.tsx:646](src/pages/OwnerDashboard.tsx:646)) | ❌ MOCK |
| Owner "List Property" form | Uncontrolled inputs, no submit handler ([OwnerDashboard.tsx:704-769](src/pages/OwnerDashboard.tsx:704)) | ❌ DEAD (only the *Developer* form works) |

**Verdict:** The **single most important finding** confirmed: property creation is genuinely wired to the database, but the marketplace and dashboards read mock data, and the record is `draft` with no promotion path. Owner creates → record exists in DB → **nothing else in the product can see it**. This is a wiring + workflow gap, not a missing-table gap.

---

## Broker — **~0% real**. Breakpoint: immediately.

Intended: refer investors → earn commission → withdraw.
- All data hardcoded ($125,000 commission, [BrokerDashboard.tsx:36](src/pages/BrokerDashboard.tsx:36)). "New Referral", "Download Commission Report", "Withdraw Funds" all **DEAD** (no handlers). There is **no referral/commission table or logic** in the schema or code (the `transaction_type` enum has `referral_commission`, but nothing writes it). **Verdict:** purely a static mockup.

---

## Liquidity Provider — **~0% real**. Breakpoint: immediately.

Intended: provide liquidity → back exits/assets → earn yield → withdraw.
- LP stats/assets hardcoded ([LiquidityDashboard.tsx:62](src/pages/LiquidityDashboard.tsx:62)). "Provide Liquidity" = fake toast ([:159](src/pages/LiquidityDashboard.tsx:159)); "Confirm Allocation" on the LP market = fake toast ([LiquidityProviderMarket.tsx:208](src/pages/LiquidityProviderMarket.tsx:208)); both Withdraw buttons **DEAD**. The exit requests the LP market claims to fund are a **separate mock set**, not linked to the (localStorage-based) exit store. There is **no liquidity-provider table** in the schema at all. **Verdict:** static mockup with no data model behind it.

---

## Admin — **does not exist**.

No `/admin` route, no admin component, no role-gated surface. Yet the platform *requires* an admin/automation actor to: approve KYC (`submitted→verified`), promote properties (`draft→active`), grant `user_roles`, confirm investments, process withdrawals, and distribute returns. **Today none of these can be done from the product — only by hand in the Supabase SQL console.** This is the core of the automation gap (see [06-automation-gaps.md](audit/06-automation-gaps.md)).

---

### Cross-role summary

| Role | % of journey real | Exact breakpoint |
|---|---|---|
| Investor | ~15% | **Invest** — no transaction created/charged ([InvestmentCalculator.tsx:96](src/components/property/InvestmentCalculator.tsx:96)) |
| Owner/Developer | ~50% (create only) | **Listing never reaches marketplace** (mock marketplace + `draft` + no promotion) |
| Broker | ~0% | Everything mock; no commission engine |
| Liquidity Provider | ~0% | Everything mock; no LP data model |
| Admin | n/a | Role/surface does not exist |
