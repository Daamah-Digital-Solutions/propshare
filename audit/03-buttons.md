# 03 — Button & Interaction Audit (core deliverable)

**Classification key:**
- **WIRED** — real operation (Supabase call, real navigation, or persisted state).
- **FAKE-SUCCESS** — shows a success `toast()`/message but performs no persistence/API call. *The most dangerous: looks done, isn't.*
- **NAVIGATION-ONLY** — only routes to another page.
- **DEAD** — no handler / disabled / stub / `console.log` / `alert()` / `// TODO`.

> **Headline:** Across the app, the only buttons that perform a **real backend operation** are the auth/profile/KYC/property-create/sign-out set listed under "WIRED (real backend)" below. **Every financial action is FAKE-SUCCESS or DEAD.** Several money buttons (investor Deposit/Withdraw, installment Pay Now, secondary-market Confirm Purchase, broker Withdraw) have *no handler at all*.

---

## A. WIRED — real backend operations (the complete list)

| Action | File:line (handler) | What it does |
|---|---|---|
| Sign in | [Auth.tsx:55](src/pages/Auth.tsx:55) `handleLogin` | `supabase.auth.signInWithPassword` |
| Register | [Auth.tsx:110](src/pages/Auth.tsx:84) `handleRegister` | `supabase.auth.signUp` (+ trigger provisions profile/wallet/kyc) |
| Google / Apple sign-in | [Auth.tsx:159](src/pages/Auth.tsx:156)/[193](src/pages/Auth.tsx:190) | OAuth via Lovable wrapper → `setSession` |
| Submit KYC docs | [KYCVerification.tsx:144](src/pages/KYCVerification.tsx:144) `handleSubmit` | uploads 3 files to `kyc-documents`, sets `kyc_verifications.status='submitted'` |
| Save profile | [AccountSettings.tsx:138](src/pages/AccountSettings.tsx:138) `handleProfileSave` | avatar upload + `profiles` update |
| Change password | [AccountSettings.tsx:193](src/pages/AccountSettings.tsx:193) `handlePasswordChange` | `supabase.auth.updateUser` |
| Create property | [PropertyCreationForm.tsx:146](src/components/developer/PropertyCreationForm.tsx:146) `handleSubmit` | image upload + `properties.insert({…status:'draft'})` |
| Sign out | [AppSidebar.tsx:475](src/components/layout/AppSidebar.tsx:475) | `supabase.auth.signOut` |
| PWA install | [PWAInstallPrompt.tsx:97](src/components/pwa/PWAInstallPrompt.tsx:97), [InstallApp.tsx:175](src/pages/InstallApp.tsx:175) | real `beforeinstallprompt` |

Partially-real / client-only-persistence (works, but no server):
- **Exit request submit** → writes to **localStorage only** ([ExitFlowDialog.tsx:91](src/components/exit/ExitFlowDialog.tsx:91) via [exitStore.ts:105](src/components/exit/exitStore.ts:105)); also `toast.success`. No backend, no wallet credit, no ownership change.
- **Exit request cancel** → flips localStorage status ([ExitRequestsPanel.tsx:166](src/components/exit/ExitRequestsPanel.tsx:166)).
- **Download installment schedule / certificate** → real client-side `.txt`/Blob download of **mock data** ([InstallmentCalculator.tsx:189](src/components/property/InstallmentCalculator.tsx:189), [InstallmentSchedule.tsx:74](src/components/dashboard/InstallmentSchedule.tsx:74)).

---

## B. FINANCIAL actions — what happens vs. what *should* (every one is fake or dead)

| Action | File:line | What happens now | What a real platform must do | Class |
|---|---|---|---|---|
| **Invest (ready property)** | [InvestmentCalculator.tsx:94](src/components/property/InvestmentCalculator.tsx:94) `handleConfirmPayment` | `alert("Payment flow would proceed here")` + closes modal | Charge payment / debit wallet; insert `investments`; decrement `properties.available_units`; bump `funded_amount`; emit `transactions` — atomically, server-side | **DEAD** |
| **Invest (installment)** | [InstallmentCalculator.tsx:181](src/components/property/InstallmentCalculator.tsx:181) `handleConfirmPayment` | `toast.success("Investment confirmed! …added to your dashboard")` — nothing persists | Create investment + installment plan + first payment + schedule | **FAKE-SUCCESS** |
| **Invest (sample page)** | [SamplePropertyDetails.tsx:343](src/pages/SamplePropertyDetails.tsx:343) | no handler | (demo) | **DEAD** |
| **Invest Now (advanced page)** | [AdvancedPropertyPage.tsx:1287](src/pages/AdvancedPropertyPage.tsx:1287) | no handler | as above | **DEAD** |
| **Deposit funds** | [InvestorWallet.tsx:190](src/components/dashboard/InvestorWallet.tsx:190) | **no handler at all** | Payment-gateway top-up → credit `wallets.balance` via webhook | **DEAD** |
| **Withdraw funds (investor)** | [InvestorWallet.tsx:234](src/components/dashboard/InvestorWallet.tsx:234) | **no handler** | Payout API → debit wallet, create withdrawal `transaction`, status tracking | **DEAD** |
| **Withdraw funds (owner)** | [OwnerDashboard.tsx:646](src/pages/OwnerDashboard.tsx:646) `handleWithdraw` | `toast.success("Withdrawal initiated")`; balance static | as above | **FAKE-SUCCESS** |
| **Withdraw (broker)** | [BrokerDashboard.tsx:278](src/pages/BrokerDashboard.tsx:278) | **no handler** | payout of commissions | **DEAD** |
| **Withdraw to bank / crypto (LP)** | [LiquidityDashboard.tsx:703](src/pages/LiquidityDashboard.tsx:703)/[707](src/pages/LiquidityDashboard.tsx:707) | **no handler** | payout API | **DEAD** |
| **Provide liquidity** | [LiquidityDashboard.tsx:404](src/pages/LiquidityDashboard.tsx:159) `handleProvideLiquidity` | `toast.success(...)`; nothing persists | debit funds, create LP position, lock period | **FAKE-SUCCESS** |
| **Confirm liquidity allocation** | [LiquidityProviderMarket.tsx:640](src/pages/LiquidityProviderMarket.tsx:208) `acceptOpportunity` | toast only | match LP capital to an exit request, move funds | **FAKE-SUCCESS** |
| **Sell / List units** | [SellUnitsForm.tsx:309](src/components/marketplace/SellUnitsForm.tsx:101) `handleCreateListing` | `toast.success("Listing created")`; no row, units never locked (mock array never mutated, so you can "sell" the same units infinitely) | insert `secondary_listings`, escrow/lock units | **FAKE-SUCCESS** |
| **Sell (dashboard tab)** | [ActiveInvestments.tsx:194](src/components/dashboard/ActiveInvestments.tsx:117) `handleSell` | toast only | as above | **FAKE-SUCCESS** |
| **Buy units (secondary, dashboard)** | [SecondaryMarketTab.tsx:194](src/components/dashboard/SecondaryMarketTab.tsx:117) `handleBuy` | `toast.success("Purchase successful!")` | match listing, debit buyer, credit seller, transfer units, take fee — atomic | **FAKE-SUCCESS** |
| **Buy units (secondary page)** | [SecondaryMarket.tsx:326](src/pages/SecondaryMarket.tsx:326) "Confirm Purchase" | **no handler** (only `disabled` gate) | as above | **DEAD** |
| **Reinvest returns** | [ReinvestReturns.tsx:310](src/components/dashboard/ReinvestReturns.tsx:50) `handleReinvest` | writes to React context (lost on refresh) + `navigate('/marketplace')` | debit returns, apply discount, create investment | **NAV + in-memory** |
| **Pay installment ("Pay Now")** | [InstallmentSchedule.tsx:134](src/components/dashboard/InstallmentSchedule.tsx:134) & [:284](src/components/dashboard/InstallmentSchedule.tsx:284) | **no handler** | charge payment, mark installment paid, update plan | **DEAD** |
| **Transfer units (family)** | [FamilyInvestment.tsx:479](src/components/dashboard/FamilyInvestment.tsx:119) `handleTransfer` | adds a history row in local state; **member balances unchanged**; toast | insert `family_transfers`, move `allocated_units` | **FAKE-SUCCESS** |
| **Allocate family returns** | [FamilyInvestment.tsx:564](src/components/dashboard/FamilyInvestment.tsx:149) | toast only, **no state change** | insert `family_return_allocations` | **FAKE-SUCCESS** |
| **Add family member** | [FamilyInvestment.tsx:348](src/components/dashboard/FamilyInvestment.tsx:89) | local append; "invitation email sent" (none sent) | insert `family_members`, send invite | **FAKE-SUCCESS** |
| **Schedule gift / add beneficiary** | [FamilyBeneficiaryGifting.tsx:712](src/components/dashboard/FamilyBeneficiaryGifting.tsx:299)/[479](src/components/dashboard/FamilyBeneficiaryGifting.tsx:251) | local append; claims "encrypted, reviewed by legal partners", "auto-executed" — none true | real scheduling + legal workflow | **FAKE-SUCCESS** |
| **Request / Issue virtual card** | [ProShareCards.tsx:437](src/components/dashboard/ProShareCards.tsx:264), [VirtualCardRequest.tsx:462](src/components/dashboard/VirtualCardRequest.tsx:309) | local-state card with fabricated PAN; toast | card-issuer API (Marqeta/Stripe Issuing/etc.) | **FAKE-SUCCESS** |

---

## C. By page/component — non-financial interactions

### Investor dashboard ([InvestorDashboard.tsx](src/pages/InvestorDashboard.tsx) + components)
- Tab nav `handleTabChange` ([:48](src/pages/InvestorDashboard.tsx:48)) — WIRED (URL/state). Bell ([:70](src/pages/InvestorDashboard.tsx:70)) & Settings ([:76](src/pages/InvestorDashboard.tsx:76)) icons — **DEAD**.
- **PortfolioOverview** — all hardcoded ($125,000 etc., [:21-87](src/components/dashboard/PortfolioOverview.tsx:21)); only ExitButton interactive.
- **ReturnsTracker** — "Export" ([:134](src/components/dashboard/ReturnsTracker.tsx:134)) & "Download Statement" ([:225](src/components/dashboard/ReturnsTracker.tsx:225)) — **DEAD**.
- **InvestmentCertificates** — "Download" / "Download All" → `console.log` stubs ([:73-81](src/components/dashboard/InvestmentCertificates.tsx:73)); "View" — **DEAD**. `documentUrl: "#"`.
- **SecondaryMarketTab** — sort Select sets state but is **never applied** to results ([:215](src/components/dashboard/SecondaryMarketTab.tsx:215)); "Edit" listing — DEAD.
- **ProShareCards / VirtualCardRequest** — reveal-number shows fabricated PAN ([ProShareCards.tsx:180](src/components/dashboard/ProShareCards.tsx:180)); freeze/limit = local state; "Manage" — DEAD.
- **ReinvestContext** — in-memory only; note sign inconsistency between `setReinvestment` (discount added, [:42](src/contexts/ReinvestContext.tsx:42)) and `applyReinvestDiscount` (discount subtracted, [:87](src/contexts/ReinvestContext.tsx:87)) — NEEDS MANUAL VERIFICATION of intended math.

### Owner / Developer dashboards
- Owner: header "List Property" ([:176](src/pages/OwnerDashboard.tsx:176)), "View Details"/"Analytics"/"Export"/"Download Statement"/in-tab "Submit for Review"/"Save as Draft" — **all DEAD**. The in-page "List Property" form has uncontrolled inputs and no submit ([:704-769](src/pages/OwnerDashboard.tsx:704)) — owners **cannot** list a property here (only the *developer* dashboard's embedded `PropertyCreationForm` works).
- Developer: "New Project" → real `PropertyCreationForm` (**WIRED**, [:167](src/pages/DeveloperDashboard.tsx:167)). All other buttons (View Details/Update Progress/Investor Report/Add Milestone/Send Update) — **DEAD**. The "Projects" list is hardcoded and does **not** show the user's real created properties.

### Broker / Liquidity
- Broker: "New Referral", "Download Commission Report", "Withdraw Funds" — **all DEAD**; figures hardcoded.
- LP market: "Deploy Liquidity"/"Open Dashboard"/"Manage" — **DEAD**; filters work.

### Property pages
- PropertyDetails: "View Profile" — DEAD; "View Full SPV Details" — NAV ([:470](src/pages/PropertyDetails.tsx:470)); tabs local. Invest delegated to calculators (see §B).
- PropertyDocuments / Sample / Advanced: all "View"/"Download"/"Download All" — **DEAD** (no handlers).
- PropertyFilters: filters WIRED (client-side), but city-by-country filter is a no-op stub ([:94-99](src/components/marketplace/PropertyFilters.tsx:94)).
- PropertyGrid: cards = NAVIGATION-ONLY (`<Button>` nested in `<Link>` — minor a11y smell).

### Auth / Settings
- [Auth.tsx]: "Forgot password?" ([:291](src/pages/Auth.tsx:291)) — **DEAD**; "Remember me" checkbox uncontrolled ([:288](src/pages/Auth.tsx:288)); Terms/Privacy/Risk-Disclosure link-buttons ([:440](src/pages/Auth.tsx:440),[444](src/pages/Auth.tsx:444),[490](src/pages/Auth.tsx:490)) — DEAD.
- [AccountSettings.tsx]: notification toggles ([:240](src/pages/AccountSettings.tsx:240)) `toast("Preferences saved")` but **nothing persists** — **FAKE-SUCCESS**; 2FA "Enable" ([:540](src/pages/AccountSettings.tsx:540)) & sessions "View" ([:551](src/pages/AccountSettings.tsx:551)) — **DEAD**. ("Current password" field is collected but unused — password change doesn't re-verify it.)

### Layout / nav / home
- **Role-switcher** `<Select onValueChange={setUserRole}>` ([AppSidebar.tsx:369](src/components/layout/AppSidebar.tsx:369)) — WIRED to client state; **lets anyone assume any role** (security note in [00-summary.md](audit/00-summary.md) & [05](audit/05-backend-gaps.md)).
- Sidebar: Logout — WIRED; dark-mode toggle — WIRED (not persisted); **language Select — DEAD** ([:504](src/components/layout/AppSidebar.tsx:504)); "Install App" → `alert()` stub ([:338](src/components/layout/AppSidebar.tsx:338)).
- MainLayout: search input, Bell "3" badge, User button — **all DEAD** ([:44-62](src/components/layout/MainLayout.tsx:44)).
- Home: BenefitsSection "Start Owning Today"/"List Your Property" look clickable but are plain `<div>`s — **DEAD** ([:98](src/components/home/BenefitsSection.tsx:98),[126](src/components/home/BenefitsSection.tsx:126)); home SecondaryMarket "View All" — DEAD ([:16](src/components/home/SecondaryMarket.tsx:16)). Most home CTAs are NAVIGATION-ONLY.
- Support: contact form + "live chat" = **FAKE-SUCCESS** (`setTimeout` + canned reply, [:74-114](src/pages/Support.tsx:74)); "Online Now" badge fake; WhatsApp/`mailto:`/`tel:` links real.

---

## D. Tally

- **Real backend buttons:** ~9 distinct actions (auth/profile/kyc/property-create/signout/pwa).
- **FAKE-SUCCESS:** the majority of dashboard/financial/family/secondary-market/support actions.
- **DEAD:** a large set — every "Download/Export", most secondary action buttons, both investor wallet money buttons, all installment "Pay Now", broker withdraw, LP withdraw, 2FA, sessions, language, "Forgot password".
- **NAVIGATION-ONLY:** nearly all home/marketing/property-grid links.

**If asked "what % of buttons actually do something real?" — for the money-touching surface it is effectively 0%.** For the app as a whole, real-backend interactions are a small minority concentrated entirely in auth, profile, KYC upload, and property-draft creation.
