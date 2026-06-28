# 02 — Route & Page Inventory

Parsed from [App.tsx:72-106](src/App.tsx:72). **There are no route guards** — every `<Route>` is public; `MainLayout` wraps all of them but does not gate by auth or role. Any auth enforcement lives *inside* a handful of page components (KYC, Settings redirect to `/auth`; the create-property form checks `user`). A visitor can navigate to `/dashboard`, `/owner-dashboard`, `/admin`-style pages, etc. freely.

**Data-source classification key:** REAL = reads/writes live Supabase tables or auth · MOCK = hardcoded data · STATIC = informational, no data layer · MIXED = both.

The only files in the whole app that touch Supabase tables are: [AuthContext.tsx](src/contexts/AuthContext.tsx) (`user_roles`), [PropertyCreationForm.tsx](src/components/developer/PropertyCreationForm.tsx) (`properties`), [AccountSettings.tsx](src/pages/AccountSettings.tsx) (`profiles`), [KYCVerification.tsx](src/pages/KYCVerification.tsx) (`kyc_verifications`). Plus auth/storage calls in [Auth.tsx](src/pages/Auth.tsx). Everything else is mock/static.

## Sorted by classification (REAL → MIXED → MOCK → STATIC)

| Route | Page component | Class | Auth requirement — enforced? |
|---|---|---|---|
| `/auth` | [Auth.tsx](src/pages/Auth.tsx) | **REAL** | Public by design. Real `signInWithPassword`/`signUp`/OAuth ([:55](src/pages/Auth.tsx:55),[110](src/pages/Auth.tsx:110),[159](src/pages/Auth.tsx:159)). Redirects to `/dashboard` if already authed ([:44](src/pages/Auth.tsx:44)). |
| `/kyc` | [KYCVerification.tsx](src/pages/KYCVerification.tsx) | **REAL** | Assumes logged-in. **Enforced** — redirects to `/auth` if not authed ([:86](src/pages/KYCVerification.tsx:86)). Reads/updates `kyc_verifications` ([:97](src/pages/KYCVerification.tsx:97),[173](src/pages/KYCVerification.tsx:173)). |
| `/settings` | [AccountSettings.tsx](src/pages/AccountSettings.tsx) | **REAL** | Assumes logged-in. **Enforced** — redirect to `/auth` ([:94](src/pages/AccountSettings.tsx:94)). Reads/writes `profiles` + avatar storage + auth password. (Notification toggles are fake; see [03-buttons.md](audit/03-buttons.md).) |
| `/developer-dashboard` | [DeveloperDashboard.tsx](src/pages/DeveloperDashboard.tsx) | **MIXED** | Assumes owner/developer; **NOT enforced** (open to anyone). Page body is mock; but it embeds the **real** `PropertyCreationForm` ([:167](src/pages/DeveloperDashboard.tsx:167)) which writes to `properties`. Its own "Projects" list is hardcoded, not the user's real rows. |
| `/` | [Index.tsx](src/pages/Index.tsx) | MOCK | Public. Composes home sections; all hardcoded ([HeroSection.tsx:25](src/components/home/HeroSection.tsx:25), [FeaturedProperties.tsx:20](src/components/home/FeaturedProperties.tsx:20)). |
| `/marketplace` | [Marketplace.tsx](src/pages/Marketplace.tsx) | MOCK | Public. **Hardcoded `allProperties` array** [:44-297](src/pages/Marketplace.tsx:44) + `sampleProperties`; never queries `properties`. |
| `/property/:id` | [PropertyDetails.tsx](src/pages/PropertyDetails.tsx) | MOCK | Public. Two hardcoded objects selected by id∈{4,5,6} ([:38-188](src/pages/PropertyDetails.tsx:38)); ignores the DB. |
| `/property-sample/:slug` | [SamplePropertyDetails.tsx](src/pages/SamplePropertyDetails.tsx) | MOCK | Public. Looks up `sampleProperties` by slug ([:27,45](src/pages/SamplePropertyDetails.tsx:27)). Self-labelled "Demo / Educational". |
| `/advanced-property/:model` | [AdvancedPropertyPage.tsx](src/pages/AdvancedPropertyPage.tsx) | MOCK | Public. From `sampleProperties` ([:721](src/pages/AdvancedPropertyPage.tsx:721)). |
| `/properties/:model` | [ConstructionModelPage.tsx](src/pages/ConstructionModelPage.tsx) | MOCK | Public. Hardcoded `models` + listings synthesized from `sampleProperties` ([:42,221](src/pages/ConstructionModelPage.tsx:42)). |
| `/dashboard` | [InvestorDashboard.tsx](src/pages/InvestorDashboard.tsx) | MOCK | Assumes investor; **NOT enforced**. Tab shell over mock components; greeting "Ahmed" hardcoded ([:62](src/pages/InvestorDashboard.tsx:62)). |
| `/owner-dashboard` | [OwnerDashboard.tsx](src/pages/OwnerDashboard.tsx) | MOCK | Assumes owner; **NOT enforced**. All stats/properties/payouts hardcoded ([:64-126](src/pages/OwnerDashboard.tsx:64)). |
| `/broker-dashboard` | [BrokerDashboard.tsx](src/pages/BrokerDashboard.tsx) | MOCK | Assumes broker; **NOT enforced**. Hardcoded referrals/commission ([:34-71](src/pages/BrokerDashboard.tsx:34)). |
| `/liquidity-dashboard` | [LiquidityDashboard.tsx](src/pages/LiquidityDashboard.tsx) | MOCK | Assumes LP; **NOT enforced**. Hardcoded LP stats/assets ([:62-146](src/pages/LiquidityDashboard.tsx:62)). |
| `/liquidity-market` | [LiquidityProviderMarket.tsx](src/pages/LiquidityProviderMarket.tsx) | MOCK | Assumes LP; **NOT enforced**. Hardcoded `SAMPLE_REQUESTS` ([:73](src/pages/LiquidityProviderMarket.tsx:73)); "Live" badge is decorative. |
| `/secondary-market` | [SecondaryMarket.tsx](src/pages/SecondaryMarket.tsx) | MOCK | Public. Hardcoded listings ([:40](src/pages/SecondaryMarket.tsx:40)); search/sort state never applied. |
| `/spv-model`, `/spv-model/:propertyId` | [SPVModel.tsx](src/pages/SPVModel.tsx) | MOCK | Public. Hardcoded SPV data; local detail-view state only. |
| `/how-it-works` | [HowItWorks.tsx](src/pages/HowItWorks.tsx) | STATIC | Public. |
| `/property-types` | [PropertyTypes.tsx](src/pages/PropertyTypes.tsx) | STATIC | Public. |
| `/exit-mechanisms` | [ExitMechanisms.tsx](src/pages/ExitMechanisms.tsx) | STATIC | Public. |
| `/fees` | [Fees.tsx](src/pages/Fees.tsx) | STATIC | Public. |
| `/partners` | [Partners.tsx](src/pages/Partners.tsx) | STATIC/MOCK | Public. Hardcoded partner list; buttons open external sites ([:92](src/pages/Partners.tsx:92)). |
| `/support` | [Support.tsx](src/pages/Support.tsx) | MOCK | Public. **Contact form & "live chat" are fake-success** (no API) ([:100-114](src/pages/Support.tsx:100)); WhatsApp/email/phone links are real. |
| `/install` | [InstallApp.tsx](src/pages/InstallApp.tsx) | STATIC | Public. Real PWA install prompt ([:46](src/pages/InstallApp.tsx:46)). |
| `/about-capimax-propshare` | [AboutCapimaxPropShare.tsx](src/pages/AboutCapimaxPropShare.tsx) | STATIC | Public. |
| `/faq` | [FAQ.tsx](src/pages/FAQ.tsx) | STATIC | Public. |
| `/disclaimer` | [Disclaimer.tsx](src/pages/Disclaimer.tsx) | STATIC | Public. |
| `/legal` | [Legal.tsx](src/pages/Legal.tsx) | STATIC | Public. |
| `/terms` | [Terms.tsx](src/pages/Terms.tsx) | STATIC | Public. |
| `/privacy` | [Privacy.tsx](src/pages/Privacy.tsx) | STATIC | Public. |
| `/risk-disclosure` | [RiskDisclosure.tsx](src/pages/RiskDisclosure.tsx) | STATIC | Public. |
| `/platform-rules` | [PlatformRules.tsx](src/pages/PlatformRules.tsx) | STATIC | Public. |
| `*` (404) | [NotFound.tsx](src/pages/NotFound.tsx) | STATIC | Public. |

**Totals:** 35 routes → **3 REAL** (auth/kyc/settings), **1 MIXED** (developer dashboard via embedded form), **~14 MOCK**, **~17 STATIC**.

**Notable absences:** there is **no admin route/page** anywhere (no way in the UI to approve KYC, promote a property `draft→active`, grant a role, or process a withdrawal). There is **no `/forgot-password` flow** (the link is dead — [Auth.tsx:291](src/pages/Auth.tsx:291)). The home page links "List Property" to `/developer-dashboard` and several Footer links point to routes that don't exist in the router (`/guide`, `/careers`, `/help`, `/contact`, etc. — NEEDS MANUAL VERIFICATION but they 404 against this route table).
