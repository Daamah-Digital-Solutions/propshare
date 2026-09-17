# Public Claims Review: Website Text vs. What the Platform Actually Does

**Date:** 2026-09-17
**Prepared for:** Platform owner (Capimax PropShare)
**Scope:** Every page a visitor or investor can open without special access: home page sections, marketplace, property page, property types, the model pages under `/properties/...`, how it works, FAQ, fees, SPV model, exit and liquidity pages, about, partners, support, platform rules and terms.

## Purpose

This document lists every statement on the public website that does not match what the platform really does today, or that invents a number the platform does not have. For each one it quotes the exact text, explains in plain English how the platform really works, and offers short, truthful replacement wording that can be pasted in. Each finding was checked against the platform's own code (the part that holds the money, the units, the fees and the rules), not against earlier notes. Where something cannot be proven from the platform itself (licences, partners, company figures), it is marked "Not verifiable from the platform, confirm with the client" and repeated in the final section.

## Summary

1. **115 findings in total: 34 High, 45 Medium, 36 Low** (plus 17 items in the final "confirm with the client" list).
2. The biggest problem is **ownership models that do not exist**. Phase-Based, Future, Option and Shared Development/Partnership are described in detail (option premiums, forward contracts, preferred returns, profit splits, voting). On the platform a listing tagged with any of these is bought only through the one standard installment plan.
3. **Many headline numbers are typed into the page, not calculated from anything**: "$50M+ AUM", "15,000+ Active Owners", "$12.5M+ liquidity", "< 5 min" exits, "82% buyer demand", yields and IRR ranges, plus a whole directory of made-up SPVs.
4. **Installment terms are wrong almost everywhere.** The real plan is 6/12/18/24 months with 30/25/20/15% down, monthly payments only, a 4% fee on every payment, and no late fee. Units stay locked until the last payment, so they cannot be sold or transferred before then. There is no escrow, no independent inspector and no developer guarantee.
5. **Fees and exit mechanics are misstated**: the purchase fee is 3% on the site but 2.5% on the platform, the 10% performance fee is never charged, the "2% seller exit fee" is really 1% paid by the buyer, liquidity exits are not auto-matched or guaranteed, there is no 6-month lock-up by default, distributions are not automatically quarterly, and there is no shareholder voting.

## Severity legend

| Level | Meaning |
|---|---|
| **High** | Promises a product or mechanic investors cannot get, or shows a number that is invented. |
| **Medium** | Wrong detail or wrong number about a feature that does exist. |
| **Low** | Vague marketing that could mislead, or a small labelling problem. |

## Reference: how the platform really works (checked in code)

These facts are used throughout the tables below.

- **Two ways to buy.** (a) *Ready properties* (ready income, ready portfolio): buy whole units outright from the wallet, by card, or with the "Pronova" option (paid by card, 5% off). Crypto and bank transfer are used to top up the wallet first. (b) *Under-construction properties* (installment, construction portfolio, and any listing tagged future, option or shared development): bought only through the standard installment plan. The future, option and shared-development tags have no mechanics of their own.
- **Standard installment plan.** You choose 6, 12, 18 or 24 months. The down payment is 30%, 25%, 20% or 15% of the price and is paid on the day you sign up. The rest is split into equal monthly payments. A 4% installment fee (an admin setting) is added to the down payment and to every monthly payment. Your price is locked. Units are added to your holding with each payment. Payments are taken automatically from your wallet balance on the due date. If the wallet is short, the payment is marked overdue, you get a reminder and it is tried again: no late fee, nothing is taken away. You can only sell, transfer, gift or exit units bought this way once the whole plan is paid, and rental income also starts only then. There are no custom terms per property.
- **Units.** Whole units only. Any amount is rounded down to whole units. Each listing sets its own minimum (the database default is $500, and it must cover at least one unit).
- **Fees on the live platform.** Platform (purchase) fee 2.5%, charged once. Management fee 1% a year of your purchase value, taken out of rental distributions. Installment fee 4% per payment. Secondary market resale fee 1%, **paid by the buyer** on top (the seller gets the full price). Liquidity provider exit: price 3% below unit price, then a 2% fee taken from that price (the seller gets about 95% of unit value). Gift and family transfer fees 0%. Reinvest discount 5%. A listing may show a "performance fee" or "exit fee", but the platform never charges either.
- **Distributions.** An administrator starts each payout by hand, per property, for a period they choose, and enters the amount to share. There is no automatic monthly or quarterly schedule.
- **Secondary market.** The seller lists units at a price they set, within an optional price band set by the admin. Buyers buy directly at that price, and partial buys are allowed. The platform-wide lock-up setting defaults to **0 days**, meaning no holding period (the live value was not checked).
- **Liquidity provider (LP) exit.** The investor posts an exit request. An approved liquidity provider may choose to fund it. If none does within 24 hours (a setting), the request expires. There is no auto-matching, no guaranteed buyer, and no passive pool (switched off).
- **Not in the platform at all:** voting or governance, escrow of installment money, independent inspectors or developer draw control, developer guarantees, phase-based pricing, NAV re-pricing, option premiums or expiry, forward contracts, preferred return or profit split, blockchain records, automatic reinvestment, Pronova bonus rewards, performance fee charging, occupancy data, and any site-wide statistics (AUM, investor counts, liquidity totals).

---

## 1. Home page (`/`)

### 1a. Hero section

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 1 | High | "Platform Performance": "$50M+" "Assets Under Management", "15,000+" "Active Owners", "12%" "Avg. Annual Returns", "100+" "Properties Funded" | These four numbers are fixed text. The platform does not calculate any site-wide totals and nothing feeds this card. | Remove the card, or replace it with figures the owner confirms and updates by hand, e.g. "Properties listed: [X]". | components/home/HeroSection.tsx:25-30, 147 |
| 2 | High | "$125,000 in property ownership acquired in the last hour" (with a pulsing "live" dot) | Fixed text. It is not live and not linked to any real purchases. | Remove. | components/home/HeroSection.tsx:157-167 |
| 3 | Medium | "Regulated • Institutional-Grade • Fully Compliant" | Not verifiable from the platform, confirm with the client. The platform does enforce identity checks (KYC) before investing. | Only if a licence exists: "Licensed by [regulator], licence no. [X]". Otherwise: "KYC-verified investors • One SPV per property". | components/home/HeroSection.tsx:76 |
| 4 | Low | "Own Fractional Real Estate Shares Across More Than 15 Countries From Anywhere" | The countries shown are just whatever listings exist. The count of 15 is not verifiable from the platform. | "Own fractional real estate shares in the markets listed on the platform." | components/home/HeroSection.tsx:61 |
| 5 | Low | "exit easily through our integrated secondary market" / pillar "Exit Easily" "P2P liquidity" | You can only sell when another investor buys. Units on an unfinished installment plan cannot be sold at all. | "sell your units to other investors on our secondary market when a buyer is available." | components/home/HeroSection.tsx:36, 86-88 |
| 6 | Low | "24/7 Support" | Support is an AI chat assistant plus a contact form. Round-the-clock human support is not verifiable, confirm with the client. | "Help center and contact form" (or keep if staffed 24/7). | components/home/HeroSection.tsx:139 |
| 7 | Low | "SPV Protected" / "Fractional Title" | Units are recorded in the platform's ownership register. Whether each unit carries legal title through an SPV depends on legal set-up outside the platform. Confirm with the client. | "Held through a property SPV" (only if true for every listing). | components/home/HeroSection.tsx:131, 135 |

### 1b. "Multiple Ownership & Opportunity Models" banner

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 8 | High | "6 Different Real Estate Ownership & Opportunity Types Available on the Platform" with chips "Phase-Based", "Future", "Option" | There are two ways to buy: outright purchase of ready properties, or the standard installment plan for under-construction ones. No phase-based model exists. "Future" and "Option" listings are sold exactly like an installment purchase. | "Two ways to own: buy ready income properties outright, or buy under-construction units on a monthly installment plan." Chips: "Ready", "Ready Portfolio", "Under Construction", "Installment". | components/home/PropertyTypesBanner.tsx:12-20, 36 |

### 1c. Featured properties

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 9 | Low | "All properties are vetted by our expert team." | Listings are published by an admin. The review process is not verifiable from the platform, confirm with the client. | "Every listing is reviewed by our team before it is published." (only if true) | components/home/FeaturedProperties.tsx:151-152 |
| 10 | Low | Badge "Funding Soon" | This badge appears when a property is already 90% or more funded, so it actually means "almost full". | "Almost Funded" | components/home/FeaturedProperties.tsx:30, 137 |
| 11 | Low | "{yield}% Expected Yield" | When a listing has no yield entered (typical for under-construction), the card says "0% Expected Yield". | Hide the line when no yield is set, or show "Yield after completion". | components/home/FeaturedProperties.tsx:87, 134 |

### 1d. "What is Fractional Real Estate Ownership?" section

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 12 | Medium | "Acquire fractional ownership starting from $100." | Each listing sets its own minimum (default $500), and it must cover at least one whole unit. Amounts are rounded down to whole units. | "Start with the minimum set for each property, shown on its page." | components/home/HowItWorks.tsx:19 |
| 13 | High | "Clear ownership structure with blockchain verification" | There is no blockchain. Ownership is recorded in the platform's own ownership register, and investors can download an ownership certificate. | "Ownership recorded in the platform register, with a downloadable ownership certificate." | components/home/HowItWorks.tsx:92 |

### 1e. Benefits section

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 14 | Medium | "Start owning from as little as $100 in premium properties worldwide." | Same as #12: the minimum is per listing, default $500, and at least one unit. | "Start with the minimum set for each property." | components/home/BenefitsSection.tsx:18 |
| 15 | Medium | "Receive quarterly rental income distributions directly to your wallet." | An administrator starts each payout by hand, for a period they choose. There is no fixed quarterly schedule, and the 1% management fee is deducted first. | "Receive your share of rental income in your wallet each time a distribution is paid." | components/home/BenefitsSection.tsx:23 |
| 16 | High | "8-12% Annual Yield" and "15-25% Capital Growth" | These ranges are invented. Each listing has its own expected figures, and nothing on the platform backs these ranges. | Remove the ranges. Use "Yield shown on each property" / "Growth potential shown on each property". | components/home/BenefitsSection.tsx:157, 181 |
| 17 | Low | "Immediate Income" / "generating immediate rental returns" | Income arrives only when a distribution is paid. | "Rental income paid through distributions" | components/home/BenefitsSection.tsx:149, 154 |
| 18 | Low | "Reach thousands of qualified property owners through our platform." / "Complete property funding in weeks, not months." | Not verifiable from the platform, confirm with the client. | "Reach verified investors on our platform." | components/home/BenefitsSection.tsx:46, 51 |

### 1f. Secondary market section

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 19 | Medium | "Exit After 6 Months" / "Trade units on the secondary market after a 6-month holding period." | The holding period is one admin setting whose default is 0 days (no holding period). The value on the live site was not checked. It is not fixed at 6 months. | "Sell your units on the secondary market (a minimum holding period may apply, shown when you list)." | components/home/SecondaryMarket.tsx:87-88 |
| 20 | Medium | "Trade Your Ownership Units Anytime" | A sale completes only when another investor buys. Units on an unfinished installment plan cannot be listed until the plan is fully paid. | "Sell Your Units to Other Investors" | components/home/SecondaryMarket.tsx:74 |
| 21 | Low | "Unit prices reflect current market demand and property performance." | The seller sets the asking price (within any price band the admin sets). The property's own unit price is set by the admin and does not update automatically. | "Sellers set their asking price, within any limits the platform sets." | components/home/SecondaryMarket.tsx:92-93 |

### 1g. Liquidity provider section

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 22 | High | "Earn attractive fixed returns backed by premium real estate assets." / "Up to 12% APY" / "Premium Returns" "Earn competitive yields on your capital" | There are no fixed returns and no APY. A liquidity provider buys units from an exiting investor at a discount (currently 3%) and then earns whatever rental income and resale gain those units make. | "Buy units from investors who want to exit, at a discount, then earn rental income as the owner or resell on the secondary market." | components/home/LiquiditySection.tsx:9, 93-94, 129 |
| 23 | High | "Total Liquidity Provided" "$12.5M+" | Fixed text, not calculated. | Remove. | components/home/LiquiditySection.tsx:121-122 |
| 24 | Medium | "Choose liquidity periods that match your ownership goals." / "Choose your preferred commitment period" | There are no periods or commitments. A provider funds individual exit requests one by one. The "passive pool" product is switched off. | "Pick which exit requests you want to fund." | components/home/LiquiditySection.tsx:19, 113-114 |
| 25 | Medium | "Your capital is secured against tangible real estate assets." / "Asset-Backed" "Secured by real estate assets" | The provider simply owns the units it buys. There is no security or collateral, and the value can fall. | "You own the property units you buy. Their value can go up or down." | components/home/LiquiditySection.tsx:14, 103-104 |
| 26 | Low | "Your capital helps facilitate property funding and secondary market transactions." | Provider money only funds exit requests. It does not fund new properties. | "Your capital gives exiting investors a faster way out." | components/home/LiquiditySection.tsx:57-58 |

### 1h. Payment options section

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 27 | Medium | "Pronova Token" "5% Discount" / "Save 5% with Pronova Token" / "Pay for your property ownership using Pronova Token and receive an automatic 5% discount on all transaction fees." | "Pronova" at checkout is paid **by card**. No token is used. The 5% (an admin setting) comes off the whole total (price plus platform fee), not just the fees. It is only offered on ready properties, and installment plans show it as "Coming soon". Confirm with the client that this wording matches the Pronova arrangement. | "Choose Pronova at checkout on ready properties and get 5% off your total (paid by card). Not yet available on installment plans." | components/home/PaymentSection.tsx:8, 52-56 |
| 28 | Low | "Apple Pay / Google Pay" "One-tap checkout" | Card payments use Stripe's hosted checkout. Apple Pay and Google Pay appear only if they are switched on in the Stripe account and the device supports them. Not verified. | Keep only if confirmed switched on in Stripe. Otherwise: "Visa / Mastercard". | components/home/PaymentSection.tsx:6 |
| 29 | Low | "Cryptocurrency" "BTC, ETH, USDT" | Crypto is available only to top up the wallet (through NOWPayments), not directly at property checkout. The accepted coin list depends on the NOWPayments account and was not verified. | "Cryptocurrency (wallet top-up)" | components/home/PaymentSection.tsx:7 |
| 30 | Medium | "Nova Financing (Sukuk-Based)" / "Access Shariah-compliant financing through our Nova Sukuk program. Flexible terms with competitive profit rates." | There is no financing inside the platform. The button links to an outside website. Terms, Shariah status and profit rates are not verifiable, confirm with the client. | "Financing is offered separately by Nova Digital Finance. Terms are set by Nova." | components/home/PaymentSection.tsx:96-99 |

### 1i. "Latest Updates & Features" section

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 31 | Medium | "Automatically reinvest your returns and enjoy exclusive benefits:" | Reinvesting is a manual action the investor takes from their wallet. Nothing is reinvested automatically. The 5% reinvest discount is real (an admin setting). | "Reinvest your returns in one step and get a 5% discount on the units." | components/home/NotificationsSection.tsx:25 |
| 32 | High | "Pronova bonus rewards for reinvestment" | Not built. No bonus is ever paid. | Remove. | components/home/NotificationsSection.tsx:28 |
| 33 | Low | "Capimax BRX — Tokenization Exchange" / "our blockchain-powered real estate tokenization exchange" | This is a separate outside website. Nothing in this platform uses blockchain. Confirm with the client that BRX is live and is "ours". | "Capimax BRX, a separate Capimax platform for tokenized property (external site)." | components/home/NotificationsSection.tsx:13-14 |

### 1j. Final call-to-action section

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 34 | Medium | "Start owning from just $100" | Same as #12: the minimum is per listing (default $500). | "Low minimums, set per property" | components/home/CTASection.tsx:7 |
| 35 | Medium | "Earn quarterly rental income" | Same as #15: distributions are started by an admin, with no quarterly schedule. | "Earn rental income distributions" | components/home/CTASection.tsx:8 |
| 36 | Medium | "Exit anytime via secondary market" | Same as #20: a buyer is needed, and installment units are locked until fully paid. | "Sell to other investors on the secondary market" | components/home/CTASection.tsx:10 |
| 37 | Low | "Join thousands of owners already earning passive income" / "Regulated platform • 256-bit encryption • KYC verified owners" | Owner numbers and regulated status are not verifiable from the platform. KYC is real (it is required before investing). | "KYC-verified owners • Secure encrypted connection" (add "Regulated" only with a named licence). | components/home/CTASection.tsx:26-27, 60 |

### 1k. Site-wide footer

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 38 | Medium | "Build wealth with as little as $100." | Same as #12. | "Own real estate with low, per-property minimums." | components/layout/Footer.tsx:45 |

---

## 2. Marketplace (`/marketplace`)

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 39 | High | Quick links "Future Model" "Lock price, settle later" / "Option Model" "Premium today, decide later" / "Shared Development" "Co-invest with developer" | None of these exist as separate products. A listing tagged with any of them is bought through the standard installment plan. You cannot settle later, pay a premium and decide later, or co-invest. The owner has already decided to hide these from the admin. | Remove the three tiles. Keep "Installment-Based: Down payment, then monthly payments" and add "Construction Portfolio: Several off-plan projects, installment plan". | pages/Marketplace.tsx:271-273 |
| 40 | High | Filter chips "Future", "Option", "Partnership w/ Developer" | Same as #39. | Remove these chips. Keep "Installment" and "Construction Portfolio". | components/marketplace/PropertyFilters.tsx:219-221 |
| 41 | Low | "Income Generating" "Monthly rental yield" | Distribution frequency is not fixed (see #15). | "Rental income" | pages/Marketplace.tsx:233 |
| 42 | Low | Sort option "Ending Soon" | This option actually sorts by newest listing. There are no end dates. | "Newest" | pages/Marketplace.tsx:348, 404 |

---

## 3. Property page (`/property/:id`)

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 43 | High | "Governance Rights" "Participate in major decisions affecting the property" | There is no voting or decision feature anywhere in the platform. | Replace the card with "Income Rights: Receive your share of each rental distribution." | pages/PropertyDetails.tsx:465-467 |
| 44 | Medium | "Est. Total Return (5yr)" (ready property calculator and installment calculator) | The figure is simply your amount multiplied by the listing's "total return %" once. Nothing is calculated over 5 years. | "Est. total return (at [X]% as stated by the listing)", or confirm with the owner what the listing's total-return % means and label it that way. | components/property/InvestmentCalculator.tsx:126, 384; components/property/InstallmentCalculator.tsx:186, 520 |
| 45 | Low | "Expected Rental Yield", "Est. Capital Appreciation", "Total Expected Return", calculator header "Expected Return" | When the listing leaves these blank, the page shows "0%", which reads as a real forecast of zero. | Hide the tile when the value is blank, or show "Not provided". | pages/PropertyDetails.tsx:75-77, 354-365; components/property/InvestmentCalculator.tsx:235; components/property/InstallmentCalculator.tsx:286 |
| 46 | Low | "Maximum Investment" | When the listing sets no maximum, the page shows the full property value. The real limit is the units still available. | Hide when not set, or show "Up to the available units". | pages/PropertyDetails.tsx:74, 376 |
| 47 | Medium | "Performance Fee" "(On profits)" / "Exit Fee" "(On secondary sales)" | These appear only if the listing declares them, but the platform never charges either one. The fees that are really charged on exit are not shown: 1% resale fee paid by the buyer, and for liquidity exits a 3% discount plus a 2% fee. | Remove the two lines. Add "Secondary market: 1% paid by the buyer" and "Liquidity provider exit: 3% discount + 2% fee". | pages/PropertyDetails.tsx:402-406 |
| 48 | High | Installment schedule window: "Performance Fee" "10% on profits*" and "*Performance fee calculated annually on realized profit"; downloaded schedule: "Performance Fee: 10% of annual profit (calculated annually)" and "Note: Performance fee of 10% applies to annual realized profits and capital growth." | Fixed text. The platform charges no performance fee. | Remove all three. | components/property/InstallmentCalculator.tsx:250, 256, 629-630, 636 |
| 49 | Medium | Checkbox: "I agree that installments will be due on the dates shown above and understand that late payments may incur additional fees." | There is no late fee. A missed payment is marked overdue, the investor is reminded, and it is tried again from the wallet. Nothing is added and nothing is taken away. | "I agree that installments will be taken from my wallet on the dates shown above. If my wallet is short, the payment will be marked overdue and retried." | components/property/InstallmentCalculator.tsx:701 |
| 50 | Low | Downloaded schedule: "Fee (4%)", "Down Payment Fee: 4%", "Installment Fee: 4% per payment" | The 4% is typed into the text, while the real rate is an admin setting (4.0 today). If the admin changes it, this download will be wrong. The download is also a plain text file, not the official PDF schedule the platform can produce. | Use the live rate, or link to the platform's PDF schedule. | components/property/InstallmentCalculator.tsx:235, 247-248 |
| 51 | Medium | "Already own units in this property? Exit via the secondary market or through a liquidity provider — fully tracked in your dashboard." | Also shown on under-construction properties, but units bought on an installment plan cannot be sold or exited until the plan is fully paid. | Add: "Units on an installment plan can be sold once all payments are made." | pages/PropertyDetails.tsx:526-528 |
| 52 | Low | Payment option "Pronova Token" "5% OFF" | Paid by card with 5% off the total. No token is used (see #27). | "Pronova (card), 5% off" | components/property/InvestmentCalculator.tsx:64 |
| 53 | Low | "Asset Protection" "Your investment is legally separated from platform operations" | This is a legal claim that cannot be verified from the platform. Confirm with the client. | Keep only if the legal set-up confirms it. | pages/PropertyDetails.tsx:456-457 |

---

## 4. Property Types (`/property-types`)

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 54 | High | Hero stats "Property models" "6", "Ready-to-earn assets" "120+", "Active developments" "38", "Avg. yield" "11.2%" | Fixed text. There are two purchase models, and the other numbers are not calculated from anything. | Remove, or show "2 ways to buy" and owner-confirmed counts. | pages/PropertyTypes.tsx:329-332 |
| 55 | High | "from ready-rented income properties to phase-based, future, option and shared development models for under-construction projects." | Phase-based does not exist. Future, option and shared development behave as a plain installment purchase. | "Ready income properties you buy outright, and under-construction properties you buy on a monthly installment plan." | pages/PropertyTypes.tsx:322-324 |
| 56 | High | Ready card: "Rental yield" "8% – 11% / yr", "Occupancy" "92% avg.", "Expected income" "Monthly distributions", "Valuation" "Independent appraisal", "Exit options" "Secondary + Instant", badge "Most popular" | The platform holds no occupancy data at all. Yield is set per listing. Distributions are started by an admin with no monthly schedule. Liquidity exits are not instant (a provider must choose to fund within 24 hours). Appraisal and popularity are not verifiable. | "Rental yield: shown per property", "Income: rental distributions", "Exit options: secondary market or liquidity provider request". Remove occupancy and the badge. | pages/PropertyTypes.tsx:71-75, 80 |
| 57 | Medium | Installment card: "Down payment" "From 10%", "Installment duration" "12 – 60 months", "Payment schedule" "Monthly / Quarterly", "Ownership activation" "Per milestone", horizon "1 – 5 years" | Real plan: 6, 12, 18 or 24 months, with 30/25/20/15% down, monthly payments only. Units are added with each payment, not per milestone. | "Down payment: 15% to 30%", "Duration: 6, 12, 18 or 24 months", "Payments: monthly", "Ownership: builds with each payment", "Horizon: up to 2 years". | pages/PropertyTypes.tsx:99-102, 106 |
| 58 | Medium | Deep dive: "over predefined periods" "monthly or quarterly installments"; tiles "From 10% – 30%", "12 – 60 months", "Monthly / Quarterly", "Auto-debit supported", "Per milestone" "Progressive title rights", "Returns after activation" "Pro-rata yield"; step "Pay monthly or quarterly under your chosen plan."; step "Receive pro-rata returns and access exit options." | Same terms as #57. "Auto-debit" means each payment is taken from your **wallet balance** on the due date, not from a bank or card. Rental income and any exit (sale or liquidity provider) are available only after the final payment. A 4% fee is added to every payment and is not mentioned here. | "Pay 15% to 30% down, then equal monthly payments over 6 to 24 months, taken from your wallet on each due date. A 4% installment fee applies to each payment. Your price is locked. Units are added with every payment; rental income and selling start once the plan is fully paid." | pages/PropertyTypes.tsx:421-424, 432-437, 457, 459 |
| 59 | High | "Phase-Based Property" card ("Current phase" "Phase 2 of 4", "Share price" "$118 / unit", "Next phase pricing" "$132 / unit", "Estimated appreciation" "+22% to delivery") and section "How phase-based pricing evolves" ("$100", "$118", "$132", "$148"; "Every phase price update is supported by independent valuation reports and verified construction milestones.") | Not built. Each property has one unit price set by the admin, an installment plan locks the price at sign-up, and there is no valuation process tied to pricing. | Remove the card and the section. | pages/PropertyTypes.tsx:109-131, 922-947 |
| 60 | High | "Future-Based Property" card and deep dive: "Settlement date" "18 – 36 months", "Future pricing" "Pre-agreed", "Expected appreciation" "+22% – 35%", "Projected ROI" "12% – 18% IRR", value path "$100 / $108 / $118 / $130+", exits "Transfer of allocation", "Liquidity provider exit" "Instant exit through provider quotes", risks "Settlement obligations may apply at the future date." "Margin-related exposure may apply per opportunity structure." | Not built. A "future" listing is sold only through the standard installment plan. There is no settlement date, no transfer of an allocation, and no margin. The return figures are invented. | Remove. If the owner wants to keep the idea, describe it as "an under-construction property bought on the standard installment plan". | pages/PropertyTypes.tsx:134-155, 661-805 |
| 61 | High | "Option-Based Property" card and deep dive: "Option pricing" "From 3% of unit value", "Option price" "From 3% – 10%", "Option duration" "6 – 24 months", "The option expires automatically at the deadline.", "The investor may lose the option amount paid.", "No further obligations or remaining balance due.", exits "Sell on secondary market" "Transfer the option" "Liquidity provider exit", example "Option amount (5%)" "$5,000" to "Resale option value" "~$20,000", "Institutional-grade structure — similar to options used in structured financial products" | Not built. An "option" listing is sold through the standard installment plan: the investor commits to the full price, nothing expires, nothing caps the loss, and nothing can be sold before the plan is paid. The example gain is invented. | Remove. | pages/PropertyTypes.tsx:158-179, 494-646 |
| 62 | High | "Shared Development Property" card and deep dive: "Participation structure" "Equity partnership", "Revenue distribution" "Quarterly", "Expected ROI" "15% – 25%", "Land ownership participation", "Development profit margins", "Returns distributed pro-rata after exit or sale." | Not built. A "shared development" listing is sold through the standard installment plan. There is no partnership, no profit share and no quarterly schedule. | Remove. | pages/PropertyTypes.tsx:182-203, 820-911 |
| 63 | High | Comparison table: "Income type" "Profit share"; "Return potential" "Stable 8-11%", "10-14%", "15-22%", "12-18% IRR", "Variable", "15-25%"; risk and horizon for six models | Four of the six columns describe models that do not exist, and every return range is invented. | Replace with a two-column comparison (Ready purchase vs. Installment plan): how you pay, when income starts, when you can sell, fees. | pages/PropertyTypes.tsx:209-214 |
| 64 | Low | "Choosing the right model" ("Options and ready-rented are flexible, phase and future-based models reward patience until delivery.") and CTA "filter by ownership model, yield, location and horizon" | Refers to models that do not exist. The marketplace has no horizon filter. | "Ready properties pay rental income; installment properties let you pay over time and earn after completion." / "filter by model, yield and location". | pages/PropertyTypes.tsx:1003-1013, 1039 |

---

## 5. Model pages (`/properties/installment`, `/properties/future`, `/properties/option`, `/properties/partnership`)

Note: no menu or button on the site links to these pages except the "Explore Other Construction Models" links on the pages themselves. They still open for anyone with the address (including search engines), and they list live properties of that model.

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 65 | Medium | Installment page: "Down Payment" "10–20%", "Plan Length" "12–36 months" | Real plan: 15% to 30% down, over 6, 12, 18 or 24 months. | "Down Payment: 15% to 30%", "Plan Length: 6 to 24 months" | pages/ConstructionModelPage.tsx:58-59 |
| 66 | High | "Equal monthly payments recorded in your dashboard and held in regulated escrow." / "Capital protected by escrow + milestone gating" | There is no escrow. Each payment is taken from the investor's wallet and booked to the property straight away. Nothing is held back or released against milestones. | "Equal monthly payments are taken from your wallet on each due date and shown in your dashboard." | pages/ConstructionModelPage.tsx:65, 72 |
| 67 | High | "Milestone Audits" "Independent inspectors verify construction stages before each developer draw." / risk note "Mitigated by escrow, milestone audits, and developer guarantees." | The platform has no inspectors, no control over developer payouts and no developer guarantee. It does publish construction milestones and developer updates on the property page. | "Construction Updates: Milestones and developer updates are published on the property page." Risk note: "Construction delays can push back handover and income." | pages/ConstructionModelPage.tsx:66, 76 |
| 68 | High | "Position can be transferred at any time on the secondary market" / exit "Transfer Installment Position" "Sell your remaining position to another investor on the secondary market." "3–10 days" / "Liquidity Provider" "Instant exit at a discount; LP assumes the remaining installment schedule." "Same day" | An installment plan cannot be transferred or taken over. Units bought on a plan are locked until the last payment. After that they can be sold like any other units. | "Once all payments are made, you can sell your units on the secondary market or request a liquidity provider exit." Remove the times. | pages/ConstructionModelPage.tsx:73, 81-82 |
| 69 | High | FAQ "What if I miss an installment?" "A grace period applies. Persistent default triggers an automated re-listing of your position; recovered proceeds (less fees) are returned to you." / risk "Payment default" "Position can be re-listed; partial recovery from paid installments." | Nothing is re-listed or recovered. A missed payment is marked overdue, the investor is reminded, and it is retried from the wallet. There is no fee and nothing is taken away. | "Your payment is marked overdue and we remind you. It is retried from your wallet once you top up. No late fee is charged." | pages/ConstructionModelPage.tsx:77, 86 |
| 70 | Medium | FAQ "No rental yield until handover, but NAV-based capital appreciation is reflected at each milestone." / "Capture appreciation between subscription and delivery" | The first half is correct. There is no revaluation of any kind: your locked price never changes while the plan runs. | "No rental income until your plan is fully paid. Your price stays locked for the whole plan." | pages/ConstructionModelPage.tsx:71, 87 |
| 71 | Low | Tagline "paying in milestone-aligned installments" / "Hold to Delivery" "Complete payments and receive title + monthly rental yield." | Payments fall due every calendar month, not at milestones. Rental income is paid when an admin runs a distribution, not on a monthly schedule. | "paying in monthly installments" / "Complete payments and start receiving rental distributions." | pages/ConstructionModelPage.tsx:51, 83 |
| 72 | Medium | "Every position on the platform comes with multiple exit paths so you stay liquid throughout the lifecycle." (shown on all four pages) | Installment units cannot be sold until fully paid, and any exit needs a buyer or a provider. | "Once you fully own your units, you can sell on the secondary market or request a liquidity provider exit." | pages/ConstructionModelPage.tsx:368 |
| 73 | High | Future page (whole page): "A forward purchase agreement that locks today's price for delivery at a defined future date.", "Forward Contract • Settlement on Delivery", "Reservation" "10% of forward value", "Settlement" "T + 18–36 months", "Locked-in Price" "Today's NAV", "Projected IRR" "12–18%", "NAV is re-marked at each milestone", "Settle or Assign", "held by an independent custodian", exits "Assign Forward Contract" "5–14 days", "Discounted instant assignment to a market-making LP." "Same day" | None of this exists. A "future" listing is bought only through the standard installment plan: 15% to 30% down, monthly payments over 6 to 24 months, 4% fee per payment. There is no contract assignment, custodian, NAV or return forecast. | Remove the page, or redirect it to the installment page. | pages/ConstructionModelPage.tsx:90-133 |
| 74 | High | Option page (whole page): "Pay a small option premium today for the right — but not the obligation — to acquire the unit later.", "Option Position • Capped Downside", "Option Premium" "3–10% of strike", "Activation Window" "6–18 months", "Max Loss" "Premium paid", "Projected Upside" "20–35%", "Is the premium refundable?" "No...", "Sell Option" "1–7 days" | None of this exists. An "option" listing is bought through the standard installment plan: the buyer is committed to the full price, and nothing caps the loss or lets the buyer walk away. | Remove the page, or redirect it to the installment page. | pages/ConstructionModelPage.tsx:134-177 |
| 75 | High | Partnership page (whole page): "Co-invest with the developer in both land and construction; share profits pro-rata after a preferred return.", "Joint Venture • Profit Sharing", "Capital Stack" "60% land / 40% build", "Preferred Return" "8% pref", "Profit Split" "70 / 30 LP / GP", "Hold Period" "24–36 months", "Capital Calls", "LPs receive quarterly reporting and voting rights on major decisions", "Governance rights on major project decisions", "Refinance Distribution", "liability is limited to capital committed" | None of this exists. A "shared development" listing is bought through the standard installment plan. There is no preferred return, profit split, capital call, voting or refinance payout. | Remove the page, or redirect it to the installment page. | pages/ConstructionModelPage.tsx:178-221 |

---

## 6. Sample property page (`/property-sample/:slug`)

Note: nothing on the site links to this page. It opens only if someone types or shares the address.

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 76 | Medium | Sections "Option Terms" ("Option Premium", "Activation Deadline", "Locked-in Strike"), "Future Agreement" ("Settlement Date", "Locked Future Price"), "Installment Plan" ("Down Payment", "Term"), "Shared Development Terms" ("Land Share", "Profit Split", "Governance") | These values come from sample listing content, not from any platform mechanic. Option, future and shared terms do not exist, and the installment values shown can differ from the one standard plan. | Remove the route, or strip these sections and show only the standard plan terms. | pages/SamplePropertyDetails.tsx:151-157, 164-170, 177-183, 190-197 |
| 77 | Medium | Button "Invest in this Sample" (next to badge "Demo / Educational") | It opens the real property page for that listing, where real money can be invested, even though this page calls itself a demo. | Remove the button, or rename it to "View live listing". | pages/SamplePropertyDetails.tsx:97, 361 |

---

## 7. How It Works (`/how-it-works`)

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 78 | Medium | "Receive quarterly rental distributions directly to your wallet. Track your returns in real-time." | Distributions are started by an admin per period, with no quarterly schedule. | "Receive your share of rental income in your wallet whenever a distribution is paid, and track it in your dashboard." | pages/HowItWorks.tsx:48 |
| 79 | Medium | "Exit Anytime" "Sell your shares on our secondary market after 6 months, providing liquidity when you need it." / "Tradeable Shares" "Sell your shares on the secondary market after 6 months for liquidity." | The holding period is an admin setting that defaults to 0 days, not 6 months. A buyer is needed, and installment units are locked until fully paid. | "Sell your units to other investors on the secondary market (a minimum holding period may apply)." | pages/HowItWorks.tsx:53-54, 76-77 |
| 80 | High | "Governance Rights" "Participate in major decisions affecting the property through shareholder voting." | There is no voting feature. | Replace with "Income Rights: Receive your share of each rental distribution." | pages/HowItWorks.tsx:71-72 |
| 81 | Low | "complete the payment using credit card, bank transfer, or cryptocurrency." | Card can pay directly. Bank transfer and crypto are used to top up the wallet first (bank transfers are confirmed by an admin), and then you pay from the wallet. | "Pay by card, or top up your wallet by bank transfer or crypto and pay from your wallet." | pages/HowItWorks.tsx:36 |
| 82 | Low | "Join thousands of investors already building wealth through fractional real estate." | Not verifiable from the platform, confirm with the client. | "Start building your real estate portfolio." | pages/HowItWorks.tsx:194 |

---

## 8. SPV Model (`/spv-model` and `/spv-model/:propertyId`)

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 83 | High | "Key SPV Details" directory: "Capimax Marina SPV Ltd" "British Virgin Islands", "Capimax Downtown SPV Ltd" "Cayman Islands", "Capimax Beach SPV Ltd" "Delaware, USA", with asset values, "Investor Participation" percentages, durations, exit rules ("Secondary market trading available after 6 months", "Exit available after 12-month lock-in period") and links to three properties | Entirely made up. The code itself labels it "Mock SPV data". The linked properties do not exist. The "View Full SPV Details" button on every real property page leads here and shows none of that property's own SPV. | Remove the directory. Show each listing's real SPV name and registration on its property page only. | pages/SPVModel.tsx:45-89, 297-370; pages/PropertyDetails.tsx:485 |
| 84 | Medium | "Return Distribution Flow": "Management Fee (1%)" "-$125/month", "Platform Fee (2.5%)" "-$312/month", "Net Distributable" "$10,063/month" | The 2.5% platform fee is charged once when units are bought and is never taken from rent. The management fee is 1% a year of each investor's purchase value, deducted from their rental distributions. | Remove the platform fee line and relabel: "Management fee: 1% a year of your purchase value, deducted from your distributions". | pages/SPVModel.tsx:551-566 |
| 85 | Medium | Document cards "SPV Incorporation Documents", "Property Ownership Documents", "Financial Reports", "Valuation Reports" with "Download" buttons, and "All documents are available for download in PDF format." | The buttons do nothing. Real documents are uploaded per property and appear in the property page's Documents tab. | "Each property's documents are in the Documents tab of its property page." Remove the buttons. | pages/SPVModel.tsx:91-96, 672-675, 683 |
| 86 | Medium | "Periodic Reports" "Quarterly financial reports for all investors" | The platform produces no quarterly reports. Not verifiable whether they are sent outside the platform, confirm with the client. | "Distribution history and documents in your dashboard." | pages/SPVModel.tsx:469-470 |
| 87 | Medium | "Defined Timelines" "Exit timelines are clearly defined per SPV. Ready properties: 6 months. Under-construction: varies by project." / "Lock-in Periods" "Installment projects allow exit after the defined lock-in period based on project milestones." | There is one platform-wide holding period (default 0 days), not one per SPV. Installment units can be sold once the plan is fully paid, not at milestones. | "Ready property units can be sold on the secondary market (a platform-wide minimum holding period may apply). Installment units can be sold once all payments are made." | pages/SPVModel.tsx:620-621, 635-636 |
| 88 | Low | "Trade your shares on the secondary market after the lock-in period" / "Digital shares represent direct ownership in the property SPV, fully transparent and verifiable." | See #87 for the lock-in. Ownership is recorded in the platform register. Whether that legally equals direct SPV ownership is not verifiable from the platform. | "Trade your units on the secondary market." / "Your units are recorded in the platform ownership register." | pages/SPVModel.tsx:106, 116, 600 |

---

## 9. Fees (`/fees`)

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 89 | Medium | "Purchase Fee" "3%" "Paid once at the time of buying investment units" (card and summary table) | The live platform fee is **2.5%**, charged once at purchase. | "Purchase Fee 2.5%, paid once when you buy units" | pages/Fees.tsx:37-39, 527-532 |
| 90 | High | "Performance Fee" "10%" "Of annual profit & capital growth margin. Calculated annually based on the official annual valuation report. Applied only on realized growth and profit." (card, large panel and summary table) | The platform charges no performance fee and has no annual valuation process. | Remove, unless the owner confirms it is charged outside the platform (then state how and when). | pages/Fees.tsx:75-77, 298-318, 559-564 |
| 91 | Medium | "Secondary Market Exit Fee" "Variable" "Applied when selling units on the secondary market." / summary "Exit Fee" "Variable" "On exit transaction" / "Exit fees calculated on trade completion" | The resale fee is a fixed 1% (an admin setting), paid **by the buyer** on top of the price. The seller receives the full price and pays nothing. | "Secondary Market Fee 1%, paid by the buyer on top of the price. Sellers pay no fee." | pages/Fees.tsx:51-53, 470-471, 567-572 |
| 92 | Medium | "Total Owner Fee" "4%" "Calculated on the total project value and deducted according to platform rules." | The platform has no owner or developer fee at all. It may be charged under a separate contract, but this cannot be verified from the platform. Confirm with the client. | Keep only if charged under the listing agreement: "Owner fee 4% of project value, charged under the listing agreement." | pages/Fees.tsx:155-162, 519-524 |
| 93 | Medium | (Missing) The page says "no hidden charges" but lists no cost for a liquidity provider exit. | A liquidity exit prices units 3% below unit price, then takes a 2% fee from that price, so the seller receives about 95% of unit value. The page also omits the real discounts: 5% reinvest, 5% Pronova, and 0% gift and family transfer fees. | Add "Liquidity provider exit: 3% discount + 2% fee (you receive about 95% of unit value)", "Gifts and family transfers: no fee", "Reinvest discount: 5%". | pages/Fees.tsx:127-128, 495-576 |
| 94 | Low | "Annual Management Fee" "1%" "Calculated annually on invested amount" / summary "Management Fee" "Ready Properties" | Correct rate. It is taken out of each rental distribution (1% a year of your purchase value, pro-rated for the period), and it also applies to installment buyers once their plan is complete. The 4% down payment and installment fees are correct but can be changed by the admin. | "Management fee 1% a year of your purchase value, deducted from rental distributions (ready properties and completed installment plans)." | pages/Fees.tsx:44-46, 535-540 |
| 95 | Low | "Downloadable reports" / "Fee history visible in all financial reports" | Fees appear in the transaction history. A fee breakdown in downloadable reports was not verified. | "Fee history in your transaction records" | pages/Fees.tsx:111, 475-476 |

---

## 10. Exit Mechanisms (`/exit-mechanisms`)

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 96 | High | Stats with a "Live" badge: "Avg. secondary exit" "4.6 days", "Instant exit speed" "< 5 min", "Active marketplace demand" "$3.4M", "Available liquidity" "$1.25M" | Fixed text. None of these are measured or live. | Remove. | pages/ExitMechanisms.tsx:73-76, 83 |
| 97 | High | "Marketplace demand" "High", "Active buyer demand" "82%", "Avg. timeframe" "4 – 7 days", "Liquidity available" "$1.25M", "Liquidity availability" "94%" | Fixed text. None of these are measured. | Remove. | pages/ExitMechanisms.tsx:126-127, 133-134, 193, 199-200 |
| 98 | High | "Match required" "No — auto-matched" / "System auto-matches the request with available liquidity providers." | Nothing is auto-matched. The request is posted to the liquidity provider market and waits for an approved provider to choose to fund it. If none does within 24 hours, it expires. | "Your request is shown to approved liquidity providers. If one funds it within 24 hours, the sale completes; otherwise it expires and you can try again." | pages/ExitMechanisms.tsx:33, 47 |
| 99 | Medium | "Exit speed" "Instant / minutes", "Settlement" "Real-time settlement", "Investor receives funds in real time — settlement is immediate.", "Exit instantly through institutional liquidity providers", badge "Instant", "Immediate exit execution" | Once a provider funds the request, the money arrives in your wallet straight away. But whether and when a provider funds it is not guaranteed. | "Paid to your wallet as soon as a provider funds your request." | pages/ExitMechanisms.tsx:29, 34, 49, 179, 185-187, 210-211 |
| 100 | Medium | "Typical fees" "1.0% – 1.5%" (secondary) and "1.8% – 2.5%" (liquidity provider), "Estimated fees" "1.0% – 1.5%", "Liquidity fees" "1.8% – 2.5%" | Secondary market: 1% paid by the buyer, and the seller pays nothing. Liquidity provider: 3% below unit price, then a 2% fee, so the seller receives about 95% of unit value. | Secondary: "Seller fee 0% (buyer pays 1%)". Liquidity provider: "3% discount + 2% fee". | pages/ExitMechanisms.tsx:32, 125, 191 |
| 101 | Medium | "Qualified platform investors browse and place purchase requests." / "Funds are credited to the seller's wallet — net of platform fees." | There are no purchase requests: a buyer buys directly at the listed price (part of a listing can be bought). The seller is paid the full price, and the 1% fee is paid by the buyer. | "Verified investors buy your units at your asking price." / "The full price is credited to your wallet." | pages/ExitMechanisms.tsx:40, 42 |
| 102 | Medium | "Two transparent, asset-backed paths to exit your real estate ownership at any time" / "so you always have a path to exit" / "You're never locked in." / "Institutional providers stand ready to acquire your ownership immediately at a quoted price" | Installment units are locked until fully paid. Both exits depend on someone choosing to buy, and nobody is on standby. | "Two ways to sell units you fully own: to another investor, or to a liquidity provider at a discount. Neither is guaranteed." | pages/ExitMechanisms.tsx:65-67, 303, 318, 328 |
| 103 | Low | "Institutional liquidity provider" / "Backed by institutional providers" | Liquidity providers are platform users approved for that role. Whether they are institutions is not verifiable, confirm with the client. | "Approved liquidity providers" | pages/ExitMechanisms.tsx:31, 212 |
| 104 | Low | "Ownership units are transferred via the SPV upon payment." / "Every transfer is recorded through the property's SPV." | The transfer is recorded in the platform's ownership register when the trade settles. Any SPV-side record is outside the platform. | "Ownership moves to the buyer in the platform register as soon as the trade settles." | pages/ExitMechanisms.tsx:41, 308 |

---

## 11. Liquidity Provider Market (`/liquidity-market`)

This page is mostly accurate: it correctly describes funding exit requests at a discount and earning as the new owner.

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 105 | Low | "Institutional Marketplace" / "enabling investors to exit at any time" | See #102 and #103. | "Liquidity Provider Marketplace" / "giving investors another way to exit" | pages/LiquidityProviderMarket.tsx:117, 317 |

---

## 12. FAQ (`/faq`)

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 106 | High | "What is the Installment Model?": "pay through structured installment plans without bank interest", "Right to exit or resell the share", "Transfer of remaining obligations to a new buyer upon resale (subject to approval)" | A plan cannot be transferred to anyone, and units cannot be sold until the plan is fully paid. There is no interest, but a 4% fee is added to every payment. | "Buy under-construction units with a down payment of 15% to 30% and monthly payments over 6 to 24 months. No interest; a 4% installment fee is added to each payment. Your price is locked. Once fully paid, your units can be sold." | pages/FAQ.tsx:55-62 |
| 107 | Medium | "What is the Development Model?": "This model includes defined development phases, pre-set pricing stages, fixed timelines, and documented development and exit plans." | There are no pricing stages. Development properties are bought on the standard installment plan at one locked price. | "Under-construction properties are bought on the standard installment plan at a locked price. Rental income starts after completion." | pages/FAQ.tsx:46-52 |
| 108 | Medium | "The platform acts only as a digital and operational facilitator—not an owner or custodian of investor funds." / "Investor funds are not part of the platform's balance sheet." | The platform does hold investor cash in platform wallets: deposits (card, crypto, bank transfer to the platform's own bank accounts), rental payouts and sale proceeds stay there until withdrawn. Whether this money is legally ring-fenced is not verifiable, confirm with the client. | Confirm the legal position first. If funds sit in a segregated client account: "Wallet balances are held in a segregated client account, separate from the company's own money." | pages/FAQ.tsx:176-183 |
| 109 | Low | "Periodic returns (monthly or quarterly)" / "Distributions based on actual net rental income" | An admin runs each distribution and enters the amount to share. There is no fixed frequency. | "Returns are paid as rental distributions when they are declared, and credited to your wallet." | pages/FAQ.tsx:40-41 |
| 110 | Low | "Can I sell my ownership share?" "Yes, subject to platform rules, applicable laws, and approval procedures" | There is no approval step: any verified holder can list, and any verified investor can buy. Installment units must be fully paid first. | "Yes. Once you fully own your units you can list them on the secondary market, or request a liquidity provider exit." | pages/FAQ.tsx:194-195 |

---

## 13. Support (`/support`), Platform Rules (`/platform-rules`), Terms (`/terms`)

| # | Severity | Exact text (quoted) | What the platform actually does | Suggested wording | Source (file:line) |
|---|---|---|---|---|---|
| 111 | Medium | Support FAQ: "Minimum investments vary by property, typically starting from AED 500." | The platform works in US dollars. The default minimum is $500 and each property can set its own. | "Minimum investments vary by property (at least one unit). Check each property page." | pages/Support.tsx:312 |
| 112 | Medium | Support FAQ: "A 2% exit fee applies to all sales." | Sellers pay no fee. The buyer pays a 1% resale fee. Liquidity provider exits cost a 3% discount plus a 2% fee. | "Sellers pay no fee on the secondary market (the buyer pays 1%). A liquidity provider exit costs a 3% discount plus a 2% fee." | pages/Support.tsx:334 |
| 113 | Medium | Platform Rules: "Pay all applicable fees (2% exit fee for sellers, 3% purchase fee for buyers)" | Secondary market: 0% for sellers, 1% for buyers. The primary purchase fee is 2.5%. | "Pay all applicable fees (secondary market: 1% paid by the buyer)." | pages/PlatformRules.tsx:143 |
| 114 | Low | Platform Rules: "Honor all accepted offers within the specified timeframe" / "lock-up periods ... as specified for each investment opportunity" | There are no offers: buyers buy at the listed price immediately. The lock-up is one platform-wide setting, not per property. | "Keep enough wallet balance to complete purchases" / "the platform's minimum holding period". | pages/PlatformRules.tsx:34, 142 |
| 115 | Low | Terms: "These may include purchase fees, management fees, performance fees, and exit fees." | No performance fee is charged. The resale fee is paid by the buyer, and installment and liquidity exit fees are not named. | "These include purchase, management, installment, secondary market and liquidity exit fees." | pages/Terms.tsx:133-134 |

---

## Items to confirm with the client

None of these can be proven or disproven from the platform's code. Each depends on business, legal or partner facts. Please confirm each one, or tell us to remove or soften it.

| Claim on the site | Where | What we need from you |
|---|---|---|
| "Regulated • Institutional-Grade • Fully Compliant", "Regulated platform", "Is the platform legally regulated? Yes", "Is the SPV registered and regulated? Yes" | Home hero (HeroSection.tsx:76), CTA (CTASection.tsx:60), FAQ (FAQ.tsx:72-78, 157-162) | Name of each regulator and licence number, and in which countries. |
| "$50M+" AUM, "15,000+ Active Owners", "12%" average returns, "100+ Properties Funded", "thousands of owners/investors" | HeroSection.tsx:26-29; CTASection.tsx:26; HowItWorks.tsx:194; BenefitsSection.tsx:46 | Real, current figures and their source, or approval to remove. |
| "More Than 15 Countries" | HeroSection.tsx:61 | The list of countries with live or past listings. |
| Each property is held in its own SPV; "SPV Protected"; "Fractional Title"; the investment is "legally separated from platform operations"; what happens if the platform shuts down | HeroSection.tsx:131-135; PropertyDetails.tsx:456-457; FAQ.tsx:99-162; SPVModel.tsx:285-286 | Confirmation that every listing has its own SPV, who the SPV issues interests to, and the investor-protection documents. |
| Investor cash is "not part of the platform's balance sheet" and the platform is not a custodian | FAQ.tsx:179-183 | How wallet balances and bank-transfer deposits are held (segregated client account or not). |
| "Every property undergoes independent professional valuation, full legal due diligence, verification of ownership, permits, and contracts"; "vetted by our expert team"; "Independent appraisal" | FAQ.tsx:80-87; FeaturedProperties.tsx:151-152; PropertyTypes.tsx:74 | The actual review process and who performs valuations. |
| "Property management is handled by licensed property management companies"; "Returns are collected through dedicated asset accounts" | FAQ.tsx:90-93 | Which managers, and how rent reaches the platform. |
| Partners: Elite Gate Properties, TDH Development, Priminn Hotels, Capimax Development, CIM Financial Group, Capimax Financial Management, Assurax Insurance, HCC International Insurance, Nova Property Management, Nova Digital Finance; "Insurance providers" | Partners.tsx:11-44; AboutCapimaxPropShare.tsx:247 | Signed partnerships for each name. Note: the partner "logos" are stock photos, not the partners' real logos. |
| "Nova Financing (Sukuk-Based)", Shariah-compliant, "competitive profit rates" | PaymentSection.tsx:96-99 | Whether this product is live and who offers it. |
| "Pay ... using Pronova Token" (the platform actually takes a card payment with a 5% discount) | PaymentSection.tsx:52-56; InvestmentCalculator.tsx:64 | Whether the wording "Pronova Token" is acceptable when no token changes hands. |
| "Capimax BRX — Tokenization Exchange" | NotificationsSection.tsx:13-14 | Whether BRX is live and part of the group. |
| "Institutional" liquidity providers | ExitMechanisms.tsx:31, 185, 212; LiquidityProviderMarket.tsx:117 | Who the approved liquidity providers are. |
| "Total Owner Fee 4%" of project value | Fees.tsx:158-162, 519-524 | Whether this fee is charged under the listing contract (the platform itself never charges it). |
| "Performance Fee 10%" | Fees.tsx:75-77, 298-318, 559-564; InstallmentCalculator.tsx:250, 256, 629-636 | Whether any performance fee is charged outside the platform. If not, it should be removed everywhere. |
| "Quarterly financial reports for all investors" | SPVModel.tsx:469-470 | Whether reports are sent outside the platform, and how often. |
| "24/7 Support"; "we'll get back to you within 24 hours" | HeroSection.tsx:139; Support.tsx:225 | Actual support hours and response time. |
| "Apple Pay / Google Pay"; "BTC, ETH, USDT" | PaymentSection.tsx:6-7 | Whether Apple Pay and Google Pay are switched on in the Stripe account, and which coins the NOWPayments account accepts. |
| Secondary market holding period (the site says 6 months; the platform default is 0 days) | SecondaryMarket.tsx:87-88; HowItWorks.tsx:53-54, 76-77; SPVModel.tsx:620 | The holding period you want. We will set the admin setting to match and word the site from that value. |
