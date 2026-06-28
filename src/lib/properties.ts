// Adapters: convert backend property DTOs into the shapes the existing UI
// components were written against (the marketplace `Property` and the rich
// `SampleProperty`). This keeps the big render files almost unchanged — only
// their DATA SOURCE switches from hardcoded arrays to live `/properties` data.

import type { PropertyDetail, PropertyMilestone, PropertySummary } from "@/lib/api";
import type { Property, OwnershipModel } from "@/pages/Marketplace";
import type { SampleProperty, SampleOwnershipModel } from "@/data/sampleProperties";

const READY_MODELS = new Set(["ready-income", "ready-portfolio"]);

// Phase 15b — map the real per-property milestones back into the SampleMilestone
// shape the sample/advanced construction pages render (NAV preserved via value_index).
const fmtMilestoneDate = (iso: string | null): string => {
  if (!iso) return "TBD";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "TBD";
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
};

const milestonesToTimeline = (
  milestones: PropertyMilestone[] | undefined,
): SampleProperty["timeline"] =>
  [...(milestones ?? [])]
    .sort((a, b) => a.sort_index - b.sort_index)
    .map((m) => ({
      label: m.title,
      date: fmtMilestoneDate(m.target_date),
      progress: m.progress_pct ?? 0,
      valueIndex: m.value_index ?? 100,
      status: m.status === "completed" ? "done" : m.status === "in_progress" ? "active" : "upcoming",
    }));

export const isSampleSlug = (slug: string | null | undefined): boolean =>
  !!slug && slug.startsWith("demo-");

const coerceType = (t: string): Property["type"] => {
  const v = t.toLowerCase();
  if (v === "apartment" || v === "villa" || v === "commercial" || v === "land") return v;
  if (v === "residential") return "apartment";
  if (["office", "retail", "mixed-use", "industrial", "hotel"].includes(v)) return "commercial";
  return "apartment";
};

const coerceStatus = (status: string, fundingProgress: number): Property["status"] => {
  if (status === "funded" || fundingProgress >= 100) return "funded";
  if (fundingProgress >= 90) return "funding";
  return "open";
};

const daysUntil = (iso: string | null): number => {
  if (!iso) return 0;
  const ms = new Date(iso).getTime() - Date.now();
  return ms > 0 ? Math.ceil(ms / 86_400_000) : 0;
};

/** Backend summary → marketplace card `Property`. */
export const toMarketplaceProperty = (s: PropertySummary): Property => ({
  id: s.id,
  title: s.title,
  location: s.location,
  country: s.country ?? "",
  city: s.city ?? "",
  image: s.image ?? "",
  price: s.total_value,
  minInvestment: s.minimum_investment,
  yield: s.expected_yield ?? s.target_yield ?? 0,
  funded: Math.round(s.funding_progress),
  type: coerceType(s.property_type),
  status: coerceStatus(s.status, s.funding_progress),
  propertyStatus: READY_MODELS.has(s.model) ? "ready" : "construction",
  ownershipModel: s.model as OwnershipModel,
  investors: s.investors_count,
  daysLeft: 0,
  developer: s.developer_name ?? "—",
  propertyManagement: "Nova Property Management",
  insurance: "Assurax Insurance",
  valuation: "Capimax Financial Management",
  isSample: isSampleSlug(s.slug),
  slug: s.slug ?? undefined,
});

type Dict = Record<string, unknown>;
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const obj = (v: unknown): Dict => (v && typeof v === "object" ? (v as Dict) : {});

/** Backend detail → rich `SampleProperty` (drives the model/sample pages). */
export const toSampleProperty = (d: PropertyDetail): SampleProperty => {
  const c = obj(d.content);
  const dev = obj(c.developer);
  return {
    slug: d.slug ?? d.id,
    model: d.model as SampleOwnershipModel,
    badge: (c.badge as string) ?? "",
    badgeTone: (c.badgeTone as SampleProperty["badgeTone"]) ?? "ready",
    title: d.title,
    subtitle: d.subtitle ?? "",
    location: d.location,
    country: d.country ?? "",
    city: d.city ?? "",
    image: d.image ?? d.images[0] ?? "",
    gallery: d.images.length ? d.images : d.image ? [d.image] : [],
    description: d.description ?? "",
    propertyValue: d.total_value,
    minInvestment: d.minimum_investment,
    expectedYield: d.expected_yield ?? d.target_yield ?? undefined,
    capitalAppreciation: d.capital_appreciation ?? undefined,
    totalReturn: d.total_return ?? undefined,
    fundingProgress: Math.round(d.funding_progress),
    investorsCount: d.investors_count,
    ownershipStructure: arr(c.ownershipStructure) as SampleProperty["ownershipStructure"],
    investmentStructure: arr(c.investmentStructure) as SampleProperty["investmentStructure"],
    timeline: milestonesToTimeline(d.milestones),
    scenarios: arr(c.scenarios) as SampleProperty["scenarios"],
    exitMechanisms: arr(c.exitMechanisms) as SampleProperty["exitMechanisms"],
    risks: arr(c.risks) as SampleProperty["risks"],
    documents: arr(c.documents) as SampleProperty["documents"],
    developer: {
      name: (dev.name as string) ?? d.developer_name ?? "",
      rating: (dev.rating as number) ?? 0,
      projectsCompleted: (dev.projectsCompleted as number) ?? 0,
    },
    marketAnalysis: arr(c.marketAnalysis) as SampleProperty["marketAnalysis"],
    optionTerms: c.optionTerms as SampleProperty["optionTerms"],
    futureTerms: c.futureTerms as SampleProperty["futureTerms"],
    installmentTerms: c.installmentTerms as SampleProperty["installmentTerms"],
    sharedTerms: c.sharedTerms as SampleProperty["sharedTerms"],
    portfolioHoldings: c.portfolioHoldings as SampleProperty["portfolioHoldings"],
  };
};

export { daysUntil };
