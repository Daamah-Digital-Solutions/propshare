import { Link, useParams, Navigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  ArrowLeft,
  MapPin,
  Building2,
  TrendingUp,
  Shield,
  FileText,
  Download,
  ChevronRight,
  CheckCircle,
  Wallet,
  AlertTriangle,
  Target,
  CalendarClock,
  Hammer,
  Handshake,
  Layers,
  Banknote,
  ArrowRight,
  ScrollText,
  Briefcase,
  LineChart,
  HardHat,
  Scale,
  Globe2,
  Users,
} from "lucide-react";
import { Loader2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import {
  type SampleOwnershipModel,
  type SampleProperty,
} from "@/data/sampleProperties";
import { propertyApi } from "@/lib/api";
import { toSampleProperty } from "@/lib/properties";


// Map URL slug → sample model + display config
const MODEL_MAP: Record<
  string,
  {
    model: SampleOwnershipModel;
    title: string;
    tagline: string;
    icon: typeof Hammer;
    accent: string;
  }
> = {
  option: {
    model: "option",
    title: "Option Property",
    tagline: "Pay a small premium today, decide whether to activate later",
    icon: Target,
    accent: "from-violet-500/15 to-violet-500/0 border-violet-500/30",
  },
  future: {
    model: "future",
    title: "Future Property",
    tagline: "Lock today's price, settle at delivery — capture appreciation",
    icon: CalendarClock,
    accent: "from-blue-500/15 to-blue-500/0 border-blue-500/30",
  },
  shared: {
    model: "shared-development",
    title: "Shared Development Property",
    tagline: "Co-invest in land + construction alongside the developer",
    icon: Handshake,
    accent: "from-fuchsia-500/15 to-fuchsia-500/0 border-fuchsia-500/30",
  },
  installment: {
    model: "installment",
    title: "Installment-Based Property",
    tagline: "Pay in monthly installments while the property is built",
    icon: Hammer,
    accent: "from-amber-500/15 to-amber-500/0 border-amber-500/30",
  },
};

const tone = (
  t: "low" | "medium" | "high" | "positive" | "neutral" | "negative",
) => {
  switch (t) {
    case "low":
    case "positive":
      return "bg-success/10 text-success border-success/30";
    case "medium":
    case "neutral":
      return "bg-amber-500/10 text-amber-600 border-amber-500/30";
    case "high":
    case "negative":
      return "bg-destructive/10 text-destructive border-destructive/30";
  }
};

const fmt = (n: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);

const ModelSpecificBlock = ({ p }: { p: SampleProperty }) => {
  if (p.optionTerms) {
    const o = p.optionTerms;
    return (
      <Card className="border-violet-500/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Target className="h-4 w-4 text-violet-500" /> Option Structure
          </CardTitle>
        </CardHeader>
        <CardContent className="grid sm:grid-cols-2 gap-4 text-sm">
          <div className="p-3 rounded-lg bg-secondary/40 border border-border">
            <div className="text-xs text-muted-foreground">Option Premium</div>
            <div className="font-semibold text-foreground">{o.optionPremium}</div>
          </div>
          <div className="p-3 rounded-lg bg-secondary/40 border border-border">
            <div className="text-xs text-muted-foreground">Activation Deadline</div>
            <div className="font-semibold text-foreground">{o.activationDeadline}</div>
          </div>
          <div className="p-3 rounded-lg bg-secondary/40 border border-border">
            <div className="text-xs text-muted-foreground">Locked Strike Price</div>
            <div className="font-semibold text-foreground">{o.lockedPrice}</div>
          </div>
          <div className="p-3 rounded-lg bg-secondary/40 border border-border">
            <div className="text-xs text-muted-foreground">Projected Future Value</div>
            <div className="font-semibold text-success">{o.futureValue}</div>
          </div>
          <div className="sm:col-span-2 p-3 rounded-lg bg-violet-500/5 border border-violet-500/30 text-xs text-muted-foreground">
            Activation conditions: pay remaining strike before deadline · transferable on
            secondary market · liquidity-provider instant assignment available · option
            expires worthless if not activated (loss capped at premium).
          </div>
        </CardContent>
      </Card>
    );
  }
  if (p.futureTerms) {
    const f = p.futureTerms;
    return (
      <Card className="border-blue-500/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarClock className="h-4 w-4 text-blue-500" /> Future Agreement Structure
          </CardTitle>
        </CardHeader>
        <CardContent className="grid sm:grid-cols-2 gap-4 text-sm">
          <div className="p-3 rounded-lg bg-secondary/40 border border-border">
            <div className="text-xs text-muted-foreground">Settlement Date</div>
            <div className="font-semibold text-foreground">{f.settlementDate}</div>
          </div>
          <div className="p-3 rounded-lg bg-secondary/40 border border-border">
            <div className="text-xs text-muted-foreground">Locked Future Price</div>
            <div className="font-semibold text-foreground">{f.futurePrice}</div>
          </div>
          <div className="p-3 rounded-lg bg-secondary/40 border border-border sm:col-span-2">
            <div className="text-xs text-muted-foreground">Appreciation Projection</div>
            <div className="font-semibold text-success">{f.appreciationProjection}</div>
          </div>
          <div className="sm:col-span-2 p-3 rounded-lg bg-blue-500/5 border border-blue-500/30 text-xs text-muted-foreground">
            {f.constructionMilestoneImpact}
          </div>
        </CardContent>
      </Card>
    );
  }
  if (p.sharedTerms) {
    const s = p.sharedTerms;
    return (
      <Card className="border-fuchsia-500/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Handshake className="h-4 w-4 text-fuchsia-500" /> Shared Development Structure
          </CardTitle>
        </CardHeader>
        <CardContent className="grid sm:grid-cols-2 gap-4 text-sm">
          <div className="p-3 rounded-lg bg-secondary/40 border border-border">
            <div className="text-xs text-muted-foreground">Land Participation</div>
            <div className="font-semibold text-foreground">{s.landShare}</div>
          </div>
          <div className="p-3 rounded-lg bg-secondary/40 border border-border">
            <div className="text-xs text-muted-foreground">Construction Participation</div>
            <div className="font-semibold text-foreground">{s.constructionShare}</div>
          </div>
          <div className="p-3 rounded-lg bg-secondary/40 border border-border">
            <div className="text-xs text-muted-foreground">Profit Split</div>
            <div className="font-semibold text-foreground">{s.profitSplit}</div>
          </div>
          <div className="p-3 rounded-lg bg-secondary/40 border border-border">
            <div className="text-xs text-muted-foreground">Governance</div>
            <div className="font-semibold text-foreground">{s.governance}</div>
          </div>
          <div className="sm:col-span-2 p-3 rounded-lg bg-fuchsia-500/5 border border-fuchsia-500/30 text-xs text-muted-foreground">
            Investors benefit from property appreciation, developer profit margins,
            market growth, and project-level development profits — distributed pro-rata
            after the preferred return hurdle.
          </div>
        </CardContent>
      </Card>
    );
  }
  if (p.installmentTerms) {
    const i = p.installmentTerms;
    return (
      <Card className="border-amber-500/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Hammer className="h-4 w-4 text-amber-500" /> Installment Plan Structure
          </CardTitle>
        </CardHeader>
        <CardContent className="grid sm:grid-cols-2 gap-4 text-sm">
          <div className="p-3 rounded-lg bg-secondary/40 border border-border">
            <div className="text-xs text-muted-foreground">Down Payment</div>
            <div className="font-semibold text-foreground">{i.downPayment}</div>
          </div>
          <div className="p-3 rounded-lg bg-secondary/40 border border-border">
            <div className="text-xs text-muted-foreground">Duration</div>
            <div className="font-semibold text-foreground">{i.months} months</div>
          </div>
          <div className="p-3 rounded-lg bg-secondary/40 border border-border sm:col-span-2">
            <div className="text-xs text-muted-foreground">Monthly Schedule</div>
            <div className="font-semibold text-foreground">{i.monthly}</div>
          </div>
          <div className="sm:col-span-2 p-3 rounded-lg bg-amber-500/5 border border-amber-500/30 text-xs text-muted-foreground">
            {i.completionUnlock}
          </div>
        </CardContent>
      </Card>
    );
  }
  return null;
};

const OptionDetailedSection = ({
  property,
  currentValue,
  nextValue,
  finalValue,
  currentMilestone,
  nextMilestone,
}: {
  property: SampleProperty;
  currentValue: number;
  nextValue: number;
  finalValue: number;
  currentMilestone: SampleProperty["timeline"][number];
  nextMilestone?: SampleProperty["timeline"][number];
}) => {
  const o = property.optionTerms;
  if (!o) return null;
  const remainingPayment = Math.max(property.propertyValue - property.minInvestment, 0);

  const dataPoints = [
    { label: "Option Price (Premium)", value: o.optionPremium, tone: "primary" },
    { label: "Option Activation Period", value: "12-month exercise window", tone: "neutral" },
    { label: "Option Activation Deadline", value: o.activationDeadline, tone: "warning" },
    { label: "Locked Strike Price", value: o.lockedPrice, tone: "neutral" },
    { label: "Current Property Price", value: fmt(currentValue), tone: "neutral" },
    { label: "Expected Next Phase Price", value: fmt(nextValue), tone: "success" },
    { label: "Estimated Future Property Value", value: o.futureValue, tone: "success" },
    { label: "Remaining Payment After Activation", value: fmt(remainingPayment), tone: "primary" },
  ];

  return (
    <div className="space-y-6">
      {/* Headline data grid */}
      <Card className="border-violet-500/30 bg-gradient-to-br from-violet-500/5 to-transparent">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Target className="h-4 w-4 text-violet-500" /> Option Ownership Details
          </CardTitle>
        </CardHeader>
        <CardContent className="grid sm:grid-cols-2 gap-3">
          {dataPoints.map((d) => (
            <div
              key={d.label}
              className={`p-3 rounded-lg border ${
                d.tone === "success"
                  ? "bg-success/5 border-success/30"
                  : d.tone === "warning"
                  ? "bg-amber-500/5 border-amber-500/30"
                  : d.tone === "primary"
                  ? "bg-violet-500/5 border-violet-500/30"
                  : "bg-secondary/40 border-border"
              }`}
            >
              <div className="text-xs text-muted-foreground">{d.label}</div>
              <div
                className={`font-semibold ${
                  d.tone === "success"
                    ? "text-success"
                    : d.tone === "warning"
                    ? "text-amber-600"
                    : "text-foreground"
                }`}
              >
                {d.value}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Construction & appreciation linkage */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <HardHat className="h-4 w-4 text-primary" /> Construction Progress &amp; Appreciation
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid sm:grid-cols-3 gap-3 text-sm">
            <div className="p-3 rounded-lg bg-secondary/40 border border-border">
              <div className="text-xs text-muted-foreground">Current Stage</div>
              <div className="font-semibold text-foreground">{currentMilestone.label}</div>
              <Progress value={currentMilestone.progress} className="h-1.5 mt-2" />
              <div className="text-xs text-muted-foreground mt-1">{currentMilestone.progress}% complete</div>
            </div>
            <div className="p-3 rounded-lg bg-secondary/40 border border-border">
              <div className="text-xs text-muted-foreground">Independent Valuation</div>
              <div className="font-semibold text-foreground">{fmt(currentValue)}</div>
              <div className="text-xs text-muted-foreground mt-1">NAV index {currentMilestone.valueIndex}</div>
            </div>
            <div className="p-3 rounded-lg bg-success/5 border border-success/30">
              <div className="text-xs text-muted-foreground">Projected Delivery Value</div>
              <div className="font-semibold text-success">{fmt(finalValue)}</div>
              <div className="text-xs text-muted-foreground mt-1">After full milestones</div>
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-3 text-xs text-muted-foreground">
            <div className="p-3 rounded-lg bg-secondary/30 border border-border">
              <div className="font-medium text-foreground mb-1">Engineering Progress Updates</div>
              Quarterly engineering reports certify physical progress and trigger NAV revisions when milestones are signed off.
            </div>
            <div className="p-3 rounded-lg bg-secondary/30 border border-border">
              <div className="font-medium text-foreground mb-1">Independent Reports</div>
              Third-party valuers (RICS-aligned) publish updated property valuations after each major construction milestone.
            </div>
          </div>

          <div className="text-xs text-muted-foreground p-3 rounded-lg bg-primary/5 border border-primary/20">
            As construction milestones progress and independent valuation updates are completed, the
            ownership value and option pricing may increase. Estimated next phase price:{" "}
            <strong className="text-foreground">{fmt(nextValue)}</strong>
            {nextMilestone ? ` at ${nextMilestone.label}.` : "."}
          </div>
        </CardContent>
      </Card>

      {/* Activation system */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarClock className="h-4 w-4 text-primary" /> Option Activation System
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="grid sm:grid-cols-3 gap-3">
            <div className="p-3 rounded-lg bg-secondary/40 border border-border">
              <div className="text-xs text-muted-foreground">Activation Date</div>
              <div className="font-semibold text-foreground">Anytime within window</div>
              <div className="text-xs text-muted-foreground mt-1">Until {o.activationDeadline}</div>
            </div>
            <div className="p-3 rounded-lg bg-secondary/40 border border-border">
              <div className="text-xs text-muted-foreground">Activation Conditions</div>
              <div className="font-semibold text-foreground">Pay remaining strike</div>
              <div className="text-xs text-muted-foreground mt-1">Wallet · Bank · Stablecoin</div>
            </div>
            <div className="p-3 rounded-lg bg-amber-500/5 border border-amber-500/30">
              <div className="text-xs text-muted-foreground">Countdown</div>
              <div className="font-semibold text-amber-600">~{o.activationDeadline}</div>
              <div className="text-xs text-muted-foreground mt-1">Decision window open</div>
            </div>
          </div>

          <div>
            <div className="text-xs uppercase text-muted-foreground mb-2">Ownership Conversion Process</div>
            <div className="space-y-2">
              {[
                "Investor signals activation through the dashboard",
                "Remaining strike payment settled via escrow",
                "SPV issues digital ownership certificate to investor",
                "Investor becomes an official ownership holder",
                "Eligible for rental returns, appreciation gains, ownership rights and exit options",
              ].map((step, i) => (
                <div key={step} className="flex items-start gap-3 p-2.5 rounded-lg bg-secondary/40 border border-border">
                  <div className="h-6 w-6 rounded-full bg-primary text-primary-foreground text-xs font-semibold flex items-center justify-center shrink-0">
                    {i + 1}
                  </div>
                  <div className="text-foreground">{step}</div>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Non-activation warning */}
      <Card className="border-destructive/40 bg-destructive/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base text-destructive">
            <AlertTriangle className="h-4 w-4" /> Important: Non-Activation Warning
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm space-y-2">
          <p className="text-foreground font-medium">
            If the option is not activated before the activation deadline, the option may expire and
            the investor may lose the option value paid.
          </p>
          <p className="text-xs text-muted-foreground">
            The maximum loss is strictly capped at the option premium (
            <strong className="text-foreground">{o.optionPremium}</strong>). No further liability,
            margin call, or claim applies. To avoid expiry, investors may either activate the option
            or transfer the position via the secondary market before the deadline.
          </p>
        </CardContent>
      </Card>

      {/* Secondary market / exit before activation */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ArrowRight className="h-4 w-4 text-primary" /> Secondary Market &amp; Pre-Activation Exit
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="grid sm:grid-cols-3 gap-3">
            {[
              { name: "Sell Option", desc: "List the option position on the secondary market at intrinsic + time value.", eta: "1–7 days" },
              { name: "Transfer Rights", desc: "Assign ownership rights of the option to another verified investor.", eta: "Instant" },
              { name: "Liquidity Provider", desc: "Exit instantly to a Capimax-approved liquidity provider (when available).", eta: "Same day" },
            ].map((e) => (
              <div key={e.name} className="p-3 rounded-lg bg-secondary/40 border border-border">
                <div className="flex items-center justify-between">
                  <div className="font-semibold text-foreground">{e.name}</div>
                  <Badge variant="outline" className="text-[10px]">{e.eta}</Badge>
                </div>
                <div className="text-xs text-muted-foreground mt-1">{e.desc}</div>
              </div>
            ))}
          </div>
          <div className="p-3 rounded-lg bg-success/5 border border-success/30 text-xs text-muted-foreground">
            If the property value increases due to construction progress, valuation updates, market
            appreciation or development milestones, the investor may potentially profit from a
            <strong className="text-foreground"> higher option resale value</strong> before activation —
            without committing the remaining strike payment.
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

const ConstructionValuationSection = ({
  property,
  cfg,
  baseValue,
  currentValue,
  nextValue,
  finalValue,
  currentMilestone,
  nextMilestone,
}: {
  property: SampleProperty;
  cfg: { title: string; model: SampleOwnershipModel };
  baseValue: number;
  currentValue: number;
  nextValue: number;
  finalValue: number;
  currentMilestone: SampleProperty["timeline"][number];
  nextMilestone?: SampleProperty["timeline"][number];
}) => {
  const overallProgress = Math.round(
    property.timeline.reduce((acc, m) => acc + (m.progress ?? 0), 0) /
      property.timeline.length,
  );
  const appreciationPct = property.capitalAppreciation ?? 0;
  const nextDeltaPct = currentValue > 0
    ? Math.round(((nextValue - currentValue) / currentValue) * 1000) / 10
    : 0;
  const phaseStages = property.timeline.length;
  const completedStages = property.timeline.filter((m) => m.status === "done").length;

  const v = property as SampleProperty & { valuationProvider?: string; valuationDate?: string };
  const valuationProvider =
    v.valuationProvider ?? "JLL · Knight Frank · Capimax Independent Valuation Panel";
  const reportDate = v.valuationDate ?? `Q${Math.min(4, completedStages + 1)} ${new Date().getFullYear()}`;

  return (
    <div className="space-y-6">
      {/* 1. CONSTRUCTION PROGRESS INDICATOR */}
      <Card className="border-primary/30 bg-gradient-to-br from-primary/5 to-transparent">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <HardHat className="h-4 w-4 text-primary" /> Construction Progress Indicator
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid sm:grid-cols-[auto,1fr] gap-5 items-center">
            {/* Circular indicator */}
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
                  strokeDasharray={`${(overallProgress / 100) * 264} 264`}
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-bold text-foreground">{overallProgress}%</span>
                <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Complete</span>
              </div>
            </div>
            <div className="space-y-3">
              <div>
                <div className="text-xs uppercase text-muted-foreground">Current Construction Phase</div>
                <div className="text-lg font-semibold text-foreground">{currentMilestone.label}</div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  Stage {Math.max(1, completedStages + 1)} of {phaseStages} ·
                  {nextMilestone ? ` Next: ${nextMilestone.label}` : " Final stage"}
                </div>
              </div>
              <Progress value={overallProgress} className="h-2" />
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div className="p-2 rounded-md bg-secondary/50 border border-border">
                  <div className="text-muted-foreground">Engineering</div>
                  <div className="font-semibold text-success">Certified</div>
                </div>
                <div className="p-2 rounded-md bg-secondary/50 border border-border">
                  <div className="text-muted-foreground">Milestone Audit</div>
                  <div className="font-semibold text-foreground">On track</div>
                </div>
                <div className="p-2 rounded-md bg-secondary/50 border border-border">
                  <div className="text-muted-foreground">Delivery ETA</div>
                  <div className="font-semibold text-foreground">
                    {property.timeline[property.timeline.length - 1]?.date ?? "—"}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Stage timeline */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {property.timeline.map((m, i) => {
              const state =
                m.status === "done"
                  ? "border-success/40 bg-success/5"
                  : m.status === "active"
                  ? "border-primary/50 bg-primary/10"
                  : "border-border bg-secondary/30";
              return (
                <div key={i} className={`p-2.5 rounded-lg border ${state}`}>
                  <div className="flex items-center gap-1.5">
                    <div
                      className={`h-2 w-2 rounded-full ${
                        m.status === "done"
                          ? "bg-success"
                          : m.status === "active"
                          ? "bg-primary animate-pulse"
                          : "bg-muted-foreground/40"
                      }`}
                    />
                    <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                      {m.status === "done" ? "Done" : m.status === "active" ? "Active" : "Upcoming"}
                    </span>
                  </div>
                  <div className="text-xs font-semibold text-foreground mt-1 leading-tight">
                    {m.label}
                  </div>
                  <Progress value={m.progress} className="h-1 mt-1.5" />
                  <div className="text-[10px] text-muted-foreground mt-1">{m.progress}%</div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* 2. PRICE & APPRECIATION INDICATOR */}
      <Card className="border-success/30 bg-gradient-to-br from-success/5 to-transparent">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <TrendingUp className="h-4 w-4 text-success" /> Price &amp; Appreciation Indicator
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
            <div className="p-3 rounded-lg bg-secondary/40 border border-border">
              <div className="text-xs text-muted-foreground">Launch / Previous Phase Price</div>
              <div className="font-semibold text-foreground">{fmt(baseValue)}</div>
              <div className="text-[11px] text-muted-foreground mt-1">Initial offering reference</div>
            </div>
            <div className="p-3 rounded-lg bg-primary/5 border border-primary/30">
              <div className="text-xs text-muted-foreground">Current Property Price</div>
              <div className="font-semibold text-foreground">{fmt(currentValue)}</div>
              <div className="text-[11px] text-muted-foreground mt-1">
                NAV index {currentMilestone.valueIndex}
              </div>
            </div>
            <div className="p-3 rounded-lg bg-success/10 border border-success/30">
              <div className="text-xs text-muted-foreground">Expected Next Phase Price</div>
              <div className="font-semibold text-success">{fmt(nextValue)}</div>
              <div className="text-[11px] text-muted-foreground mt-1">
                {nextMilestone ? `At ${nextMilestone.label}` : "Final phase"}
                {nextDeltaPct > 0 ? ` · +${nextDeltaPct}%` : ""}
              </div>
            </div>
            <div className="p-3 rounded-lg bg-success/10 border border-success/40">
              <div className="text-xs text-muted-foreground">Estimated Future Valuation</div>
              <div className="font-semibold text-success">{fmt(finalValue)}</div>
              <div className="text-[11px] text-muted-foreground mt-1">
                Projected at delivery · +{appreciationPct}% horizon
              </div>
            </div>
          </div>

          {/* Pricing progression bar */}
          <div className="relative pt-2">
            <div className="h-2 rounded-full bg-secondary overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-primary via-primary to-success transition-all"
                style={{ width: `${Math.min(100, Math.max(5, overallProgress))}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] uppercase text-muted-foreground mt-1.5">
              <span>Launch</span>
              <span>Construction</span>
              <span>Delivery</span>
            </div>
          </div>

          <div className="text-xs text-muted-foreground p-3 rounded-lg bg-primary/5 border border-primary/20">
            As construction milestones and independent valuation updates progress, the property
            price and ownership value may increase. Current uplift from launch:{" "}
            <strong className="text-success">
              +{Math.max(0, Math.round(((currentValue - baseValue) / baseValue) * 1000) / 10)}%
            </strong>
            . Projected total appreciation at delivery:{" "}
            <strong className="text-success">+{appreciationPct}%</strong>.
          </div>
        </CardContent>
      </Card>

      {/* 3. INDEPENDENT VALUATION REPORT */}
      <Card className="border-border bg-gradient-to-br from-secondary/40 to-transparent">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Scale className="h-4 w-4 text-primary" /> Independent Valuation Report
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="grid sm:grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-card border border-border">
              <div className="text-xs text-muted-foreground">Valuation Provider</div>
              <div className="font-semibold text-foreground">{valuationProvider}</div>
              <div className="text-[11px] text-muted-foreground mt-1">
                RICS-aligned · Independent third-party panel
              </div>
            </div>
            <div className="p-3 rounded-lg bg-card border border-border">
              <div className="text-xs text-muted-foreground">Report Issue Date</div>
              <div className="font-semibold text-foreground">{reportDate}</div>
              <div className="text-[11px] text-muted-foreground mt-1">
                Refreshed each construction milestone
              </div>
            </div>
            <div className="p-3 rounded-lg bg-card border border-border">
              <div className="text-xs text-muted-foreground">Latest Valuation Summary</div>
              <div className="font-semibold text-foreground">{fmt(currentValue)}</div>
              <div className="text-[11px] text-muted-foreground mt-1">
                Reflects {overallProgress}% completion · NAV {currentMilestone.valueIndex}
              </div>
            </div>
            <div className="p-3 rounded-lg bg-card border border-border">
              <div className="text-xs text-muted-foreground">Development Impact on Valuation</div>
              <div className="font-semibold text-success">+{appreciationPct}% projected</div>
              <div className="text-[11px] text-muted-foreground mt-1">
                Driven by construction progress &amp; market dynamics
              </div>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-secondary/40 border border-border">
            <div className="text-xs uppercase text-muted-foreground mb-1">Market Analysis</div>
            <div className="text-foreground text-sm">
              {property.marketAnalysis?.[0]?.value ??
                "Local submarket showing positive absorption, supply-demand balance and prime-area appreciation supportive of the development thesis."}
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-2">
            <Button variant="outline" className="gap-2" disabled title="Reports are not available yet">
              <FileText className="h-4 w-4" /> View Full Report
            </Button>
            <Button className="gap-2" disabled title="Document downloads are not available yet">
              <Download className="h-4 w-4" /> Download Valuation PDF
            </Button>
          </div>

          <div className="text-[11px] text-muted-foreground">
            Valuations are independently issued, signed and archived. Reports are made available to
            verified investors and updated after each major milestone audit.
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

const AdvancedPropertyPage = () => {
  const { model } = useParams();
  const cfg = model ? MODEL_MAP[model] : undefined;

  const { data: list, isLoading } = useQuery({
    queryKey: ["properties", "model", cfg?.model],
    queryFn: () => propertyApi.list({ model: cfg!.model, limit: 1 }),
    enabled: !!cfg,
  });
  const ref = list?.items[0]?.slug ?? list?.items[0]?.id;
  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["property", ref],
    queryFn: () => propertyApi.get(ref as string),
    enabled: !!ref,
  });

  if (!cfg) return <Navigate to="/marketplace" replace />;
  if (isLoading || detailLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }
  if (!detail) return <Navigate to="/marketplace" replace />;

  const property = toSampleProperty(detail);
  // A few presentational fields aren't part of SampleProperty; read them off an
  // optional extension instead of `any`.
  const extra = property as SampleProperty & {
    valuationProvider?: string;
    valuationDate?: string;
    propertyType?: string;
    rentalProjection?: string;
  };
  const Icon = cfg.icon;
  const timeline = property.timeline ?? [];
  const fallbackMilestone = {
    label: "Listed",
    date: "Today",
    progress: 0,
    valueIndex: 100,
    status: "active" as const,
  };
  const currentMilestone =
    timeline.find((m) => m.status === "active") ?? timeline[0] ?? fallbackMilestone;
  const nextMilestone = timeline.find((m) => m.status === "upcoming");
  const baseValue = property.propertyValue;
  const currentValue = Math.round((baseValue * currentMilestone.valueIndex) / 100);
  const nextValue = nextMilestone
    ? Math.round((baseValue * nextMilestone.valueIndex) / 100)
    : currentValue;
  const finalValue = Math.round(
    (baseValue * (timeline[timeline.length - 1]?.valueIndex ?? 100)) / 100,
  );

  return (
    <div className="min-h-screen bg-background">
      <main>
        {/* Breadcrumb */}
        <div className="bg-secondary/30 border-b border-border">
          <div className="container mx-auto px-4 py-4 flex items-center gap-2 text-sm">
            <Link to="/" className="text-muted-foreground hover:text-foreground">Home</Link>
            <ChevronRight size={14} className="text-muted-foreground" />
            <Link to="/marketplace" className="text-muted-foreground hover:text-foreground">Marketplace</Link>
            <ChevronRight size={14} className="text-muted-foreground" />
            <span className="text-foreground font-medium">{cfg.title}</span>
          </div>
        </div>

        {/* Hero */}
        <section className={`relative bg-gradient-to-br ${cfg.accent} border-b border-border`}>
          <div className="container mx-auto px-4 py-10">
            <Link to="/marketplace" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6">
              <ArrowLeft size={16} /> Back to Marketplace
            </Link>
            <div className="grid lg:grid-cols-2 gap-8 items-start">
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Badge className="bg-background/70 text-foreground border-border">
                    <Icon className="h-3.5 w-3.5 mr-1" /> {cfg.title}
                  </Badge>
                  <Badge variant="outline">Advanced Opportunity</Badge>
                  <Badge variant="outline">Educational Demo</Badge>
                </div>
                <h1 className="text-3xl md:text-4xl font-bold text-foreground mb-3">{property.title}</h1>
                <p className="text-muted-foreground mb-4">{cfg.tagline}</p>
                <p className="text-sm text-muted-foreground mb-6">{property.description}</p>
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-6">
                  <MapPin size={16} /> {property.location}
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 rounded-lg bg-card border border-border">
                    <div className="text-[10px] uppercase text-muted-foreground">Asset Value</div>
                    <div className="font-bold text-foreground">{fmt(baseValue)}</div>
                  </div>
                  <div className="p-3 rounded-lg bg-card border border-border">
                    <div className="text-[10px] uppercase text-muted-foreground">Min. Ticket</div>
                    <div className="font-bold text-foreground">{fmt(property.minInvestment)}</div>
                  </div>
                  <div className="p-3 rounded-lg bg-card border border-border">
                    <div className="text-[10px] uppercase text-muted-foreground">Appreciation</div>
                    <div className="font-bold text-success">+{property.capitalAppreciation ?? 0}%</div>
                  </div>
                  <div className="p-3 rounded-lg bg-card border border-border">
                    <div className="text-[10px] uppercase text-muted-foreground">Investors</div>
                    <div className="font-bold text-foreground">{property.investorsCount}</div>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl overflow-hidden border border-border">
                <img src={property.image} alt={property.title} className="w-full h-72 object-cover" />
                {property.gallery.length > 1 && (
                  <div className="grid grid-cols-3 gap-1 bg-card p-1">
                    {property.gallery.slice(0, 3).map((g, idx) => (
                      <img key={idx} src={g} alt="" className="h-20 w-full object-cover rounded" />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>

        <div className="container mx-auto px-4 py-10 grid lg:grid-cols-3 gap-8">
          {/* Main content */}
          <div className="lg:col-span-2 space-y-6">
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
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Building2 className="h-4 w-4 text-primary" /> Property Overview
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground space-y-4">
                    <p>{property.description}</p>
                    <div>
                      <div className="text-xs uppercase text-muted-foreground mb-2">Investment Highlights</div>
                      <div className="grid sm:grid-cols-2 gap-2">
                        {[
                          `Opportunity Model: ${cfg.title}`,
                          `Property Type: ${extra.propertyType ?? "Residential"}`,
                          `Projected Appreciation: +${property.capitalAppreciation ?? 0}%`,
                          `Asset Value: ${fmt(baseValue)}`,
                          `Minimum Ticket: ${fmt(property.minInvestment)}`,
                          `Active Investors: ${property.investorsCount}`,
                        ].map((h) => (
                          <div key={h} className="flex items-start gap-2 text-sm p-2.5 rounded-lg bg-secondary/40 border border-border">
                            <CheckCircle className="h-4 w-4 text-success mt-0.5 shrink-0" />
                            <span className="text-foreground">{h}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs uppercase text-muted-foreground mb-2">Ownership Structure Summary</div>
                      <div className="grid sm:grid-cols-2 gap-3">
                        {property.ownershipStructure.map((o) => (
                          <div key={o.label} className="p-3 bg-secondary/40 rounded-lg border border-border">
                            <div className="text-xs text-muted-foreground">{o.label}</div>
                            <div className="font-semibold text-foreground">{o.value}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <ModelSpecificBlock p={property} />

                <ConstructionValuationSection
                  property={property}
                  cfg={cfg}
                  baseValue={baseValue}
                  currentValue={currentValue}
                  nextValue={nextValue}
                  finalValue={finalValue}
                  currentMilestone={currentMilestone}
                  nextMilestone={nextMilestone}
                />

                {cfg.model === "option" && (
                  <OptionDetailedSection
                    property={property}
                    currentValue={currentValue}
                    nextValue={nextValue}
                    finalValue={finalValue}
                    currentMilestone={currentMilestone}
                    nextMilestone={nextMilestone}
                  />
                )}

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <TrendingUp className="h-4 w-4 text-primary" /> ROI Expectations &amp; Scenarios
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="grid sm:grid-cols-3 gap-3">
                    {property.scenarios.map((s) => (
                      <div key={s.label} className={`p-3 rounded-lg border ${tone(s.tone)}`}>
                        <div className="text-xs uppercase opacity-80">{s.label}</div>
                        <div className="text-sm font-medium mt-1">{s.outcome}</div>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <AlertTriangle className="h-4 w-4 text-primary" /> Risk Disclosures
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {property.risks.map((r) => (
                      <div key={r.label} className="flex items-start gap-3 p-3 rounded-lg bg-secondary/40 border border-border">
                        <Badge variant="outline" className={tone(r.level)}>{r.level.toUpperCase()}</Badge>
                        <div>
                          <div className="text-sm font-medium text-foreground">{r.label}</div>
                          <div className="text-xs text-muted-foreground">{r.note}</div>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </TabsContent>

              {/* FINANCIALS */}
              <TabsContent value="financials" className="mt-6 space-y-6">
                <div className="grid sm:grid-cols-2 gap-4">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <LineChart className="h-4 w-4 text-primary" /> Financial Projections
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      {property.investmentStructure.map((s) => (
                        <div key={s.label} className="flex items-center justify-between border-b border-border pb-1.5 last:border-0">
                          <span className="text-muted-foreground">{s.label}</span>
                          <span className="font-medium text-foreground">{s.value}</span>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <Globe2 className="h-4 w-4 text-primary" /> Market Analysis &amp; Valuation
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      {property.marketAnalysis.map((m) => (
                        <div key={m.label} className="flex items-center justify-between border-b border-border pb-1.5 last:border-0">
                          <span className="text-muted-foreground">{m.label}</span>
                          <span className="font-medium text-foreground">{m.value}</span>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                </div>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Banknote className="h-4 w-4 text-primary" /> Cash Flow &amp; Return Expectations
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="grid sm:grid-cols-3 gap-3 text-sm">
                    <div className="p-3 rounded-lg bg-secondary/40 border border-border">
                      <div className="text-xs text-muted-foreground">Current Asset Value</div>
                      <div className="font-semibold text-foreground">{fmt(currentValue)}</div>
                    </div>
                    <div className="p-3 rounded-lg bg-secondary/40 border border-border">
                      <div className="text-xs text-muted-foreground">Next Phase Value</div>
                      <div className="font-semibold text-foreground">{fmt(nextValue)}</div>
                    </div>
                    <div className="p-3 rounded-lg bg-success/5 border border-success/30">
                      <div className="text-xs text-muted-foreground">Projected Delivery Value</div>
                      <div className="font-semibold text-success">{fmt(finalValue)}</div>
                    </div>
                    <div className="sm:col-span-3 grid sm:grid-cols-2 gap-3">
                      <div className="p-3 rounded-lg bg-secondary/30 border border-border">
                        <div className="text-xs text-muted-foreground mb-1">Rental / Income Projections</div>
                        <div className="text-foreground">{extra.rentalProjection ?? "Income-producing once delivered; net distributions paid quarterly to SPV holders."}</div>
                      </div>
                      <div className="p-3 rounded-lg bg-secondary/30 border border-border">
                        <div className="text-xs text-muted-foreground mb-1">Development &amp; Operating Costs</div>
                        <div className="text-foreground">Land, construction, SPV admin, escrow, valuation, and platform fees disclosed in the offering memorandum.</div>
                      </div>
                      <div className="p-3 rounded-lg bg-secondary/30 border border-border">
                        <div className="text-xs text-muted-foreground mb-1">Appreciation Expectation</div>
                        <div className="text-success font-medium">+{property.capitalAppreciation ?? 0}% over project horizon</div>
                      </div>
                      <div className="p-3 rounded-lg bg-secondary/30 border border-border">
                        <div className="text-xs text-muted-foreground mb-1">Exit Projection</div>
                        <div className="text-foreground">Settlement at delivery, secondary-market sale, or liquidity-provider buy-back.</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <ArrowRight className="h-4 w-4 text-primary" /> Exit Mechanisms
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="grid sm:grid-cols-2 gap-3">
                    {property.exitMechanisms.map((e) => (
                      <div key={e.name} className="p-3 rounded-lg bg-secondary/40 border border-border">
                        <div className="flex items-center justify-between">
                          <div className="text-sm font-semibold text-foreground">{e.name}</div>
                          <Badge variant="outline" className="text-[10px]">{e.eta}</Badge>
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">{e.description}</div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </TabsContent>

              {/* SPV STRUCTURE */}
              <TabsContent value="structure" className="mt-6 space-y-6">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Layers className="h-4 w-4 text-primary" /> SPV &amp; Legal Structure
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4 text-sm">
                    <div className="grid sm:grid-cols-2 gap-3">
                      {[
                        { label: "SPV Name", value: `${property.title} Holdings SPV Ltd` },
                        { label: "Jurisdiction", value: "DIFC, UAE" },
                        { label: "Registration No.", value: `SPV-2025-${property.slug.slice(0, 6).toUpperCase()}` },
                        { label: "Asset Holding", value: "100% title held by SPV" },
                        { label: "Investor Allocation", value: "Pro-rata digital share certificates" },
                        { label: "Custodian / Trustee", value: "Independent licensed trustee" },
                      ].map((r) => (
                        <div key={r.label} className="p-3 bg-secondary/40 rounded-lg border border-border">
                          <div className="text-xs text-muted-foreground">{r.label}</div>
                          <div className="font-semibold text-foreground">{r.value}</div>
                        </div>
                      ))}
                    </div>
                    <div className="grid sm:grid-cols-2 gap-3">
                      {property.ownershipStructure.map((o) => (
                        <div key={o.label} className="p-3 bg-secondary/40 rounded-lg border border-border">
                          <div className="text-xs text-muted-foreground">{o.label}</div>
                          <div className="font-semibold text-foreground">{o.value}</div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Shield className="h-4 w-4 text-primary" /> Compliance &amp; Legal Framework
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="grid sm:grid-cols-2 gap-3 text-sm">
                    {[
                      "SPV holds direct, ring-fenced ownership of the asset",
                      "Investors hold digital shares in the SPV — not in Capimax",
                      "Independent escrow agent secures all capital flows",
                      "Quarterly engineering &amp; financial audits",
                      "KYC / AML verified investor base",
                      "Regulated trustee oversees custody &amp; distributions",
                    ].map((c) => (
                      <div key={c} className="flex items-start gap-2 p-2.5 rounded-lg bg-secondary/40 border border-border">
                        <CheckCircle className="h-4 w-4 text-success shrink-0 mt-0.5" />
                        <span className="text-foreground" dangerouslySetInnerHTML={{ __html: c }} />
                      </div>
                    ))}
                  </CardContent>
                </Card>

                <div className="text-center">
                  <Button asChild variant="outline">
                    <Link to="/spv-model">View Full SPV Model</Link>
                  </Button>
                </div>
              </TabsContent>

              {/* DOCUMENTS */}
              <TabsContent value="documents" className="mt-6 space-y-6">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <ScrollText className="h-4 w-4 text-primary" /> Property &amp; Investment Documents
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {[
                      ...property.documents,
                      { name: "Title Deed", type: "PDF", size: "1.2 MB" },
                      { name: "Independent Valuation Report", type: "PDF", size: "2.4 MB" },
                      { name: "Engineering / Structural Report", type: "PDF", size: "3.1 MB" },
                      { name: "SPV Articles of Incorporation", type: "PDF", size: "880 KB" },
                      { name: "Subscription Agreement", type: "PDF", size: "640 KB" },
                      { name: "Escrow Agreement", type: "PDF", size: "520 KB" },
                      { name: "Financial Projections", type: "XLSX", size: "920 KB" },
                      { name: "Compliance &amp; KYC Framework", type: "PDF", size: "410 KB" },
                      { name: "Developer Track Record Report", type: "PDF", size: "1.8 MB" },
                    ]
                      .filter((d, i, a) => a.findIndex((x) => x.name === d.name) === i)
                      .map((d) => (
                        <div key={d.name} className="flex items-center justify-between p-2.5 rounded-lg bg-secondary/40 border border-border">
                          <div className="flex items-center gap-2 text-sm">
                            <FileText className="h-4 w-4 text-muted-foreground" />
                            <span className="text-foreground" dangerouslySetInnerHTML={{ __html: d.name }} />
                            <span className="text-xs text-muted-foreground">({d.type} · {d.size})</span>
                          </div>
                          <Button variant="ghost" size="sm" disabled title="Document downloads are not available yet"><Download className="h-4 w-4" /></Button>
                        </div>
                      ))}
                    <div className="text-xs text-muted-foreground p-3 rounded-lg bg-secondary/30 border border-border">
                      All documents are verified by Capimax's legal &amp; compliance team. Investor-only files unlock after KYC &amp; subscription.
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              {/* TIMELINE */}
              <TabsContent value="timeline" className="mt-6 space-y-6">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <HardHat className="h-4 w-4 text-primary" /> Construction Phase &amp; Pricing Progression
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid sm:grid-cols-3 gap-3">
                      <div className="p-3 rounded-lg bg-secondary/40 border border-border">
                        <div className="text-xs text-muted-foreground">Current Phase</div>
                        <div className="font-semibold text-foreground">{currentMilestone.label}</div>
                        <div className="text-xs text-muted-foreground mt-1">{currentMilestone.progress}% complete</div>
                      </div>
                      <div className="p-3 rounded-lg bg-secondary/40 border border-border">
                        <div className="text-xs text-muted-foreground">Current Pricing</div>
                        <div className="font-semibold text-foreground">{fmt(currentValue)}</div>
                        <div className="text-xs text-muted-foreground mt-1">NAV index {currentMilestone.valueIndex}</div>
                      </div>
                      <div className="p-3 rounded-lg bg-success/5 border border-success/30">
                        <div className="text-xs text-muted-foreground">Next Phase Pricing</div>
                        <div className="font-semibold text-success">{fmt(nextValue)}</div>
                        <div className="text-xs text-muted-foreground mt-1">Estimated at {nextMilestone?.label ?? "—"}</div>
                      </div>
                    </div>
                    <div className="text-xs text-muted-foreground p-3 rounded-lg bg-primary/5 border border-primary/20">
                      As construction milestones are completed, independent valuations may revise the asset value upward. Estimated delivery valuation: <strong className="text-foreground">{fmt(finalValue)}</strong>.
                    </div>
                    <div className="space-y-3 pt-2">
                      {property.timeline.map((m, i) => (
                        <div key={i} className="flex items-start gap-3">
                          <div className={`mt-1 h-3 w-3 rounded-full ${
                            m.status === "done" ? "bg-success" : m.status === "active" ? "bg-primary animate-pulse" : "bg-muted"
                          }`} />
                          <div className="flex-1">
                            <div className="flex items-center justify-between">
                              <span className="text-sm font-medium text-foreground">{m.label}</span>
                              <span className="text-xs text-muted-foreground">{m.date} · NAV {m.valueIndex}</span>
                            </div>
                            <Progress value={m.progress} className="h-1.5 mt-1" />
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              {/* DEVELOPER */}
              <TabsContent value="developer" className="mt-6 space-y-6">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Briefcase className="h-4 w-4 text-primary" /> Developer / Owner Profile
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-center gap-4">
                      <Avatar className="h-16 w-16 bg-primary/10">
                        <AvatarFallback className="text-lg font-semibold text-primary bg-primary/10">
                          {property.developer.name.split(" ").map((w) => w[0]).slice(0, 2).join("")}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <div className="text-lg font-semibold text-foreground">{property.developer.name}</div>
                        <div className="text-sm text-muted-foreground">Verified developer · Capimax-approved</div>
                        <div className="flex items-center gap-2 mt-1">
                          <Badge variant="outline" className="bg-success/10 text-success border-success/30">
                            <CheckCircle className="h-3 w-3 mr-1" /> Verified
                          </Badge>
                          <Badge variant="outline">Rating {property.developer.rating} / 5</Badge>
                        </div>
                      </div>
                    </div>

                    <div className="grid sm:grid-cols-3 gap-3 text-sm">
                      <div className="p-3 rounded-lg bg-secondary/40 border border-border">
                        <div className="text-xs text-muted-foreground">Projects Completed</div>
                        <div className="font-semibold text-foreground">{property.developer.projectsCompleted}+</div>
                      </div>
                      <div className="p-3 rounded-lg bg-secondary/40 border border-border">
                        <div className="text-xs text-muted-foreground">Years of Experience</div>
                        <div className="font-semibold text-foreground">12+ years</div>
                      </div>
                      <div className="p-3 rounded-lg bg-secondary/40 border border-border">
                        <div className="text-xs text-muted-foreground">On-time Delivery</div>
                        <div className="font-semibold text-success">96%</div>
                      </div>
                    </div>

                    <div>
                      <div className="text-xs uppercase text-muted-foreground mb-2">Company Overview</div>
                      <p className="text-sm text-muted-foreground">
                        {property.developer.name} is a vetted developer on the Capimax PropShare network with a strong track record of delivering institutional-grade real estate across global markets. All projects undergo Capimax legal, financial, and engineering due diligence before being listed.
                      </p>
                    </div>

                    <div>
                      <div className="text-xs uppercase text-muted-foreground mb-2">Previous Projects</div>
                      <div className="grid sm:grid-cols-2 gap-2 text-sm">
                        {["Marina Heights Tower", "Downtown Residences Phase II", "Creek Harbour Villas", "Business Bay Office Park"].map((p) => (
                          <div key={p} className="flex items-center gap-2 p-2.5 rounded-lg bg-secondary/40 border border-border">
                            <CheckCircle className="h-4 w-4 text-success shrink-0" />
                            <span className="text-foreground">{p}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <div className="text-xs uppercase text-muted-foreground mb-2">Verification &amp; Contact</div>
                      <div className="grid sm:grid-cols-2 gap-2 text-sm">
                        {[
                          "Trade license verified",
                          "Audited financial statements on file",
                          "Insurance &amp; bonding confirmed",
                          "Direct contact via investor relations desk",
                        ].map((v) => (
                          <div key={v} className="flex items-start gap-2 p-2.5 rounded-lg bg-secondary/40 border border-border">
                            <Shield className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                            <span className="text-foreground" dangerouslySetInnerHTML={{ __html: v }} />
                          </div>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>

            {/* Investment / Payment / Ownership flow */}
            <Card className="border-primary/40">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Wallet className="h-4 w-4 text-primary" /> Invest &amp; Payment
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid sm:grid-cols-3 gap-3">
                  <div className="p-3 rounded-lg bg-secondary/40 border border-border text-sm">
                    <div className="text-xs text-muted-foreground">Min. Investment</div>
                    <div className="font-semibold text-foreground">{fmt(property.minInvestment)}</div>
                  </div>
                  <div className="p-3 rounded-lg bg-secondary/40 border border-border text-sm">
                    <div className="text-xs text-muted-foreground">Funding Progress</div>
                    <div className="font-semibold text-foreground">{property.fundingProgress}%</div>
                    <Progress value={property.fundingProgress} className="h-1.5 mt-1.5" />
                  </div>
                  <div className="p-3 rounded-lg bg-secondary/40 border border-border text-sm">
                    <div className="text-xs text-muted-foreground">Investors</div>
                    <div className="font-semibold text-foreground">{property.investorsCount}</div>
                  </div>
                </div>

                <div className="grid sm:grid-cols-2 gap-3 text-xs text-muted-foreground">
                  <div className="p-3 rounded-lg bg-secondary/30 border border-border">
                    <div className="font-medium text-foreground mb-1">Payment Methods</div>
                    Wallet balance · Bank transfer · Card · Crypto stablecoins
                  </div>
                  <div className="p-3 rounded-lg bg-secondary/30 border border-border">
                    <div className="font-medium text-foreground mb-1">Payment Plans</div>
                    Lump sum · Installment · Reservation deposit · Option premium
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row gap-3">
                  <Button className="flex-1" size="lg" asChild>
                    <Link to={`/property/${detail.slug ?? detail.id}`}>
                      <Banknote className="h-4 w-4 mr-2" /> Invest Now
                    </Link>
                  </Button>
                </div>
                <div className="text-[11px] text-muted-foreground text-center">
                  Educational demo · subscription is signed via SPV agreement; ownership is confirmed on-chain after settlement.
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Sidebar */}
          <aside className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Briefcase className="h-4 w-4 text-primary" /> Developer / Owner Profile
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="font-semibold text-foreground">{property.developer.name}</div>
                <div className="text-muted-foreground">Rating: {property.developer.rating} / 5</div>
                <div className="text-muted-foreground">
                  Projects completed: {property.developer.projectsCompleted}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Layers className="h-4 w-4 text-primary" /> SPV &amp; Ownership Structure
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {property.ownershipStructure.map((o) => (
                  <div key={o.label} className="flex items-center justify-between">
                    <span className="text-muted-foreground">{o.label}</span>
                    <span className="font-medium text-foreground">{o.value}</span>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Shield className="h-4 w-4 text-primary" /> Compliance &amp; Custody
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground space-y-2">
                <div className="flex items-center gap-2"><CheckCircle className="h-3.5 w-3.5 text-success" /> Independent trustee custody</div>
                <div className="flex items-center gap-2"><CheckCircle className="h-3.5 w-3.5 text-success" /> Escrow-secured payments</div>
                <div className="flex items-center gap-2"><CheckCircle className="h-3.5 w-3.5 text-success" /> KYC / AML verified investors</div>
                <div className="flex items-center gap-2"><CheckCircle className="h-3.5 w-3.5 text-success" /> Quarterly engineering audits</div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Users className="h-4 w-4 text-primary" /> Other Models
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {Object.entries(MODEL_MAP)
                  .filter(([k]) => k !== model)
                  .map(([k, c]) => (
                    <Link
                      key={k}
                      to={`/advanced-property/${k}`}
                      className="flex items-center justify-between p-2 rounded-lg bg-secondary/40 border border-border hover:border-primary/40"
                    >
                      <span className="text-foreground">{c.title}</span>
                      <ArrowRight className="h-4 w-4 text-muted-foreground" />
                    </Link>
                  ))}
              </CardContent>
            </Card>

            <Card className="border-primary/30">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Scale className="h-4 w-4 text-primary" /> Regulatory Note
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">
                This page is an educational illustration. All figures, valuations and
                scenarios are indicative. Final terms are governed by the SPV
                subscription documents.
              </CardContent>
            </Card>
          </aside>
        </div>
      </main>
    </div>
  );
};

export default AdvancedPropertyPage;
