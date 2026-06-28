// Shared property TYPE definitions for the catalog/model pages.
//
// The demo content that used to live here as a hardcoded array has been retired:
// those rows now live in the database (seeded via backend/scripts/seed_properties.py)
// and are fetched through `propertyApi` + reconstructed into this `SampleProperty`
// shape by `toSampleProperty` in `@/lib/properties`. Only the types remain.

export type SampleOwnershipModel =
  | "ready-income"
  | "installment"
  | "future"
  | "option"
  | "shared-development"
  | "ready-portfolio"
  | "construction-portfolio";

export interface SampleMilestone {
  label: string;
  date: string;
  progress: number;
  valueIndex: number; // 100 = entry value
  status: "done" | "active" | "upcoming";
}

export interface SampleProperty {
  slug: string;
  model: SampleOwnershipModel;
  badge: string;
  badgeTone: "ready" | "construction" | "installment" | "future" | "option" | "shared" | "portfolio";
  title: string;
  subtitle: string;
  location: string;
  country: string;
  city: string;
  image: string;
  gallery: string[];
  description: string;

  // Headline metrics
  propertyValue: number;
  minInvestment: number;
  expectedYield?: number;
  capitalAppreciation?: number;
  totalReturn?: number;
  fundingProgress: number;
  investorsCount: number;

  // Ownership structure
  ownershipStructure: { label: string; value: string; note?: string }[];

  // Investment / activation / payment
  investmentStructure: { label: string; value: string }[];

  // Timeline / milestones
  timeline: SampleMilestone[];

  // ROI / scenarios
  scenarios: { label: string; outcome: string; tone: "positive" | "neutral" | "negative" }[];

  // Exit mechanisms
  exitMechanisms: { name: string; description: string; eta: string }[];

  // Risk indicators
  risks: { label: string; level: "low" | "medium" | "high"; note: string }[];

  // Documents
  documents: { name: string; type: string; size: string }[];

  // Developer / market
  developer: { name: string; rating: number; projectsCompleted: number };
  marketAnalysis: { label: string; value: string }[];

  // Optional model-specific fields
  optionTerms?: {
    optionPremium: string;
    activationDeadline: string;
    lockedPrice: string;
    futureValue: string;
  };
  futureTerms?: {
    settlementDate: string;
    futurePrice: string;
    appreciationProjection: string;
    constructionMilestoneImpact: string;
  };
  installmentTerms?: {
    downPayment: string;
    months: number;
    monthly: string;
    completionUnlock: string;
  };
  sharedTerms?: {
    landShare: string;
    constructionShare: string;
    profitSplit: string;
    governance: string;
  };
  portfolioHoldings?: { name: string; weight: string; yield?: string }[];
}
