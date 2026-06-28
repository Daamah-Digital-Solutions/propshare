# 06 — Automation-Requirement Gap Analysis

The owner's requirement (translated from Arabic) is **not** a redesign — it is to make the *existing* online version **fully functional and end-to-end automated**, with **no ongoing back-office intervention** in core operations: instant automatic KYC, AI/third-party document services, ready-made payment/withdrawal/crypto/wallet integrations, automatic withdrawals/transfers, and human involvement only in genuinely exceptional cases — "like global platforms."

> ## ⚠️ The expectation mismatch (read this first)
> The owner's framing assumes the platform mostly exists and needs "switching on" and automating. **The code does not support that assumption.** As established in [00-summary.md](audit/00-summary.md)–[05](audit/05-backend-gaps.md): there are **no edge functions / no server-side logic**, **no payment, payout, KYC-provider, card, or notification integration of any kind**, the wallet/investment/transaction tables are **never read or written by any code**, and the marketplace shows hardcoded data. What exists is a **complete UI demo + auth + profile + KYC file-upload + property-draft creation**.
>
> Therefore the automation core **must be built and licensed, not configured.** And several pieces are **not things a developer can "turn on"** — they are **commercial and legal decisions only the business can make**: opening a payment **merchant account**, signing a **KYC/AML provider** contract, obtaining **money-services / securities-crowdfunding licensing** in each operating jurisdiction, and passing the providers' own business-verification/underwriting. A developer can integrate an API in days; a regulated merchant/KYC/payout account can take **weeks to months** and may be **refused** without the right licences. **This must be agreed before any timeline or cost is set.**

---

## Requirement-by-requirement

### 1. Instant, automatic KYC via a specialized provider (no manual approval)
- **Current reality:** Users upload ID/selfie/address to storage and the record is set to `status='submitted'` ([KYCVerification.tsx:173-185](src/pages/KYCVerification.tsx:173)). **There is no provider, no automated decision, and no code path that ever sets `verified`** — approval is a manual SQL edit today, and there is no admin UI to do even that. The UI literally tells users review "usually takes 1-2 business days" ([:322](src/pages/KYCVerification.tsx:322)) — i.e. manual.
- **What it actually requires:** A KYC/AML vendor account (e.g. **Sumsub**, Onfido, Persona) — a **paid subscription** and **business onboarding/contract**; an Edge Function that creates an applicant and receives the **verification webhook** to set `verified`/`rejected` automatically; sanctions/PEP screening as part of AML. Non-engineering prerequisites: vendor due-diligence on your business, and an **AML programme/policy** that regulators expect from a financial platform. The integration is moderate engineering; **the account + AML/regulatory posture is a business/legal decision.**
- **Gap size:** **BLOCKED-ON-BUSINESS-DECISION** (provider contract + AML), then MODERATE engineering.

### 2. Document upload, analysis & "smart" services via third-party AI APIs (not manual admin)
- **Current reality:** File **upload** works (KYC, property images, avatars). There is **no analysis, OCR, classification, e-sign, or AI of any kind**; investment certificates/contracts are placeholder `#` links ([InvestmentCertificates.tsx](src/components/dashboard/InvestmentCertificates.tsx)) and document downloads are dead/`console.log`.
- **What it actually requires:** Decide which "smart" services are actually needed (document OCR/validation, contract generation + **e-signature** like DocuSign, AI summarization). Each is a separate **paid API** + integration + (for e-sign) legal validity considerations per jurisdiction.
- **Gap size:** **MODERATE–LARGE** (depends how much "smart" scope is in/out; e-sign adds legal review).

### 3. Payments, withdrawals, crypto & internal wallets via ready-made professional APIs
- **Current reality:** **Nothing is integrated.** The `payment_method` enum lists visa/mastercard/apple_pay/google_pay/crypto/pronova_token/nova_sukuk, but there is **no Stripe/PSP/crypto SDK, no checkout, no webhook** anywhere ([PaymentSection.tsx](src/components/home/PaymentSection.tsx) is marketing copy). Internal wallets exist as a **table that no code touches** — every balance is permanently $0 in the DB ([01-schema.md](audit/01-schema.md)). Deposit/withdraw buttons are dead or fake ([03-buttons.md](audit/03-buttons.md) §B).
- **What it actually requires:** A **payment service provider merchant account** (e.g. **Stripe**, Checkout.com, regional acquirer) — requires **business verification/underwriting**, possibly a **registered legal entity per region**; for crypto, a regulated **on/off-ramp or custody provider** with its own KYC/Travel-Rule obligations. Then Edge Functions for charge/capture, **webhook-driven** wallet crediting, and a server-controlled ledger (the wallet UPDATE policy was deliberately removed so only trusted code can change balances).
- **Gap size:** **BLOCKED-ON-BUSINESS-DECISION** (merchant + crypto accounts, entity, underwriting), then LARGE engineering (this is the heart of the platform).

### 4. Automatic withdrawals & transfers (Stripe or similar, instant/automated)
- **Current reality:** All withdrawal buttons are **DEAD or fake-success** (investor wallet [InvestorWallet.tsx:234](src/components/dashboard/InvestorWallet.tsx:234) has no handler; owner [OwnerDashboard.tsx:646](src/pages/OwnerDashboard.tsx:646) toasts; LP/broker buttons dead). Internal transfers (family) only append to local state without moving balances ([FamilyInvestment.tsx:119](src/components/dashboard/FamilyInvestment.tsx:119)).
- **What it actually requires:** A **payout/disbursement** capability (Stripe Connect/Payouts, or a banking/payout provider) — again a **contracted, verified account**; Edge Functions enforcing balance, **idempotency**, limits, and **AML checks before release**. "Instant + automatic" payouts to arbitrary users are exactly what attracts fraud/AML controls — providers may **require holds, limits, or manual review for some cases**, which is in tension with "no human intervention" (see requirement 5).
- **Gap size:** **BLOCKED-ON-BUSINESS-DECISION** then LARGE.

### 5. No continuous human/back-office intervention (approvals, review, verification, withdrawals, processing)
- **Current reality:** Paradoxically, today **the platform is 100% manual for anything real** — because there is no automation at all, KYC approval, property activation, role grants, and any "processing" can *only* be done by a human editing the database (and there isn't even an admin UI for that). So the current state is the **opposite** of the goal.
- **What it actually requires:** Build the P2 Edge Functions ([05-backend-gaps.md](audit/05-backend-gaps.md)) so the **default path is automatic**: KYC webhook auto-decisions, payment webhook auto-credits wallet, investment executes atomically, returns distribute on a schedule (cron/scheduled function), withdrawals auto-process within risk limits. **Important honesty point:** fully removing humans is **not achievable for genuinely exceptional/regulated cases** — AML flags, sanctions hits, chargebacks/disputes, fraud holds, and large/edge withdrawals are *required* by providers and regulators to allow manual intervention. The realistic target is the owner's own caveat — *"human intervention only in genuinely necessary cases"* — i.e. **automate the happy path, with an exceptions queue**, not zero humans.
- **Gap size:** **LARGE** (and partly **BLOCKED-ON-BUSINESS-DECISION** via AML/risk policy).

### 6. End goal: works end-to-end, fully automatically, like global platforms
- **Current reality:** End-to-end, the real journey stops at "create account + upload KYC docs." No money moves; the marketplace and dashboards are mock; the create-property write is invisible to the rest of the app ([04-role-flows.md](audit/04-role-flows.md)).
- **What it actually requires:** Effectively **everything in [05-backend-gaps.md](audit/05-backend-gaps.md) P1–P4** plus all the third-party accounts above, plus the regulatory/licensing foundation a real investment platform needs in each market.
- **Gap size:** **LARGE + BLOCKED-ON-BUSINESS-DECISION.**

---

## Summary table

| # | Requirement | Current reality (file:line) | Core need | Gap |
|---|---|---|---|---|
| 1 | Instant auto KYC | upload-only, manual `submitted`, never `verified` ([KYCVerification.tsx:181](src/pages/KYCVerification.tsx:181)) | KYC/AML provider account + webhook function + AML programme | **BLOCKED-ON-BUSINESS** → MODERATE |
| 2 | AI/3rd-party doc services | upload only; no analysis/e-sign; `#` certs ([InvestmentCertificates.tsx](src/components/dashboard/InvestmentCertificates.tsx)) | scoped AI/OCR/e-sign APIs + integration | MODERATE–LARGE |
| 3 | Payments/crypto/wallets | nothing integrated; wallet table untouched ([PaymentSection.tsx:4](src/components/home/PaymentSection.tsx:4)) | merchant + crypto accounts + ledger functions | **BLOCKED-ON-BUSINESS** → LARGE |
| 4 | Auto withdrawals/transfers | dead/fake buttons ([InvestorWallet.tsx:234](src/components/dashboard/InvestorWallet.tsx:234)) | payout provider + risk-checked payout functions | **BLOCKED-ON-BUSINESS** → LARGE |
| 5 | No back-office intervention | currently 100% manual (no automation, no admin UI) | full automation + exceptions queue | LARGE (+ AML policy) |
| 6 | Fully automatic end-to-end | journey dies after KYC upload ([04-role-flows.md](audit/04-role-flows.md)) | all of P1–P4 + licensing | LARGE + **BLOCKED-ON-BUSINESS** |

**One-sentence alignment statement for the owner:** *The website is built; the automated financial platform behind it is not — and the parts that make it "instant and automatic like global platforms" depend on paid, contracted, regulated third-party services (KYC/AML, payments, payouts, crypto) that the business must procure and be licensed for before any developer can wire them in.*
