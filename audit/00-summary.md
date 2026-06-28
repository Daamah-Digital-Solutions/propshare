# CapiMax PropShare — Reality Audit: Executive Summary

**Date:** 2026-06-02
**Scope:** Full frontend-to-backend audit of what actually works vs. what is mock/decorative.
**Method:** Direct reading of every migration, the Supabase integration, and every page/component. Claims cite `file:line`.

> ⚠️ **One-line verdict:** This is a polished, near-complete **demo front-end** with a **thin slice of real backend** (auth, profile, KYC document upload, property draft creation). The **entire financial engine — investing, wallets, payments, returns, secondary market, withdrawals — does not exist.** The platform itself says so: a banner states *"All current transactions and activities are for demonstration and testing purposes only… Official operations begin on 01/07/2026"* ([DevelopmentNoticeBanner.tsx:26](src/components/layout/DevelopmentNoticeBanner.tsx:26)).

---

## Overall completeness

| Layer | State | Est. complete |
|---|---|---|
| UI / pages / design | Essentially finished, 35 routes | ~95% |
| Auth (email + Google/Apple OAuth) | **Real & working** | ~90% |
| Profile / account settings | **Real** (reads/writes `profiles`) | ~80% |
| KYC document **upload** | **Real** (writes to `kyc_verifications` + storage) | ~60% |
| KYC **verification/approval** | Manual only — no automation, no admin UI | ~5% |
| Property **creation** (owner/developer) | **Real insert** to `properties`… | ~50% |
| Property **discovery** (marketplace) | …but Marketplace shows **hardcoded data**, never queries the table | **disconnected** |
| Investing / wallet / transactions | **0% — no code touches these tables** | ~0% |
| Secondary market (buy/sell/list) | Fake toasts only | ~0% |
| Returns / payouts / distributions | Hardcoded display numbers | ~0% |
| Payments (card/crypto/wallet) | **No integration of any kind** | 0% |
| Withdrawals / transfers | Fake toasts or dead buttons | 0% |
| Notifications / email / SMS / WhatsApp | Not wired (toggles are cosmetic) | ~0% |

**Honest overall figure for "a functioning automated investment platform": ~10–15% built.** The 85–90% that remains is precisely the hard, money-touching, regulated core.

**The reality of the buttons:** Of every interactive/financial element across the app, **exactly the following perform real backend operations**: sign in / register / OAuth ([Auth.tsx:55](src/pages/Auth.tsx:55), [110](src/pages/Auth.tsx:110), [159](src/pages/Auth.tsx:159)), KYC submit ([KYCVerification.tsx:173](src/pages/KYCVerification.tsx:173)), save profile / change password ([AccountSettings.tsx:164](src/pages/AccountSettings.tsx:164), [214](src/pages/AccountSettings.tsx:214)), create property ([PropertyCreationForm.tsx:167](src/components/developer/PropertyCreationForm.tsx:167)), sign out ([AppSidebar.tsx:475](src/components/layout/AppSidebar.tsx:475)), PWA install ([PWAInstallPrompt.tsx:97](src/components/pwa/PWAInstallPrompt.tsx:97)). **Every other financial action is a fake-success toast, a dead button, or browser-local state.**

---

## The 5 biggest risks

1. **Expectation mismatch (the #1 risk).** The owner's framing — *"just make the existing online version fully functional and automated"* — assumes the platform is mostly built. It is not. The financial/automation core **does not exist** and must be built from scratch, on top of paid third-party services that require commercial contracts, merchant accounts, and regulatory/AML clearance. This is a build-and-license programme, not a "switch it on" task. **Align on this before any timeline or budget is agreed.**

2. **The Marketplace ↔ Properties disconnect.** An owner *can* create a real property — it writes to the `properties` table ([PropertyCreationForm.tsx:167](src/components/developer/PropertyCreationForm.tsx:167)) — but it is invisible twice over: (a) the Marketplace renders a **hardcoded array** and never queries the table ([Marketplace.tsx:44-297](src/pages/Marketplace.tsx:44)), and (b) the record is created with `status: 'draft'` ([PropertyCreationForm.tsx:184](src/components/developer/PropertyCreationForm.tsx:184)) with no review/approval path to ever make it `active`. Created listings go nowhere.

3. **"Fake-success" money buttons.** Invest, Buy units, Sell units, Provide liquidity, Withdraw, Pay installment, Transfer to family, Reinvest, Schedule gift — all show success messages like *"Investment confirmed! …added to your dashboard"* ([InstallmentCalculator.tsx:181](src/components/property/InstallmentCalculator.tsx:181)) while doing nothing. Some don't even fake it: Deposit/Withdraw in the investor wallet have **no handler at all** ([InvestorWallet.tsx:190](src/components/dashboard/InvestorWallet.tsx:190), [234](src/components/dashboard/InvestorWallet.tsx:234)). In a live financial product these are dangerous — they look done but are not.

4. **No access control on the front-end.** Every route is public — there are **no route guards** in [App.tsx:72-106](src/App.tsx:72). Worse, a visible **role-switcher dropdown lets anyone become Investor/Owner/Broker/Liquidity-Provider** with no authentication ([AppSidebar.tsx:369](src/components/layout/AppSidebar.tsx:369), via `setUserRole` in [AuthContext.tsx:93](src/contexts/AuthContext.tsx:93)). (The database RLS would still block real data — but no real data is wired, so today this is a misleading-UI and future-security concern.)

5. **Fabricated trust/financial claims shown as fact.** "$50M+ AUM / 15,000+ owners / 12% returns" ([HeroSection.tsx:25-30](src/components/home/HeroSection.tsx:25)), live "$125,000 acquired in the last hour" ([HeroSection.tsx:165](src/components/home/HeroSection.tsx:165)), "Regulated by Financial Services Authority" ([Footer.tsx:150](src/components/layout/Footer.tsx:150)). These are hardcoded marketing copy. Presenting fabricated regulatory/performance claims on a live financial site is a legal/compliance exposure, mitigated today only by the dismissible demo banner.

---

## Where we are vs. where we need to be (plain language)

**Where we are:** A beautiful, complete-looking website where users can really sign up, log in, fill in their profile, upload KYC documents, and (as an owner) submit a property draft. Everything else that *looks* interactive — investing, the wallet, returns, the marketplace listings, buying and selling shares, withdrawing money — is a realistic-looking mock. Numbers are hand-typed into the code, and most buttons either pop a "success!" message or do nothing.

**Where we need to be:** A platform where money actually moves — safely, automatically, and legally. That means building the server-side engine that none of the current code has (so a user can't simply tell the browser "I now have $1M"), and connecting paid, contracted, regulated external services for KYC, payments, payouts, and notifications. Several of those services cannot be "turned on" by a developer; they require the business to open merchant accounts, sign provider contracts, and satisfy identity/AML/licensing requirements first.

**Bottom line for the owner:** The shop window is built. The shop — the tills, the vault, the bank connection, the ID checks — has not been built yet, and parts of it require licences and contracts only the business can obtain. Budget and timeline should be set against *building the financial core*, not against *finishing a nearly-done product*.

See the companion files for detail:
[01-schema.md](audit/01-schema.md) · [02-pages.md](audit/02-pages.md) · [03-buttons.md](audit/03-buttons.md) · [04-role-flows.md](audit/04-role-flows.md) · [05-backend-gaps.md](audit/05-backend-gaps.md) · [06-automation-gaps.md](audit/06-automation-gaps.md)
