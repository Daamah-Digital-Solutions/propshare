/**
 * The partners shown on the Partners page: the client's "Partner Content Register" (Capimax
 * PropShare Partners Page technical content brief, 2026), section by section and in its order,
 * each with its role, its copy, its market, the link to its own site and its logo.
 *
 * Kept as the client wrote it, except:
 *  - LexCrest's link. The brief gives lexcrestglobal.com, a name that does not exist (checked
 *    2026-10-07); the firm's site is the one the Verification Center already links.
 *  - The two newest developers (Singapore, South Africa) came as working notes ("partner entry
 *    for ..."): they are said the way the other developers are, claiming nothing more.
 *  - "Other Approved Banks" is a category that fills as banks are approved, not a company: it
 *    has no site and no role line.
 * The brief's last entry, Proof Anchor, is listed there for the ecosystem's tokenization
 * platforms (Capimax BRX, Capimax RT), not for PropShare: here it is on the Verification
 * Center only (src/lib/verificationPartners.ts).
 *
 * The logos are the brief's own images, sized for the page (src/assets/partners). The assistant
 * reads the same register from backend/app/knowledge/reference/partners_register_2026.md.
 */
import aetheraDevelopment from "@/assets/partners/aethera-development.webp";
import assuraxInsurance from "@/assets/partners/assurax-insurance.webp";
import cimGlobalFinancial from "@/assets/partners/cim-global-financial.webp";
import covertechInsurance from "@/assets/partners/covertech-insurance.webp";
import crestmarkGlobal from "@/assets/partners/crestmark-global.webp";
import crownFacilities from "@/assets/partners/crown-facilities.webp";
import elevateProperties from "@/assets/partners/elevate-properties.webp";
import eliteGateProperties from "@/assets/partners/elite-gate-properties.webp";
import lexcrestGlobalLegal from "@/assets/partners/lexcrest-global-legal.webp";
import mercury from "@/assets/partners/mercury.webp";
import novaDigitalFinance from "@/assets/partners/nova-digital-finance.webp";
import nowpayments from "@/assets/partners/nowpayments.webp";
import otherApprovedBanks from "@/assets/partners/other-approved-banks.webp";
import paypal from "@/assets/partners/paypal.webp";
import primeStoneGlobal from "@/assets/partners/prime-stone-global.webp";
import priminnHotels from "@/assets/partners/priminn-hotels.webp";
import revolutBusiness from "@/assets/partners/revolut-business.webp";
import stripe from "@/assets/partners/stripe.webp";
import sumsub from "@/assets/partners/sumsub.webp";
import valoraEstatesGlobal from "@/assets/partners/valora-estates-global.webp";
import verdeaEstates from "@/assets/partners/verdea-estates.webp";
import westoriaCapitalEstates from "@/assets/partners/westoria-capital-estates.webp";
import wiseBusiness from "@/assets/partners/wise-business.webp";

/** The register's sections: every partner belongs to exactly one. */
export type PartnerSectionKey =
  | "payments"
  | "identity"
  | "banking"
  | "advisory"
  | "insurance"
  | "developers"
  | "operations";

export interface Partner {
  key: string;
  name: string;
  /** What it is to the platform, as the register says ("Integrated payment provider"). */
  role?: string;
  description: string;
  /** Where it operates, as the register says ("Global", "United States"). */
  market: string;
  /** Its own site; none for an entry that is not one company. */
  url?: string;
  logo: string;
}

export interface PartnerSection {
  key: PartnerSectionKey;
  title: string;
  partners: Partner[];
}

export const PARTNER_SECTIONS: PartnerSection[] = [
  {
    key: "payments",
    title: "Payments and Digital Asset Payments",
    partners: [
      {
        key: "stripe",
        name: "Stripe",
        role: "Integrated payment provider",
        description:
          "Payment infrastructure for card and online payments, checkout, billing and transaction processing.",
        market: "Global",
        url: "https://stripe.com",
        logo: stripe,
      },
      {
        key: "paypal",
        name: "PayPal",
        role: "Integrated payment provider",
        description:
          "Online payment option supporting eligible customer payments and account-based checkout.",
        market: "Global",
        url: "https://www.paypal.com",
        logo: paypal,
      },
      {
        key: "nowpayments",
        name: "NOWPayments",
        role: "Crypto payment provider",
        description:
          "Cryptocurrency payment gateway supporting digital-asset payment acceptance, subject to eligibility and jurisdiction.",
        market: "Global",
        url: "https://nowpayments.io",
        logo: nowpayments,
      },
    ],
  },
  {
    key: "identity",
    title: "Identity Verification and Compliance",
    partners: [
      {
        key: "sumsub",
        name: "Sumsub",
        role: "Compliance integration",
        description:
          "KYC, KYB, identity verification, AML screening and ongoing compliance workflow provider.",
        market: "Global",
        url: "https://sumsub.com",
        logo: sumsub,
      },
    ],
  },
  {
    key: "banking",
    title: "Banking and Treasury Rails",
    partners: [
      {
        key: "mercury",
        name: "Mercury",
        role: "Business account rail",
        description:
          "US business financial-technology platform used for eligible corporate banking and payment workflows through partner banks.",
        market: "United States",
        url: "https://mercury.com",
        logo: mercury,
      },
      {
        key: "revolut-business",
        name: "Revolut Business",
        role: "Business account rail",
        description:
          "Multi-currency business account, payments and treasury-management services, subject to account eligibility.",
        market: "International",
        url: "https://www.revolut.com/business",
        logo: revolutBusiness,
      },
      {
        key: "wise-business",
        name: "Wise Business",
        role: "Business payment rail",
        description:
          "International business payments, currency conversion and multi-currency account services, subject to availability.",
        market: "International",
        url: "https://wise.com/business",
        logo: wiseBusiness,
      },
      {
        key: "other-approved-banks",
        name: "Other Approved Banks",
        description:
          "Additional banks and payment institutions may be displayed only after onboarding, approval and documentary verification.",
        market: "Multiple jurisdictions",
        logo: otherApprovedBanks,
      },
    ],
  },
  {
    key: "advisory",
    title: "Finance, Valuation, Legal and Risk",
    partners: [
      {
        key: "nova-digital-finance",
        name: "Nova Digital Finance",
        role: "Financing",
        description:
          "Capimax ecosystem financing workflow supporting eligible real-estate participation and structured payment solutions.",
        market: "Capimax ecosystem",
        url: "https://novadf.com",
        logo: novaDigitalFinance,
      },
      {
        key: "cim-global-financial",
        name: "CIM Global Financial",
        role: "Financial advisory and valuation",
        description:
          "Financial studies, asset valuation, risk assessment, due diligence support, reporting and document verification.",
        market: "United Kingdom and United States",
        url: "https://www.cimglobalfinancial.com",
        logo: cimGlobalFinancial,
      },
      {
        key: "lexcrest-global-legal",
        name: "LexCrest Global Legal",
        role: "Legal and due diligence",
        description:
          "Legal structuring, real-estate due diligence, SPV support, contracts, agreements, regulatory review and dispute support.",
        market: "Global",
        url: "https://lexcrestlegal.xyz",
        logo: lexcrestGlobalLegal,
      },
    ],
  },
  {
    key: "insurance",
    title: "Insurance and Asset Protection",
    partners: [
      {
        key: "covertech-insurance",
        name: "CoverTech Insurance",
        role: "Insurance and risk",
        description:
          "Insurance and risk solutions for real estate assets, platform exposures, digital infrastructure and eligible client-money risks, subject to policy terms.",
        market: "Global",
        url: "https://www.covertechinsurance.com",
        logo: covertechInsurance,
      },
      {
        key: "assurax-insurance",
        name: "Assurax Insurance",
        role: "Insurance and risk",
        description:
          "Insurance solutions for assets, property, investment projects and eligible client protections, subject to underwriting and policy terms.",
        market: "International",
        url: "https://assuraxinsurance.com",
        logo: assuraxInsurance,
      },
    ],
  },
  {
    key: "developers",
    title: "Real Estate Development Partners",
    partners: [
      {
        key: "westoria-capital-estates",
        name: "Westoria Capital Estates",
        role: "Developer",
        description:
          "Real-estate development and investment partner for selected residential, hospitality, commercial and mixed-use opportunities.",
        market: "United States",
        url: "https://westoriacapital.com",
        logo: westoriaCapitalEstates,
      },
      {
        key: "crestmark-global",
        name: "Crestmark Global",
        role: "Developer",
        description:
          "Real-estate development and investment partner supporting selected UK opportunities.",
        market: "United Kingdom",
        url: "https://crestmarkglobal.com",
        logo: crestmarkGlobal,
      },
      {
        key: "valora-estates-global",
        name: "Valora Estates Global",
        role: "Developer",
        description:
          "Real-estate development and investment partner supporting selected opportunities in Spain.",
        market: "Spain",
        url: "https://valoraestatesglobal.com",
        logo: valoraEstatesGlobal,
      },
      {
        key: "verdea-estates",
        name: "Verdea Estates",
        role: "Developer",
        description:
          "Real-estate development and investment partner supporting selected opportunities in Georgia.",
        market: "Georgia",
        url: "https://verdeaestates.com",
        logo: verdeaEstates,
      },
      {
        key: "aethera-development",
        name: "Aethera Development",
        role: "Developer",
        description:
          "Real-estate development and investment partner supporting selected opportunities in Greece.",
        market: "Greece",
        url: "https://aetheradevelopment.com",
        logo: aetheraDevelopment,
      },
      {
        key: "elevate-properties",
        name: "Elevate Properties Pte. Ltd",
        role: "Developer",
        description: "Real-estate development partner supporting selected opportunities in Singapore.",
        market: "Singapore",
        url: "https://elevateproperties.world",
        logo: elevateProperties,
      },
      {
        key: "prime-stone-global",
        name: "Prime Stone Global",
        role: "Developer",
        description:
          "Real-estate development partner supporting selected opportunities in South Africa.",
        market: "South Africa",
        url: "https://primestoneglobal.dev",
        logo: primeStoneGlobal,
      },
    ],
  },
  {
    key: "operations",
    title: "Hospitality, Property and Facility Management",
    partners: [
      {
        key: "priminn-hotels",
        name: "Priminn Hotels",
        role: "Hospitality operator",
        description:
          "Hospitality operating partner for hotel operations, serviced accommodation, leasing and property-level guest management.",
        market: "International",
        url: "https://priminnhotels.com",
        logo: priminnHotels,
      },
      {
        key: "elite-gate-properties",
        name: "Elite Gate Properties",
        role: "Property management",
        description:
          "Property management and leasing partner supporting tenant administration, collections and day-to-day asset operations.",
        market: "International",
        url: "https://elitegateproperties.com",
        logo: eliteGateProperties,
      },
      {
        key: "crown-facilities",
        name: "Crown Facilities",
        role: "Facility management",
        description:
          "Integrated facility and property management partner supporting maintenance, engineering, building operations and asset services.",
        market: "Global",
        url: "https://crownfm.online",
        logo: crownFacilities,
      },
    ],
  },
];

/** Every entry of the register, in its order. */
export const PARTNERS: Partner[] = PARTNER_SECTIONS.flatMap((section) => section.partners);
