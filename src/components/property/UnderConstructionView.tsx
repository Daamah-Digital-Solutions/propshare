import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Banknote,
  Briefcase,
  Building2,
  CalendarClock,
  CheckCircle,
  ChevronRight,
  Download,
  ExternalLink,
  Globe2,
  Hammer,
  Handshake,
  HardHat,
  Layers,
  LineChart,
  MapPin,
  Scale,
  ScrollText,
  Shield,
  Star,
  Target,
  TrendingUp,
  Users,
  Wallet,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiUrl, assetUrl, documentsApi, type PropertyDetail, type PropertyMilestone } from "@/lib/api";
import { INSTALLMENT_DURATIONS } from "@/lib/installments";

/**
 * Under-construction property page — the design the client knew (the model page removed on
 * 2026-09-16), restored on real data.
 *
 * The old page hard-coded most of its text (an invented SPV name, "96% on-time delivery", a
 * fake document list, ownership wording the platform must not use). Here every block reads
 * from the listing: columns, real milestones, real documents, and the sections an admin
 * fills in the Listing Editor.
 * A block with no data is not rendered — nothing is invented to fill the layout.
 */

type Dict = Record<string, unknown>;
const obj = (v: unknown): Dict => (v && typeof v === "object" && !Array.isArray(v) ? (v as Dict) : {});
const str = (v: unknown): string => (typeof v === "string" ? v.trim() : "");
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const rows = <T extends Dict>(v: unknown): T[] =>
  Array.isArray(v) ? (v.filter((r) => r && typeof r === "object") as T[]) : [];
const lines = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && x.trim() !== "") : [];

const fmt = (n: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);

const tone = (t: string | undefined) => {
  switch (t) {
    case "low":
    case "positive":
      return "bg-success/10 text-success border-success/30";
    case "high":
    case "negative":
      return "bg-destructive/10 text-destructive border-destructive/30";
    default:
      return "bg-amber-500/10 text-amber-600 border-amber-500/30";
  }
};

const MODEL_CFG: Record<string, { title: string; tagline: string; icon: typeof Hammer; accent: string }> = {
  installment: {
    title: "Installment-Based Property",
    tagline: "Pay in monthly installments while the property is built",
    icon: Hammer,
    accent: "from-amber-500/15 to-amber-500/0 border-amber-500/30",
  },
  "construction-portfolio": {
    title: "Construction Portfolio",
    tagline: "Several projects under construction, bought through installment plans",
    icon: Layers,
    accent: "from-orange-500/15 to-orange-500/0 border-orange-500/30",
  },
  future: {
    title: "Future Property",
    tagline: "Lock today's price, settle at delivery",
    icon: CalendarClock,
    accent: "from-blue-500/15 to-blue-500/0 border-blue-500/30",
  },
  option: {
    title: "Option Property",
    tagline: "Pay a premium today, decide whether to activate later",
    icon: Target,
    accent: "from-violet-500/15 to-violet-500/0 border-violet-500/30",
  },
  "shared-development": {
    title: "Shared Development Property",
    tagline: "Co-invest in land and construction alongside the developer",
    icon: Handshake,
    accent: "from-fuchsia-500/15 to-fuchsia-500/0 border-fuchsia-500/30",
  },
};
const INSTALLMENT_MODELS = new Set(["installment", "construction-portfolio"]);

const Row = ({ label, value }: { label: string; value: ReactNode }) => (
  <div className="flex items-center justify-between gap-4 border-b border-border pb-1.5 last:border-0">
    <span className="text-muted-foreground">{label}</span>
    <span className="text-right font-medium text-foreground">{value}</span>
  </div>
);

const Tile = ({ label, value, note, accent }: { label: string; value: ReactNode; note?: ReactNode; accent?: "success" | "primary" }) => (
  <div
    className={`p-3 rounded-lg border ${
      accent === "success"
        ? "bg-success/10 border-success/30"
        : accent === "primary"
          ? "bg-primary/5 border-primary/30"
          : "bg-secondary/40 border-border"
    }`}
  >
    <div className="text-xs text-muted-foreground">{label}</div>
    <div className={`font-semibold ${accent === "success" ? "text-success" : "text-foreground"}`}>{value}</div>
    {note && <div className="text-[11px] text-muted-foreground mt-1">{note}</div>}
  </div>
);

const SectionCard = ({ icon: Icon, title, children, className = "" }: { icon: typeof Hammer; title: string; children: ReactNode; className?: string }) => (
  <Card className={className}>
    <CardHeader>
      <CardTitle className="flex items-center gap-2 text-base">
        <Icon className="h-4 w-4 text-primary" /> {title}
      </CardTitle>
    </CardHeader>
    <CardContent>{children}</CardContent>
  </Card>
);

interface Props {
  detail: PropertyDetail;
  /** The real investment panel (installment calculator) — investing works exactly as before. */
  investPanel: ReactNode;
  /** The real document list with downloads. */
  documentsPanel: ReactNode;
  /** Extra sidebar content under the invest panel (e.g. the exit card). */
  sidebarExtra?: ReactNode;
  preview?: string | null;
  fees: { platformFee: number; managementFee: number; installmentFee: number; performanceFee: number | null; exitFee: number | null };
}

export default function UnderConstructionView({ detail, investPanel, documentsPanel, sidebarExtra, preview, fees }: Props) {
  const c = obj(detail.content);
  const dev = obj(c.developer);
  const spv = obj(c.spv);
  const valuation = obj(c.valuation);
  const construction = obj(c.construction);
  const cashflow = obj(c.cashflow);
  const ownership = rows<{ label?: string; value?: string }>(c.ownershipStructure).filter((r) => r.label && r.value);
  const projections = rows<{ label?: string; value?: string }>(c.investmentStructure).filter((r) => r.label && r.value);
  const market = rows<{ label?: string; value?: string }>(c.marketAnalysis).filter((r) => r.label && r.value);
  const scenarios = rows<{ label?: string; outcome?: string; tone?: string }>(c.scenarios).filter((r) => r.label && r.outcome);
  const risks = rows<{ label?: string; level?: string; note?: string }>(c.risks).filter((r) => r.label);
  const exits = rows<{ name?: string; eta?: string; description?: string }>(c.exitMechanisms).filter((r) => r.name);
  const compliance = lines(c.compliance);

  const cfg = MODEL_CFG[detail.model] ?? MODEL_CFG.installment;
  const Icon = cfg.icon;
  const images = (detail.images?.length ? detail.images : detail.image ? [detail.image] : []).map(assetUrl);
  const baseValue = detail.total_value;
  const appreciation = detail.capital_appreciation;
  const devName = str(dev.name) || detail.developer_name || "";
  const devSlug = detail.developer_slug ?? null;

  // --- milestones: progress + the optional price index (100 = launch) --------------------
  const milestones: PropertyMilestone[] = detail.milestones ?? [];
  const progress = detail.construction_progress ?? 0;
  const activeIdx = milestones.findIndex((m) => m.status === "in_progress");
  const current = activeIdx >= 0 ? milestones[activeIdx] : undefined;
  const next = milestones.slice(activeIdx >= 0 ? activeIdx + 1 : 0).find((m) => m.status !== "completed");
  const doneCount = milestones.filter((m) => m.status === "completed").length;
  const deliveryEta =
    detail.expected_completion ??
    [...milestones].reverse().find((m) => m.target_date)?.target_date ??
    null;
  const fmtDate = (d: string | null | undefined) =>
    d ? new Date(d).toLocaleDateString(undefined, { year: "numeric", month: "short" }) : "—";

  // Price progression exists only if the admin gave milestones a price index.
  const indexed = milestones.filter((m) => m.value_index != null);
  const hasPricing = indexed.length > 0 && indexed.some((m) => m.value_index !== 100);
  const idxOf = (m?: PropertyMilestone) => (m?.value_index != null ? m.value_index : null);
  const currentIndex =
    idxOf(current) ??
    [...milestones].reverse().find((m) => m.status === "completed" && m.value_index != null)?.value_index ??
    100;
  const nextIndex = milestones
    .slice(activeIdx >= 0 ? activeIdx + 1 : 0)
    .find((m) => m.status !== "completed" && m.value_index != null)?.value_index;
  const finalIndex = indexed.length ? indexed[indexed.length - 1].value_index! : 100;
  const currentValue = Math.round((baseValue * currentIndex) / 100);
  const nextValue = nextIndex != null ? Math.round((baseValue * nextIndex) / 100) : null;
  const finalValue = Math.round((baseValue * finalIndex) / 100);
  const upliftPct = Math.round(((currentValue - baseValue) / baseValue) * 1000) / 10;
  const nextPct = nextValue != null ? Math.round(((nextValue - currentValue) / currentValue) * 1000) / 10 : null;

  // --- valuation report: the uploaded document of category "valuation", if any ----------
  const { data: docs } = useQuery({
    queryKey: ["property-docs", detail.id, preview],
    queryFn: () => documentsApi.listForProperty(detail.id, preview),
  });
  const valuationDoc = (docs ?? []).find((d) => d.type === "valuation");
  const withPreview = (url: string) =>
    preview ? `${url}${url.includes("?") ? "&" : "?"}preview=${encodeURIComponent(preview)}` : url;
  const hasValuation = Boolean(str(valuation.provider) || num(valuation.value) != null);

  const spvRows = [
    { label: "SPV Name", value: detail.spv_name ?? "" },
    { label: "Jurisdiction", value: str(spv.jurisdiction) },
    { label: "Registration No.", value: detail.spv_registration ?? "" },
    { label: "Asset Holding", value: str(spv.assetHolding) },
    { label: "Investor Allocation", value: str(spv.investorAllocation) },
    { label: "Custodian / Trustee", value: str(spv.trustee) },
    { label: "Auditor", value: str(spv.auditor) },
  ].filter((r) => r.value);

  const highlights = [
    `Opportunity Model: ${cfg.title}`,
    `Property Type: ${detail.property_type.replace(/-/g, " ").replace(/^\w/, (x) => x.toUpperCase())}`,
    appreciation != null ? `Projected Appreciation: +${appreciation}%` : null,
    `Asset Value: ${fmt(baseValue)}`,
    `Minimum Ticket: ${fmt(detail.minimum_investment)}`,
    `Active Investors: ${detail.investors_count}`,
  ].filter((h): h is string => Boolean(h));

  const devTiles = [
    num(dev.projectsCompleted) != null ? { label: "Projects Completed", value: `${num(dev.projectsCompleted)}` } : null,
    num(dev.yearsExperience) != null ? { label: "Years of Experience", value: `${num(dev.yearsExperience)}` } : null,
    num(dev.onTimeDelivery) != null ? { label: "On-time Delivery", value: `${num(dev.onTimeDelivery)}%` } : null,
  ].filter((t): t is { label: string; value: string } => t !== null);

  const scrollToInvest = () =>
    document.getElementById("invest-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="min-h-screen bg-background" data-testid="under-construction-view">
      <main>
        {/* Breadcrumb */}
        <div className="bg-secondary/30 border-b border-border">
          <div className="container mx-auto px-4 py-4 flex items-center gap-2 text-sm">
            <Link to="/" className="text-muted-foreground hover:text-foreground">Home</Link>
            <ChevronRight size={14} className="text-muted-foreground" />
            <Link to="/marketplace" className="text-muted-foreground hover:text-foreground">Marketplace</Link>
            <ChevronRight size={14} className="text-muted-foreground" />
            <span className="text-foreground font-medium truncate">{detail.title}</span>
          </div>
        </div>

        {/* Hero */}
        <section className={`relative bg-gradient-to-br ${cfg.accent} border-b border-border`}>
          <div className="container mx-auto px-4 py-10">
            <Link to="/marketplace" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6">
              <ArrowLeft size={16} /> Back to Marketplace
            </Link>
            <div className="grid lg:grid-cols-2 gap-8 items-start">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  <Badge className="bg-background/70 text-foreground border-border">
                    <Icon className="h-3.5 w-3.5 mr-1" /> {cfg.title}
                  </Badge>
                  <Badge variant="outline">Under Construction</Badge>
                  {detail.status === "funded" ? (
                    <Badge variant="secondary">Fully Funded</Badge>
                  ) : (
                    <Badge className="bg-success text-success-foreground">Open for Investment</Badge>
                  )}
                </div>
                <h1 className="text-3xl md:text-4xl font-bold text-foreground mb-3">{detail.title}</h1>
                {/* The listing's own subtitle when it has one, otherwise the model tagline. */}
                <p className="text-muted-foreground mb-4">{detail.subtitle?.trim() || cfg.tagline}</p>
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-6">
                  <MapPin size={16} /> {detail.location}
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 rounded-lg bg-card border border-border">
                    <div className="text-[10px] uppercase text-muted-foreground">Asset Value</div>
                    <div className="font-bold text-foreground">{fmt(baseValue)}</div>
                  </div>
                  <div className="p-3 rounded-lg bg-card border border-border">
                    <div className="text-[10px] uppercase text-muted-foreground">Min. Ticket</div>
                    <div className="font-bold text-foreground">{fmt(detail.minimum_investment)}</div>
                  </div>
                  <div className="p-3 rounded-lg bg-card border border-border">
                    <div className="text-[10px] uppercase text-muted-foreground">Appreciation</div>
                    <div className="font-bold text-success">{appreciation != null ? `+${appreciation}%` : "—"}</div>
                  </div>
                  <div className="p-3 rounded-lg bg-card border border-border">
                    <div className="text-[10px] uppercase text-muted-foreground">Investors</div>
                    <div className="font-bold text-foreground">{detail.investors_count}</div>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl overflow-hidden border border-border bg-card">
                {images.length ? (
                  <>
                    <img src={images[0]} alt={detail.title} className="w-full h-72 object-cover" />
                    {images.length > 1 && (
                      <div className="grid grid-cols-3 gap-1 p-1">
                        {images.slice(1, 4).map((g, i) => (
                          <img key={i} src={g} alt="" className="h-20 w-full object-cover rounded" />
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="flex h-72 items-center justify-center text-sm text-muted-foreground">
                    Photos will be added soon
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>

        <div className="container mx-auto px-4 py-10 grid lg:grid-cols-3 gap-8">
          {/* Main content */}
          <div className="lg:col-span-2 min-w-0 space-y-6">
            <Tabs defaultValue="overview" className="w-full">
              <TabsList className="w-full flex flex-wrap justify-start bg-secondary/50 p-1 rounded-xl h-auto gap-1">
                <TabsTrigger value="overview" className="rounded-lg">Overview</TabsTrigger>
                <TabsTrigger value="financials" className="rounded-lg">Financials</TabsTrigger>
                <TabsTrigger value="structure" className="rounded-lg">SPV Structure</TabsTrigger>
                <TabsTrigger value="documents" className="rounded-lg">Documents</TabsTrigger>
                <TabsTrigger value="timeline" className="rounded-lg">Timeline</TabsTrigger>
                <TabsTrigger value="developer" className="rounded-lg">Developer</TabsTrigger>
              </TabsList>

              {/* OVERVIEW */}
              <TabsContent value="overview" className="mt-6 space-y-6">
                <SectionCard icon={Building2} title="Property Overview">
                  <div className="text-sm text-muted-foreground space-y-4">
                    {detail.description && <p className="whitespace-pre-line">{detail.description}</p>}
                    <div>
                      <div className="text-xs uppercase text-muted-foreground mb-2">Investment Highlights</div>
                      <div className="grid sm:grid-cols-2 gap-2">
                        {highlights.map((h) => (
                          <div key={h} className="flex items-start gap-2 text-sm p-2.5 rounded-lg bg-secondary/40 border border-border">
                            <CheckCircle className="h-4 w-4 text-success mt-0.5 shrink-0" />
                            <span className="text-foreground">{h}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    {ownership.length > 0 && (
                      <div data-testid="ownership-structure">
                        <div className="text-xs uppercase text-muted-foreground mb-2">Ownership Structure Summary</div>
                        <div className="grid sm:grid-cols-2 gap-3">
                          {ownership.map((o) => (
                            <div key={o.label} className="p-3 bg-secondary/40 rounded-lg border border-border">
                              <div className="text-xs text-muted-foreground">{o.label}</div>
                              <div className="font-semibold text-foreground">{o.value}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </SectionCard>

                {INSTALLMENT_MODELS.has(detail.model) && (
                  <Card className="border-amber-500/30" data-testid="installment-structure">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <Hammer className="h-4 w-4 text-amber-500" /> Installment Plan Structure
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        {INSTALLMENT_DURATIONS.map((d) => (
                          <Tile key={d.value} label={d.label} value={`${d.downPaymentPercent}% down`} note={`then ${d.months - 1} monthly payments`} />
                        ))}
                      </div>
                      <div className="p-3 rounded-lg bg-amber-500/5 border border-amber-500/30 text-xs text-muted-foreground">
                        Your units vest progressively with every installment you pay. An installment
                        fee of {fees.installmentFee}% applies to the down payment and to each installment.
                        Use the calculator to see your exact schedule.
                      </div>
                    </CardContent>
                  </Card>
                )}

                {milestones.length > 0 && (
                  <Card className="border-primary/30 bg-gradient-to-br from-primary/5 to-transparent" data-testid="construction-progress">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <HardHat className="h-4 w-4 text-primary" /> Construction Progress Indicator
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-5">
                      <div className="grid sm:grid-cols-[auto,1fr] gap-5 items-center">
                        <div className="relative h-28 w-28 mx-auto">
                          <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
                            <circle cx="50" cy="50" r="42" className="fill-none stroke-secondary" strokeWidth="10" />
                            <circle
                              cx="50"
                              cy="50"
                              r="42"
                              className="fill-none stroke-primary transition-all"
                              strokeWidth="10"
                              strokeLinecap="round"
                              strokeDasharray={`${(progress / 100) * 264} 264`}
                            />
                          </svg>
                          <div className="absolute inset-0 flex flex-col items-center justify-center">
                            <span className="text-2xl font-bold text-foreground">{progress}%</span>
                            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Complete</span>
                          </div>
                        </div>
                        <div className="space-y-3">
                          <div>
                            <div className="text-xs uppercase text-muted-foreground">Current Construction Phase</div>
                            <div className="text-lg font-semibold text-foreground">{current?.title ?? (doneCount === milestones.length ? "Completed" : "Not started")}</div>
                            <div className="text-xs text-muted-foreground mt-0.5">
                              Stage {Math.min(milestones.length, doneCount + 1)} of {milestones.length}
                              {next ? ` · Next: ${next.title}` : " · Final stage"}
                            </div>
                          </div>
                          <Progress value={progress} className="h-2" />
                          <div className="grid grid-cols-3 gap-2 text-xs">
                            {str(construction.engineeringStatus) && (
                              <div className="p-2 rounded-md bg-secondary/50 border border-border">
                                <div className="text-muted-foreground">Engineering</div>
                                <div className="font-semibold text-success">{str(construction.engineeringStatus)}</div>
                              </div>
                            )}
                            {str(construction.auditStatus) && (
                              <div className="p-2 rounded-md bg-secondary/50 border border-border">
                                <div className="text-muted-foreground">Milestone Audit</div>
                                <div className="font-semibold text-foreground">{str(construction.auditStatus)}</div>
                              </div>
                            )}
                            <div className="p-2 rounded-md bg-secondary/50 border border-border">
                              <div className="text-muted-foreground">Delivery ETA</div>
                              <div className="font-semibold text-foreground">{fmtDate(deliveryEta)}</div>
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                        {milestones.map((m) => {
                          const done = m.status === "completed";
                          const active = m.status === "in_progress";
                          const pct = done ? 100 : active ? m.progress_pct ?? 0 : 0;
                          return (
                            <div
                              key={m.id}
                              className={`p-2.5 rounded-lg border ${
                                done ? "border-success/40 bg-success/5" : active ? "border-primary/50 bg-primary/10" : "border-border bg-secondary/30"
                              }`}
                            >
                              <div className="flex items-center gap-1.5">
                                <div className={`h-2 w-2 rounded-full ${done ? "bg-success" : active ? "bg-primary animate-pulse" : "bg-muted-foreground/40"}`} />
                                <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                                  {done ? "Done" : active ? "Active" : "Upcoming"}
                                </span>
                              </div>
                              <div className="text-xs font-semibold text-foreground mt-1 leading-tight">{m.title}</div>
                              <Progress value={pct} className="h-1 mt-1.5" />
                              <div className="text-[10px] text-muted-foreground mt-1">{pct}%</div>
                            </div>
                          );
                        })}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {hasPricing && (
                  <Card className="border-success/30 bg-gradient-to-br from-success/5 to-transparent" data-testid="price-appreciation">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <TrendingUp className="h-4 w-4 text-success" /> Price &amp; Appreciation Indicator
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
                        <Tile label="Launch Price" value={fmt(baseValue)} note="Initial offering reference" />
                        <Tile label="Current Property Price" value={fmt(currentValue)} note={`Price index ${currentIndex}`} accent="primary" />
                        {nextValue != null && (
                          <Tile
                            label="Expected Next Phase Price"
                            value={fmt(nextValue)}
                            note={`${next ? `At ${next.title}` : "Next phase"}${nextPct && nextPct > 0 ? ` · +${nextPct}%` : ""}`}
                            accent="success"
                          />
                        )}
                        <Tile label="Estimated Delivery Value" value={fmt(finalValue)} note="Projected at handover" accent="success" />
                      </div>
                      <div className="relative pt-2">
                        <div className="h-2 rounded-full bg-secondary overflow-hidden">
                          <div className="h-full bg-gradient-to-r from-primary via-primary to-success" style={{ width: `${Math.min(100, Math.max(5, progress))}%` }} />
                        </div>
                        <div className="flex justify-between text-[10px] uppercase text-muted-foreground mt-1.5">
                          <span>Launch</span>
                          <span>Construction</span>
                          <span>Delivery</span>
                        </div>
                      </div>
                      <div className="text-xs text-muted-foreground p-3 rounded-lg bg-primary/5 border border-primary/20">
                        These prices are estimates set per construction stage, not guarantees. Current
                        uplift from launch: <strong className="text-success">{upliftPct >= 0 ? "+" : ""}{upliftPct}%</strong>.
                      </div>
                    </CardContent>
                  </Card>
                )}

                {hasValuation && (
                  <Card className="bg-gradient-to-br from-secondary/40 to-transparent" data-testid="valuation-report">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <Scale className="h-4 w-4 text-primary" /> Independent Valuation Report
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4 text-sm">
                      <div className="grid sm:grid-cols-2 gap-3">
                        {str(valuation.provider) && <Tile label="Valuation Provider" value={str(valuation.provider)} />}
                        {str(valuation.reportDate) && <Tile label="Report Issue Date" value={str(valuation.reportDate)} />}
                        {num(valuation.value) != null && <Tile label="Latest Valuation" value={fmt(num(valuation.value)!)} />}
                        {str(valuation.impactNote) && <Tile label="Development Impact on Valuation" value={str(valuation.impactNote)} accent="success" />}
                      </div>
                      {str(valuation.summary) && (
                        <div className="p-3 rounded-lg bg-secondary/40 border border-border">
                          <div className="text-xs uppercase text-muted-foreground mb-1">Market Analysis</div>
                          <div className="text-foreground whitespace-pre-line">{str(valuation.summary)}</div>
                        </div>
                      )}
                      {valuationDoc && (
                        <Button asChild className="gap-2">
                          <a href={apiUrl(withPreview(valuationDoc.download_url))} target="_blank" rel="noopener noreferrer">
                            <Download className="h-4 w-4" /> Download valuation report
                          </a>
                        </Button>
                      )}
                    </CardContent>
                  </Card>
                )}

                {scenarios.length > 0 && (
                  <SectionCard icon={TrendingUp} title="ROI Expectations & Scenarios">
                    <div className="grid sm:grid-cols-3 gap-3" data-testid="scenarios">
                      {scenarios.map((s) => (
                        <div key={s.label} className={`p-3 rounded-lg border ${tone(s.tone)}`}>
                          <div className="text-xs uppercase opacity-80">{s.label}</div>
                          <div className="text-sm font-medium mt-1">{s.outcome}</div>
                        </div>
                      ))}
                    </div>
                    <p className="mt-3 text-[11px] text-muted-foreground">Scenarios are illustrations, not promises of return.</p>
                  </SectionCard>
                )}

                {risks.length > 0 && (
                  <SectionCard icon={AlertTriangle} title="Risk Disclosures">
                    <div className="space-y-2" data-testid="risks">
                      {risks.map((r) => (
                        <div key={r.label} className="flex items-start gap-3 p-3 rounded-lg bg-secondary/40 border border-border">
                          {r.level && <Badge variant="outline" className={tone(r.level)}>{r.level.toUpperCase()}</Badge>}
                          <div>
                            <div className="text-sm font-medium text-foreground">{r.label}</div>
                            {r.note && <div className="text-xs text-muted-foreground">{r.note}</div>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </SectionCard>
                )}
              </TabsContent>

              {/* FINANCIALS */}
              <TabsContent value="financials" className="mt-6 space-y-6">
                {(projections.length > 0 || market.length > 0) && (
                  <div className="grid sm:grid-cols-2 gap-4">
                    {projections.length > 0 && (
                      <SectionCard icon={LineChart} title="Financial Projections">
                        <div className="space-y-2 text-sm">
                          {projections.map((r) => <Row key={r.label} label={r.label!} value={r.value} />)}
                        </div>
                      </SectionCard>
                    )}
                    {market.length > 0 && (
                      <SectionCard icon={Globe2} title="Market Analysis & Valuation">
                        <div className="space-y-2 text-sm">
                          {market.map((r) => <Row key={r.label} label={r.label!} value={r.value} />)}
                        </div>
                      </SectionCard>
                    )}
                  </div>
                )}

                {(hasPricing || str(cashflow.rentalProjection) || str(cashflow.costs) || str(cashflow.exitProjection) || appreciation != null) && (
                  <SectionCard icon={Banknote} title="Cash Flow & Return Expectations">
                    <div className="grid sm:grid-cols-3 gap-3 text-sm">
                      {hasPricing && (
                        <>
                          <Tile label="Current Asset Value" value={fmt(currentValue)} />
                          <Tile label="Next Phase Value" value={nextValue != null ? fmt(nextValue) : "—"} />
                          <Tile label="Projected Delivery Value" value={fmt(finalValue)} accent="success" />
                        </>
                      )}
                      <div className="sm:col-span-3 grid sm:grid-cols-2 gap-3">
                        {str(cashflow.rentalProjection) && (
                          <div className="p-3 rounded-lg bg-secondary/30 border border-border">
                            <div className="text-xs text-muted-foreground mb-1">Rental / Income Projections</div>
                            <div className="text-foreground whitespace-pre-line">{str(cashflow.rentalProjection)}</div>
                          </div>
                        )}
                        {str(cashflow.costs) && (
                          <div className="p-3 rounded-lg bg-secondary/30 border border-border">
                            <div className="text-xs text-muted-foreground mb-1">Development &amp; Operating Costs</div>
                            <div className="text-foreground whitespace-pre-line">{str(cashflow.costs)}</div>
                          </div>
                        )}
                        {appreciation != null && (
                          <div className="p-3 rounded-lg bg-secondary/30 border border-border">
                            <div className="text-xs text-muted-foreground mb-1">Appreciation Expectation</div>
                            <div className="text-success font-medium">+{appreciation}% over the project horizon (estimate)</div>
                          </div>
                        )}
                        {str(cashflow.exitProjection) && (
                          <div className="p-3 rounded-lg bg-secondary/30 border border-border">
                            <div className="text-xs text-muted-foreground mb-1">Exit Projection</div>
                            <div className="text-foreground whitespace-pre-line">{str(cashflow.exitProjection)}</div>
                          </div>
                        )}
                      </div>
                    </div>
                  </SectionCard>
                )}

                <SectionCard icon={Wallet} title="Fee Structure">
                  <div className="space-y-2 text-sm" data-testid="fee-structure">
                    <Row label="Platform Fee (one-time)" value={`${fees.platformFee}%`} />
                    <Row label="Management Fee (annual)" value={`${fees.managementFee}%`} />
                    {INSTALLMENT_MODELS.has(detail.model) && <Row label="Installment Fee (per payment)" value={`${fees.installmentFee}%`} />}
                    {fees.performanceFee != null && <Row label="Performance Fee (on profits)" value={`${fees.performanceFee}%`} />}
                    {fees.exitFee != null && <Row label="Exit Fee (on secondary sales)" value={`${fees.exitFee}%`} />}
                  </div>
                </SectionCard>

                {exits.length > 0 && (
                  <SectionCard icon={ArrowRight} title="Exit Mechanisms">
                    <div className="grid sm:grid-cols-2 gap-3" data-testid="exit-mechanisms">
                      {exits.map((e) => (
                        <div key={e.name} className="p-3 rounded-lg bg-secondary/40 border border-border">
                          <div className="flex items-center justify-between gap-2">
                            <div className="text-sm font-semibold text-foreground">{e.name}</div>
                            {e.eta && <Badge variant="outline" className="text-[10px]">{e.eta}</Badge>}
                          </div>
                          {e.description && <div className="text-xs text-muted-foreground mt-1">{e.description}</div>}
                        </div>
                      ))}
                    </div>
                  </SectionCard>
                )}
              </TabsContent>

              {/* SPV STRUCTURE */}
              <TabsContent value="structure" className="mt-6 space-y-6">
                <SectionCard icon={Layers} title="SPV & Legal Structure">
                  <div className="space-y-4 text-sm">
                    {spvRows.length > 0 ? (
                      <div className="grid sm:grid-cols-2 gap-3">
                        {spvRows.map((r) => (
                          <div key={r.label} className="p-3 bg-secondary/40 rounded-lg border border-border">
                            <div className="text-xs text-muted-foreground">{r.label}</div>
                            <div className="font-semibold text-foreground">{r.value}</div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-muted-foreground">SPV details have not been published for this listing yet.</p>
                    )}
                    {ownership.length > 0 && (
                      <div className="grid sm:grid-cols-2 gap-3">
                        {ownership.map((o) => (
                          <div key={o.label} className="p-3 bg-secondary/40 rounded-lg border border-border">
                            <div className="text-xs text-muted-foreground">{o.label}</div>
                            <div className="font-semibold text-foreground">{o.value}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </SectionCard>

                {compliance.length > 0 && (
                  <SectionCard icon={Shield} title="Compliance & Legal Framework">
                    <div className="grid sm:grid-cols-2 gap-3 text-sm" data-testid="compliance">
                      {compliance.map((line) => (
                        <div key={line} className="flex items-start gap-2 p-2.5 rounded-lg bg-secondary/40 border border-border">
                          <CheckCircle className="h-4 w-4 text-success shrink-0 mt-0.5" />
                          <span className="text-foreground">{line}</span>
                        </div>
                      ))}
                    </div>
                  </SectionCard>
                )}

                <div className="text-center">
                  <Button asChild variant="outline">
                    <Link to={`/spv-model/${detail.id}`}>View Full SPV Model</Link>
                  </Button>
                </div>
              </TabsContent>

              {/* DOCUMENTS */}
              <TabsContent value="documents" className="mt-6 space-y-6">
                <SectionCard icon={ScrollText} title="Property & Investment Documents">
                  {documentsPanel}
                </SectionCard>
              </TabsContent>

              {/* TIMELINE */}
              <TabsContent value="timeline" className="mt-6 space-y-6">
                <SectionCard icon={HardHat} title="Construction Phase & Pricing Progression">
                  {milestones.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No project milestones have been published yet.</p>
                  ) : (
                    <div className="space-y-4" data-testid="timeline">
                      <div className="grid sm:grid-cols-3 gap-3">
                        <Tile label="Current Phase" value={current?.title ?? "—"} note={current ? `${current.progress_pct ?? 0}% complete` : undefined} />
                        {hasPricing && <Tile label="Current Pricing" value={fmt(currentValue)} note={`Price index ${currentIndex}`} />}
                        {hasPricing && nextValue != null && (
                          <Tile label="Next Phase Pricing" value={fmt(nextValue)} note={`Estimated at ${next?.title ?? "next phase"}`} accent="success" />
                        )}
                      </div>
                      {hasPricing && (
                        <div className="text-xs text-muted-foreground p-3 rounded-lg bg-primary/5 border border-primary/20">
                          Estimated delivery valuation: <strong className="text-foreground">{fmt(finalValue)}</strong>. Estimates, not guarantees.
                        </div>
                      )}
                      <div className="space-y-3 pt-2">
                        {milestones.map((m) => {
                          const done = m.status === "completed";
                          const active = m.status === "in_progress";
                          const pct = done ? 100 : active ? m.progress_pct ?? 0 : 0;
                          return (
                            <div key={m.id} className="flex items-start gap-3">
                              <div className={`mt-1 h-3 w-3 rounded-full ${done ? "bg-success" : active ? "bg-primary animate-pulse" : "bg-muted"}`} />
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between gap-2">
                                  <span className="text-sm font-medium text-foreground">{m.title}</span>
                                  <span className="text-xs text-muted-foreground shrink-0">
                                    {fmtDate(m.target_date)}
                                    {m.value_index != null ? ` · Price index ${m.value_index}` : ""}
                                  </span>
                                </div>
                                {m.description && <div className="text-xs text-muted-foreground">{m.description}</div>}
                                <Progress value={pct} className="h-1.5 mt-1" />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </SectionCard>
              </TabsContent>

              {/* DEVELOPER */}
              <TabsContent value="developer" className="mt-6 space-y-6">
                <SectionCard icon={Briefcase} title="Developer / Owner Profile">
                  {!devName ? (
                    <p className="text-sm text-muted-foreground">No developer is named on this listing yet.</p>
                  ) : (
                    <div className="space-y-4" data-testid="developer-tab">
                      <div className="flex items-center gap-4">
                        {str(dev.logo) ? (
                          <img src={assetUrl(str(dev.logo))} alt={devName} className="h-16 w-16 rounded-xl object-cover border border-border" />
                        ) : (
                          <div className="h-16 w-16 rounded-xl bg-primary/10 text-primary flex items-center justify-center text-lg font-semibold">
                            {devName.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase()}
                          </div>
                        )}
                        <div>
                          <div className="text-lg font-semibold text-foreground">{devName}</div>
                          <div className="flex flex-wrap items-center gap-2 mt-1">
                            {dev.verified === true && (
                              <Badge variant="outline" className="bg-success/10 text-success border-success/30">
                                <CheckCircle className="h-3 w-3 mr-1" /> Verified developer
                              </Badge>
                            )}
                            {num(dev.rating) != null && (
                              <Badge variant="outline">
                                <Star className="h-3 w-3 mr-1 fill-warning text-warning" /> Rating {num(dev.rating)} / 5
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>

                      {devTiles.length > 0 && (
                        <div className="grid sm:grid-cols-3 gap-3 text-sm">
                          {devTiles.map((t) => <Tile key={t.label} label={t.label} value={t.value} />)}
                        </div>
                      )}

                      {str(dev.about) && (
                        <div>
                          <div className="text-xs uppercase text-muted-foreground mb-2">Company Overview</div>
                          <p className="text-sm text-muted-foreground whitespace-pre-line">{str(dev.about)}</p>
                        </div>
                      )}

                      {lines(dev.previousProjects).length > 0 && (
                        <div>
                          <div className="text-xs uppercase text-muted-foreground mb-2">Previous Projects</div>
                          <div className="grid sm:grid-cols-2 gap-2 text-sm">
                            {lines(dev.previousProjects).map((p) => (
                              <div key={p} className="flex items-center gap-2 p-2.5 rounded-lg bg-secondary/40 border border-border">
                                <CheckCircle className="h-4 w-4 text-success shrink-0" />
                                <span className="text-foreground">{p}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {lines(dev.verifications).length > 0 && (
                        <div>
                          <div className="text-xs uppercase text-muted-foreground mb-2">Verification &amp; Contact</div>
                          <div className="grid sm:grid-cols-2 gap-2 text-sm">
                            {lines(dev.verifications).map((v) => (
                              <div key={v} className="flex items-start gap-2 p-2.5 rounded-lg bg-secondary/40 border border-border">
                                <Shield className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                                <span className="text-foreground">{v}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      <div className="flex flex-wrap gap-2">
                        {devSlug && (
                          <Button asChild variant="outline" size="sm">
                            <Link to={`/developers/${encodeURIComponent(devSlug)}`}>View full developer profile</Link>
                          </Button>
                        )}
                        {str(dev.website) && (
                          <Button asChild variant="ghost" size="sm">
                            <a href={str(dev.website)} target="_blank" rel="noopener noreferrer nofollow">
                              Website <ExternalLink className="ml-1 h-3 w-3" />
                            </a>
                          </Button>
                        )}
                      </div>
                    </div>
                  )}
                </SectionCard>
              </TabsContent>
            </Tabs>

            {/* Invest & Payment */}
            <Card className="border-primary/40">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Wallet className="h-4 w-4 text-primary" /> Invest &amp; Payment
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid sm:grid-cols-3 gap-3">
                  <Tile label="Min. Investment" value={fmt(detail.minimum_investment)} />
                  <div className="p-3 rounded-lg bg-secondary/40 border border-border text-sm">
                    <div className="text-xs text-muted-foreground">Funding Progress</div>
                    <div className="font-semibold text-foreground">{Math.round(detail.funding_progress)}%</div>
                    <Progress value={detail.funding_progress} className="h-1.5 mt-1.5" />
                  </div>
                  <Tile label="Investors" value={detail.investors_count} />
                </div>
                <div className="grid sm:grid-cols-2 gap-3 text-xs text-muted-foreground">
                  <div className="p-3 rounded-lg bg-secondary/30 border border-border">
                    <div className="font-medium text-foreground mb-1">Payment</div>
                    Paid from your Capimax wallet balance.
                  </div>
                  <div className="p-3 rounded-lg bg-secondary/30 border border-border">
                    <div className="font-medium text-foreground mb-1">Payment Plans</div>
                    {INSTALLMENT_MODELS.has(detail.model) ? "Installment plan · 6 to 24 months" : "Full payment"}
                  </div>
                </div>
                <Button className="w-full" size="lg" onClick={scrollToInvest}>
                  <Banknote className="h-4 w-4 mr-2" /> Invest Now
                </Button>
              </CardContent>
            </Card>
          </div>

          {/* Sidebar */}
          <aside className="space-y-6 min-w-0">
            <div id="invest-panel" className="scroll-mt-24">{investPanel}</div>
            {sidebarExtra}

            {devName && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Briefcase className="h-4 w-4 text-primary" /> Developer / Owner Profile
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <div className="font-semibold text-foreground">{devName}</div>
                  {num(dev.rating) != null && <div className="text-muted-foreground">Rating: {num(dev.rating)} / 5</div>}
                  {num(dev.projectsCompleted) != null && (
                    <div className="text-muted-foreground">Projects completed: {num(dev.projectsCompleted)}</div>
                  )}
                  {devSlug && (
                    <Link to={`/developers/${encodeURIComponent(devSlug)}`} className="inline-block text-primary text-sm hover:underline">
                      View profile
                    </Link>
                  )}
                </CardContent>
              </Card>
            )}

            {ownership.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Layers className="h-4 w-4 text-primary" /> SPV &amp; Ownership Structure
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {ownership.map((o) => <Row key={o.label} label={o.label!} value={o.value} />)}
                </CardContent>
              </Card>
            )}

            {compliance.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Shield className="h-4 w-4 text-primary" /> Compliance &amp; Custody
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-xs text-muted-foreground space-y-2">
                  {compliance.slice(0, 4).map((line) => (
                    <div key={line} className="flex items-center gap-2">
                      <CheckCircle className="h-3.5 w-3.5 text-success shrink-0" /> {line}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Users className="h-4 w-4 text-primary" /> Ownership Models
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm">
                <Link to="/property-types" className="flex items-center justify-between p-2 rounded-lg bg-secondary/40 border border-border hover:border-primary/40">
                  <span className="text-foreground">Compare how each model works</span>
                  <ArrowRight className="h-4 w-4 text-muted-foreground" />
                </Link>
              </CardContent>
            </Card>

            <Card className="border-primary/30">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Scale className="h-4 w-4 text-primary" /> Regulatory Note
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">
                Figures described as estimated, expected or projected are forecasts, not guarantees.
                Final terms are governed by the SPV subscription documents.
              </CardContent>
            </Card>
          </aside>
        </div>
      </main>
    </div>
  );
}
