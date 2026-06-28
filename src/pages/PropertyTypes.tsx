import {
  Building2,
  Home,
  Calendar,
  Layers,
  Clock,
  Key,
  Handshake,
  TrendingUp,
  Shield,
  CheckCircle2,
  ArrowRight,
  HardHat,
  Sparkles,
  PieChart,
  Wallet,
  GraduationCap,
  Scale,
  FileText,
  Banknote,
  LineChart,
  CalendarClock,
  Hammer,
  Coins,
  Target,
  Lock,
  ArrowLeftRight,
  Users,
  Briefcase,
  BookOpen,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

type PropertyModel = {
  id: string;
  title: string;
  tagline: string;
  icon: typeof Building2;
  accent: string;
  description: string;
  features: string[];
  display: { label: string; value: string }[];
  riskLevel: number; // 1-5
  returnLevel: number; // 1-5
  horizon: string;
  badge?: string;
};

const READY: PropertyModel = {
  id: "ready",
  title: "Ready Rented Property",
  tagline: "Operational · income-generating",
  icon: Home,
  accent: "from-primary to-accent",
  description:
    "Fully completed and operational properties already rented and generating income. Investors receive scheduled rental distributions — built for passive income and stable yield.",
  features: [
    "Rental returns from day one",
    "Stable, predictable cash flow",
    "Lower construction risk",
    "Operational, income-producing assets",
    "Passive income focused",
  ],
  display: [
    { label: "Rental yield", value: "8% – 11% / yr" },
    { label: "Occupancy", value: "92% avg." },
    { label: "Expected income", value: "Monthly distributions" },
    { label: "Valuation", value: "Independent appraisal" },
    { label: "Exit options", value: "Secondary + Instant" },
  ],
  riskLevel: 1,
  returnLevel: 3,
  horizon: "Ongoing",
  badge: "Most popular",
};

const UNDER_CONSTRUCTION: PropertyModel[] = [
  {
    id: "installment",
    title: "Installment-Based Property",
    tagline: "Pay over time · acquire gradually",
    icon: Calendar,
    accent: "from-primary to-accent",
    description:
      "Acquire ownership through structured installment plans. Investors purchase allocations gradually with flexible down payments and scheduled payments.",
    features: [
      "Flexible payment plans",
      "Multiple installment durations",
      "Down payment options",
      "Scheduled ownership acquisition",
    ],
    display: [
      { label: "Down payment", value: "From 10%" },
      { label: "Installment duration", value: "12 – 60 months" },
      { label: "Payment schedule", value: "Monthly / Quarterly" },
      { label: "Ownership activation", value: "Per milestone" },
    ],
    riskLevel: 2,
    returnLevel: 3,
    horizon: "1 – 5 years",
  },
  {
    id: "phase",
    title: "Phase-Based Property",
    tagline: "Progressive pricing · construction-linked",
    icon: Layers,
    accent: "from-accent to-primary",
    description:
      "Ownership pricing changes across construction phases. Each phase reflects updated developer pricing, supported by independent valuation reports and construction progress.",
    features: [
      "Early phase lower pricing",
      "Progressive appreciation",
      "Construction milestone-based pricing",
      "Phase-by-phase ownership opportunities",
    ],
    display: [
      { label: "Current phase", value: "Phase 2 of 4" },
      { label: "Share price", value: "$118 / unit" },
      { label: "Next phase pricing", value: "$132 / unit" },
      { label: "Construction progress", value: "46%" },
      { label: "Estimated appreciation", value: "+22% to delivery" },
    ],
    riskLevel: 3,
    returnLevel: 4,
    horizon: "12 – 36 months",
  },
  {
    id: "future",
    title: "Future-Based Property",
    tagline: "Future value · appreciation-focused",
    icon: Clock,
    accent: "from-primary via-primary to-accent",
    description:
      "Reserve or acquire future ownership rights based on the project's expected delivery and future valuation. Designed for appreciation-focused investors targeting market growth.",
    features: [
      "Future pricing exposure",
      "Appreciation-focused",
      "Future ownership activation",
      "Market growth potential",
    ],
    display: [
      { label: "Activation timeline", value: "18 – 36 months" },
      { label: "Expected valuation growth", value: "+28% projected" },
      { label: "Delivery expectation", value: "Q4 2027" },
      { label: "ROI projection", value: "12% – 18% IRR" },
    ],
    riskLevel: 4,
    returnLevel: 4,
    horizon: "2 – 4 years",
  },
  {
    id: "option",
    title: "Option-Based Property",
    tagline: "Right to purchase · flexible decision",
    icon: Key,
    accent: "from-accent via-primary to-accent",
    description:
      "Acquire the right — but not the obligation — to purchase ownership later under predefined conditions and timelines. Maximum flexibility on the ownership decision.",
    features: [
      "Flexible ownership decision",
      "Reserved purchase rights",
      "Predefined pricing conditions",
      "Future ownership flexibility",
    ],
    display: [
      { label: "Option duration", value: "6 – 24 months" },
      { label: "Option pricing", value: "From 3% of unit value" },
      { label: "Activation conditions", value: "Pre-agreed" },
      { label: "Conversion terms", value: "Locked-in price" },
    ],
    riskLevel: 3,
    returnLevel: 5,
    horizon: "6 – 24 months",
  },
  {
    id: "shared",
    title: "Shared Development Property",
    tagline: "Partnership · profit-sharing",
    icon: Handshake,
    accent: "from-primary to-accent",
    description:
      "Participate in property development in partnership with the owner or developer. Investors share in project growth, revenue and value creation across the development lifecycle.",
    features: [
      "Shared ownership structure",
      "Partnership-based returns",
      "Development participation",
      "Profit-sharing models",
    ],
    display: [
      { label: "Participation structure", value: "Equity partnership" },
      { label: "Ownership allocation", value: "Pro-rata to capital" },
      { label: "Revenue distribution", value: "Quarterly" },
      { label: "Development timeline", value: "24 – 48 months" },
    ],
    riskLevel: 4,
    returnLevel: 5,
    horizon: "2 – 4 years",
  },
];

const ALL_MODELS = [READY, ...UNDER_CONSTRUCTION];

const compareRows = [
  { label: "Income type", values: ["Rental", "Capital + future rental", "Capital appreciation", "Future appreciation", "Optional appreciation", "Profit share"] },
  { label: "Risk", values: ["Low", "Medium", "Medium-High", "High", "Medium", "High"] },
  { label: "Return potential", values: ["Stable 8-11%", "10-14%", "15-22%", "12-18% IRR", "Variable", "15-25%"] },
  { label: "Horizon", values: ["Ongoing", "1-5y", "1-3y", "2-4y", "6-24m", "2-4y"] },
  { label: "Best for", values: ["Passive income", "Disciplined buyers", "Growth investors", "Long-term capital", "Flexible investors", "Active partners"] },
];

function LevelBar({ level, max = 5, color }: { level: number; max?: number; color: string }) {
  return (
    <div className="flex gap-1">
      {Array.from({ length: max }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "h-1.5 flex-1 rounded-full",
            i < level ? color : "bg-muted"
          )}
        />
      ))}
    </div>
  );
}

function ModelCard({ m }: { m: PropertyModel }) {
  return (
    <Card className="relative overflow-hidden border-primary/10 h-full flex flex-col">
      <div className={cn("absolute inset-x-0 top-0 h-1 bg-gradient-to-r", m.accent)} />
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className={cn("w-12 h-12 rounded-xl bg-gradient-to-br flex items-center justify-center text-primary-foreground flex-shrink-0", m.accent)}>
              <m.icon className="w-6 h-6" />
            </div>
            <div>
              <CardTitle className="text-lg">{m.title}</CardTitle>
              <CardDescription>{m.tagline}</CardDescription>
            </div>
          </div>
          {m.badge && (
            <Badge variant="outline" className="border-primary/30 text-primary">
              <Sparkles className="w-3 h-3 mr-1" /> {m.badge}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col space-y-4">
        <p className="text-sm text-muted-foreground leading-relaxed">{m.description}</p>

        <div className="grid grid-cols-2 gap-2">
          {m.display.map((d, i) => (
            <div key={i} className="p-2.5 rounded-lg bg-muted/40">
              <div className="text-[11px] text-muted-foreground">{d.label}</div>
              <div className="text-sm font-semibold">{d.value}</div>
            </div>
          ))}
        </div>

        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Key features
          </div>
          {m.features.map((f, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
              <span>{f}</span>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3 pt-2 border-t">
          <div>
            <div className="text-[11px] text-muted-foreground mb-1 flex items-center gap-1">
              <Shield className="w-3 h-3" /> Risk level
            </div>
            <LevelBar level={m.riskLevel} color="bg-amber-500" />
          </div>
          <div>
            <div className="text-[11px] text-muted-foreground mb-1 flex items-center gap-1">
              <TrendingUp className="w-3 h-3" /> Return potential
            </div>
            <LevelBar level={m.returnLevel} color="bg-primary" />
          </div>
        </div>

        <div className="flex items-center justify-between pt-2 mt-auto">
          <div className="text-xs text-muted-foreground flex items-center gap-1">
            <Clock className="w-3 h-3" /> Horizon: <span className="font-semibold text-foreground">{m.horizon}</span>
          </div>
          <Button asChild size="sm" variant="ghost" className="gap-1">
            <Link to="/marketplace">
              Explore <ArrowRight className="w-3 h-3" />
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function PropertyTypes() {
  return (
    <div className="min-h-screen bg-background">
      {/* Hero */}
      <section className="relative border-b border-border bg-gradient-to-br from-primary/5 via-background to-accent/5">
        <div className="container mx-auto px-4 py-10 md:py-14">
          <Badge variant="outline" className="border-primary/30 text-primary mb-3">
            <Building2 className="w-3 h-3 mr-1" /> Real Estate Models
          </Badge>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
            Property Types
          </h1>
          <p className="text-muted-foreground max-w-3xl">
            Explore every ownership and opportunity model available on the platform — from
            ready-rented income properties to phase-based, future, option and shared development
            models for under-construction projects.
          </p>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-8">
            {[
              { label: "Property models", value: "6", icon: Layers },
              { label: "Ready-to-earn assets", value: "120+", icon: Home },
              { label: "Active developments", value: "38", icon: HardHat },
              { label: "Avg. yield", value: "11.2%", icon: PieChart },
            ].map((s, i) => (
              <Card key={i} className="border-primary/10">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-1">
                    <s.icon className="w-4 h-4 text-primary" />
                  </div>
                  <div className="text-xl font-bold">{s.value}</div>
                  <div className="text-xs text-muted-foreground">{s.label}</div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <div className="container mx-auto px-4 py-10 space-y-10">
        <Tabs defaultValue="all" className="space-y-6">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <h2 className="text-2xl font-bold">Browse by category</h2>
            <TabsList className="bg-muted/50 flex-wrap h-auto">
              <TabsTrigger value="all">All Models</TabsTrigger>
              <TabsTrigger value="ready" className="gap-2">
                <Home className="w-4 h-4" /> Ready Rented
              </TabsTrigger>
              <TabsTrigger value="construction" className="gap-2">
                <HardHat className="w-4 h-4" /> Under Construction
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="all" className="space-y-6">
            <ModelCard m={READY} />
            <div>
              <div className="flex items-center gap-2 mb-3">
                <HardHat className="w-5 h-5 text-primary" />
                <h3 className="text-xl font-bold">Under Construction Models</h3>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                {UNDER_CONSTRUCTION.map((m) => (
                  <ModelCard key={m.id} m={m} />
                ))}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="ready">
            <ModelCard m={READY} />
          </TabsContent>

          <TabsContent value="construction">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {UNDER_CONSTRUCTION.map((m) => (
                <ModelCard key={m.id} m={m} />
              ))}
            </div>
          </TabsContent>
        </Tabs>

        {/* Deep dive: detailed educational explanations */}
        <section className="space-y-6">
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-primary" />
            <h2 className="text-2xl font-bold">Model deep dive</h2>
            <Badge variant="outline" className="border-primary/30 text-primary ml-1">
              Educational
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground max-w-3xl -mt-2">
            A professional, in-depth breakdown of how each ownership and opportunity model
            works on the platform — structure, mechanics, returns, supporting reports and exit options.
          </p>

          {/* INSTALLMENT MODEL */}
          <Card className="border-primary/15 overflow-hidden">
            <div className="h-1 bg-gradient-to-r from-primary to-accent" />
            <CardHeader>
              <div className="flex items-start gap-4 flex-wrap">
                <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center text-primary-foreground">
                  <Calendar className="w-7 h-7" />
                </div>
                <div className="flex-1 min-w-[240px]">
                  <Badge variant="outline" className="border-primary/30 text-primary mb-2">
                    Installment-Based Property
                  </Badge>
                  <CardTitle className="text-xl md:text-2xl">
                    Acquire ownership gradually through structured installment plans
                  </CardTitle>
                  <CardDescription className="mt-2 text-sm md:text-base leading-relaxed">
                    Investors purchase property ownership allocations through installment payments
                    over predefined periods — without paying the full ownership amount upfront.
                    Ownership is acquired progressively through a down payment followed by scheduled
                    monthly or quarterly installments.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {[
                  { icon: Wallet, label: "Down payment", value: "From 10% – 30%", sub: "Flexible entry options" },
                  { icon: CalendarClock, label: "Installment duration", value: "12 – 60 months", sub: "Choose your horizon" },
                  { icon: Banknote, label: "Payment schedule", value: "Monthly / Quarterly", sub: "Auto-debit supported" },
                  { icon: CheckCircle2, label: "Ownership activation", value: "Per milestone", sub: "Progressive title rights" },
                  { icon: PieChart, label: "Remaining balance", value: "Tracked live", sub: "Visible in dashboard" },
                  { icon: TrendingUp, label: "Returns after activation", value: "Pro-rata yield", sub: "Aligned with ownership %" },
                ].map((d, i) => (
                  <div key={i} className="p-3 rounded-xl border border-border bg-card">
                    <div className="flex items-center gap-2 mb-1">
                      <d.icon className="w-4 h-4 text-primary" />
                      <span className="text-xs text-muted-foreground">{d.label}</span>
                    </div>
                    <div className="text-sm font-bold">{d.value}</div>
                    <div className="text-[11px] text-muted-foreground mt-0.5">{d.sub}</div>
                  </div>
                ))}
              </div>

              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                  How it works
                </div>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
                  {[
                    { step: "01", title: "Down payment", desc: "Pay an initial percentage to secure your allocation." },
                    { step: "02", title: "Installments", desc: "Pay monthly or quarterly under your chosen plan." },
                    { step: "03", title: "Progressive ownership", desc: "Ownership rights activate as installments are paid." },
                    { step: "04", title: "Returns & exit", desc: "Receive pro-rata returns and access exit options." },
                  ].map((s, i) => (
                    <div key={i} className="p-3 rounded-lg border border-border bg-muted/30">
                      <div className="text-[10px] text-primary font-bold tracking-widest">{s.step}</div>
                      <div className="text-sm font-semibold mt-0.5">{s.title}</div>
                      <div className="text-xs text-muted-foreground mt-1 leading-relaxed">{s.desc}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
                {[
                  "Flexible ownership access",
                  "Easier entry into real estate",
                  "Structured, predictable payment plans",
                ].map((b, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm p-2.5 rounded-lg bg-primary/5">
                    <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
                    <span>{b}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* OPTION MODEL — advanced explanation */}
          <Card className="border-primary/15 overflow-hidden">
            <div className="h-1 bg-gradient-to-r from-accent via-primary to-accent" />
            <CardHeader>
              <div className="flex items-start gap-4 flex-wrap">
                <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-accent via-primary to-accent flex items-center justify-center text-primary-foreground">
                  <Key className="w-7 h-7" />
                </div>
                <div className="flex-1 min-w-[240px]">
                  <Badge variant="outline" className="border-primary/30 text-primary mb-2">
                    Option-Based Property · Advanced
                  </Badge>
                  <CardTitle className="text-xl md:text-2xl">
                    Reserve the right to acquire ownership — pay a small option amount today, decide later
                  </CardTitle>
                  <CardDescription className="mt-2 text-sm md:text-base leading-relaxed">
                    The Option Model lets the investor reserve the right — but not the obligation —
                    to acquire ownership in a property by paying a predefined option amount upfront,
                    instead of paying the full ownership value immediately. The option grants a
                    future ownership right, a reserved acquisition opportunity and access to
                    activation under pre-agreed conditions.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                {[
                  { icon: Coins, label: "Option price", value: "From 3% – 10%", sub: "Of full ownership value" },
                  { icon: CalendarClock, label: "Option duration", value: "6 – 24 months", sub: "Per opportunity" },
                  { icon: Target, label: "Activation deadline", value: "Pre-defined", sub: "Set at issuance" },
                  { icon: Lock, label: "Future ownership value", value: "Locked-in", sub: "At today's pricing" },
                  { icon: Banknote, label: "Remaining balance", value: "Paid on activation", sub: "After option exercise" },
                  { icon: CheckCircle2, label: "Activation conditions", value: "Pre-agreed", sub: "Transparent terms" },
                ].map((d, i) => (
                  <div key={i} className="p-3 rounded-xl border border-border bg-card">
                    <div className="flex items-center gap-2 mb-1">
                      <d.icon className="w-4 h-4 text-primary" />
                      <span className="text-[11px] text-muted-foreground">{d.label}</span>
                    </div>
                    <div className="text-sm font-bold">{d.value}</div>
                    <div className="text-[11px] text-muted-foreground mt-0.5">{d.sub}</div>
                  </div>
                ))}
              </div>

              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">Activation flow</div>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
                  {[
                    { step: "01", title: "Pay option amount", desc: "Pay the option premium to reserve the future ownership right." },
                    { step: "02", title: "Holding period", desc: "Hold the position while the project develops and value evolves." },
                    { step: "03", title: "Decide before deadline", desc: "Activate, exit on the secondary market, or let the option expire." },
                    { step: "04", title: "Activation & ownership", desc: "Pay the remaining balance — ownership becomes fully activated." },
                  ].map((s, i) => (
                    <div key={i} className="p-3 rounded-lg border border-border bg-muted/30">
                      <div className="text-[10px] text-primary font-bold tracking-widest">{s.step}</div>
                      <div className="text-sm font-semibold mt-0.5">{s.title}</div>
                      <div className="text-xs text-muted-foreground mt-1 leading-relaxed">{s.desc}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl border border-primary/20 bg-primary/5">
                  <div className="text-sm font-semibold mb-2 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-primary" /> If the investor activates
                  </div>
                  <ul className="space-y-1.5 text-sm text-muted-foreground">
                    <li className="flex gap-2"><span className="text-primary">•</span> Investor pays the remaining ownership balance.</li>
                    <li className="flex gap-2"><span className="text-primary">•</span> Ownership becomes fully activated and registered.</li>
                    <li className="flex gap-2"><span className="text-primary">•</span> Eligible for rental income, appreciation gains and exit options.</li>
                    <li className="flex gap-2"><span className="text-primary">•</span> Becomes an official ownership holder with full rights.</li>
                  </ul>
                </div>
                <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-500/5">
                  <div className="text-sm font-semibold mb-2 flex items-center gap-2">
                    <Shield className="w-4 h-4 text-amber-600" /> If the option is not activated
                  </div>
                  <ul className="space-y-1.5 text-sm text-muted-foreground">
                    <li className="flex gap-2"><span className="text-amber-600">•</span> The option expires automatically at the deadline.</li>
                    <li className="flex gap-2"><span className="text-amber-600">•</span> The ownership reservation becomes invalid.</li>
                    <li className="flex gap-2"><span className="text-amber-600">•</span> The investor may lose the option amount paid.</li>
                    <li className="flex gap-2"><span className="text-amber-600">•</span> No further obligations or remaining balance due.</li>
                  </ul>
                </div>
              </div>

              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Exit before activation</div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                  {[
                    { icon: ArrowLeftRight, t: "Sell on secondary market", d: "Resell the option position to other investors at current market price." },
                    { icon: Users, t: "Transfer the option", d: "Reassign the reserved acquisition right to another qualified investor." },
                    { icon: Coins, t: "Liquidity provider exit", d: "Instant exit through liquidity provider quotes where available." },
                  ].map((x, i) => (
                    <div key={i} className="p-3 rounded-lg border border-border bg-card">
                      <div className="flex items-center gap-2 mb-1">
                        <x.icon className="w-4 h-4 text-primary" />
                        <span className="text-sm font-semibold">{x.t}</span>
                      </div>
                      <div className="text-xs text-muted-foreground leading-relaxed">{x.d}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-4 rounded-xl border border-border bg-gradient-to-br from-primary/5 via-background to-accent/5">
                <div className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-primary" /> Appreciation example — option value growth
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div className="p-2.5 rounded-lg bg-muted/40">
                    <div className="text-[11px] text-muted-foreground">Full ownership value</div>
                    <div className="font-bold">$100,000</div>
                  </div>
                  <div className="p-2.5 rounded-lg bg-muted/40">
                    <div className="text-[11px] text-muted-foreground">Option amount (5%)</div>
                    <div className="font-bold">$5,000</div>
                  </div>
                  <div className="p-2.5 rounded-lg bg-primary/10">
                    <div className="text-[11px] text-muted-foreground">Value after 12 mo. (+15%)</div>
                    <div className="font-bold text-primary">$115,000</div>
                  </div>
                  <div className="p-2.5 rounded-lg bg-primary/10">
                    <div className="text-[11px] text-muted-foreground">Resale option value</div>
                    <div className="font-bold text-primary">~$20,000</div>
                  </div>
                </div>
                <div className="text-xs text-muted-foreground mt-3 leading-relaxed">
                  Illustrative only. The investor reserved $100k of ownership for $5k. If property
                  value rises to $115k, the locked-in price advantage may translate into a higher
                  resale value of the option position on the secondary market — before any activation.
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="p-3 rounded-lg border border-border">
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Why investors choose the Option Model</div>
                  <ul className="space-y-1 text-sm">
                    <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-primary" /> Lower entry capital</li>
                    <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-primary" /> Flexible ownership exposure</li>
                    <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-primary" /> Appreciation opportunity before activation</li>
                    <li className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-primary" /> Ability to exit before full ownership activation</li>
                  </ul>
                </div>
                <div className="p-3 rounded-lg border border-amber-500/30 bg-amber-500/5">
                  <div className="text-xs font-semibold uppercase tracking-wider text-amber-700 mb-2">Risk indicators</div>
                  <ul className="space-y-1 text-sm text-muted-foreground">
                    <li className="flex gap-2"><span className="text-amber-600">•</span> Option amount may be lost if not activated.</li>
                    <li className="flex gap-2"><span className="text-amber-600">•</span> Activation timelines vary per opportunity.</li>
                    <li className="flex gap-2"><span className="text-amber-600">•</span> Resale liquidity depends on market demand.</li>
                    <li className="flex gap-2"><span className="text-amber-600">•</span> Property value may decrease before activation.</li>
                  </ul>
                </div>
              </div>

              <div className="text-xs text-muted-foreground p-3 rounded-lg border border-border bg-primary/5">
                <Sparkles className="w-3 h-3 inline mr-1 text-primary" />
                Institutional-grade structure — similar to options used in structured financial
                products, applied transparently to real estate ownership.
              </div>
            </CardContent>
          </Card>

          {/* FUTURE MODEL — advanced explanation */}
          <Card className="border-primary/15 overflow-hidden">
            <div className="h-1 bg-gradient-to-r from-primary via-primary to-accent" />
            <CardHeader>
              <div className="flex items-start gap-4 flex-wrap">
                <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-primary via-primary to-accent flex items-center justify-center text-primary-foreground">
                  <Clock className="w-7 h-7" />
                </div>
                <div className="flex-1 min-w-[240px]">
                  <Badge variant="outline" className="border-primary/30 text-primary mb-2">
                    Future-Based Property · Advanced
                  </Badge>
                  <CardTitle className="text-xl md:text-2xl">
                    Structured exposure to the future value of a project through a future agreement
                  </CardTitle>
                  <CardDescription className="mt-2 text-sm md:text-base leading-relaxed">
                    The Future Model allows investors to gain exposure to the expected future value
                    of a property or project through a structured future-based ownership commitment
                    linked to future property value, future development completion and future market
                    pricing. Designed for investors seeking early-stage exposure, higher growth
                    potential and access to projects before completion.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                {[
                  { icon: Banknote, label: "Future agreement value", value: "Project-linked", sub: "Set at issuance" },
                  { icon: CalendarClock, label: "Settlement date", value: "18 – 36 months", sub: "Future delivery" },
                  { icon: Target, label: "Future pricing", value: "Pre-agreed", sub: "Locked at entry" },
                  { icon: Hammer, label: "Construction timeline", value: "Tracked live", sub: "Milestone reports" },
                  { icon: LineChart, label: "Expected appreciation", value: "+22% – 35%", sub: "Market projection" },
                  { icon: TrendingUp, label: "Projected ROI", value: "12% – 18% IRR", sub: "Indicative" },
                ].map((d, i) => (
                  <div key={i} className="p-3 rounded-xl border border-border bg-card">
                    <div className="flex items-center gap-2 mb-1">
                      <d.icon className="w-4 h-4 text-primary" />
                      <span className="text-[11px] text-muted-foreground">{d.label}</span>
                    </div>
                    <div className="text-sm font-bold">{d.value}</div>
                    <div className="text-[11px] text-muted-foreground mt-0.5">{d.sub}</div>
                  </div>
                ))}
              </div>

              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">Construction & value milestones</div>
                <div className="relative p-4 rounded-xl border border-border bg-muted/20">
                  <div className="grid grid-cols-4 gap-2 text-center">
                    {[
                      { label: "Entry", pct: "0%", val: "100" },
                      { label: "Foundation", pct: "30%", val: "108" },
                      { label: "Structure", pct: "65%", val: "118" },
                      { label: "Delivery", pct: "100%", val: "130+" },
                    ].map((m, i) => (
                      <div key={i}>
                        <div className="text-[10px] text-muted-foreground">{m.label}</div>
                        <div className="my-2 h-2 rounded-full bg-muted overflow-hidden">
                          <div className="h-full bg-gradient-to-r from-primary to-accent" style={{ width: m.pct }} />
                        </div>
                        <div className="text-xs font-semibold">{m.pct}</div>
                        <div className="text-[11px] text-primary font-bold mt-0.5">${m.val}</div>
                      </div>
                    ))}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-3 text-center">
                    Indicative future-value progression based on construction completion and independent valuation reports.
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Future value driven by</div>
                  <div className="space-y-2">
                    {[
                      { icon: Hammer, t: "Construction progress" },
                      { icon: CheckCircle2, t: "Development completion" },
                      { icon: FileText, t: "Independent valuation reports" },
                      { icon: TrendingUp, t: "Market demand & appreciation" },
                    ].map((x, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm p-2 rounded-lg border border-border">
                        <x.icon className="w-4 h-4 text-primary" />
                        <span>{x.t}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Supported by</div>
                  <div className="space-y-2">
                    {[
                      { icon: Hammer, t: "Construction progress reports" },
                      { icon: FileText, t: "Engineering & valuation reports" },
                      { icon: PieChart, t: "Independent market analysis" },
                      { icon: Briefcase, t: "Developer milestone updates" },
                    ].map((x, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm p-2 rounded-lg border border-border">
                        <x.icon className="w-4 h-4 text-primary" />
                        <span>{x.t}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Exit possibilities before settlement</div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                  {[
                    { icon: ArrowLeftRight, t: "Secondary market exit", d: "Trade your future allocation peer-to-peer at the prevailing price." },
                    { icon: Coins, t: "Liquidity provider exit", d: "Instant exit through provider quotes — subject to availability." },
                    { icon: Users, t: "Transfer of allocation", d: "Reassign your future ownership rights to another investor." },
                  ].map((x, i) => (
                    <div key={i} className="p-3 rounded-lg border border-border bg-card">
                      <div className="flex items-center gap-2 mb-1">
                        <x.icon className="w-4 h-4 text-primary" />
                        <span className="text-sm font-semibold">{x.t}</span>
                      </div>
                      <div className="text-xs text-muted-foreground leading-relaxed">{x.d}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="p-4 rounded-xl border border-primary/20 bg-primary/5">
                  <div className="text-sm font-semibold mb-2 flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-primary" /> Upside scenario
                  </div>
                  <ul className="space-y-1.5 text-sm text-muted-foreground">
                    <li className="flex gap-2"><span className="text-primary">•</span> Construction completes on time, market appreciates.</li>
                    <li className="flex gap-2"><span className="text-primary">•</span> Future position value rises with delivery milestones.</li>
                    <li className="flex gap-2"><span className="text-primary">•</span> Investor exits at higher value or settles into ownership.</li>
                    <li className="flex gap-2"><span className="text-primary">•</span> Targeted IRR range of 12% – 18%.</li>
                  </ul>
                </div>
                <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-500/5">
                  <div className="text-sm font-semibold mb-2 flex items-center gap-2">
                    <Shield className="w-4 h-4 text-amber-600" /> Downside scenario & risks
                  </div>
                  <ul className="space-y-1.5 text-sm text-muted-foreground">
                    <li className="flex gap-2"><span className="text-amber-600">•</span> Negative market movement may reduce future value.</li>
                    <li className="flex gap-2"><span className="text-amber-600">•</span> Investor may lose part or all of the invested amount.</li>
                    <li className="flex gap-2"><span className="text-amber-600">•</span> Settlement obligations may apply at the future date.</li>
                    <li className="flex gap-2"><span className="text-amber-600">•</span> Margin-related exposure may apply per opportunity structure.</li>
                  </ul>
                </div>
              </div>

              <div className="text-xs text-muted-foreground p-3 rounded-lg border border-border bg-primary/5">
                <Shield className="w-3 h-3 inline mr-1 text-primary" />
                Higher risk and higher potential return — designed for investors seeking
                construction- and appreciation-driven growth over a multi-year horizon.
              </div>
            </CardContent>
          </Card>

          {/* SHARED DEVELOPMENT */}
          <Card className="border-primary/15 overflow-hidden">
            <div className="h-1 bg-gradient-to-r from-primary to-accent" />
            <CardHeader>
              <div className="flex items-start gap-4 flex-wrap">
                <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center text-primary-foreground">
                  <Handshake className="w-7 h-7" />
                </div>
                <div className="flex-1 min-w-[240px]">
                  <Badge variant="outline" className="border-primary/30 text-primary mb-2">
                    Shared Development Property
                  </Badge>
                  <CardTitle className="text-xl md:text-2xl">
                    Partner with the developer in the development process itself
                  </CardTitle>
                  <CardDescription className="mt-2 text-sm md:text-base leading-relaxed">
                    Investors participate alongside the developer across the entire development
                    lifecycle — sharing in land ownership, construction participation, project
                    economics and the resulting development profit margins, value increase and
                    appreciation.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                    Investor contributes to
                  </div>
                  <div className="space-y-2">
                    {[
                      { icon: Coins, t: "Development costs" },
                      { icon: Hammer, t: "Construction expenses" },
                      { icon: Banknote, t: "Project financing structure" },
                      { icon: Users, t: "Land ownership participation" },
                    ].map((x, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm p-2 rounded-lg border border-border">
                        <x.icon className="w-4 h-4 text-primary" />
                        <span>{x.t}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                    Investor benefits from
                  </div>
                  <div className="space-y-2">
                    {[
                      { icon: TrendingUp, t: "Property appreciation" },
                      { icon: PieChart, t: "Development profit margins" },
                      { icon: LineChart, t: "Value increase during development" },
                      { icon: Briefcase, t: "Shared development returns" },
                    ].map((x, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm p-2 rounded-lg border border-border">
                        <x.icon className="w-4 h-4 text-primary" />
                        <span>{x.t}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: "Participation %", value: "Pro-rata to capital" },
                  { label: "Cost allocation", value: "Capital-weighted" },
                  { label: "Development timeline", value: "24 – 48 months" },
                  { label: "Expected ROI", value: "15% – 25%" },
                ].map((d, i) => (
                  <div key={i} className="p-3 rounded-xl bg-muted/40">
                    <div className="text-[11px] text-muted-foreground">{d.label}</div>
                    <div className="text-sm font-bold mt-0.5">{d.value}</div>
                  </div>
                ))}
              </div>

              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                  Construction stages & profit distribution
                </div>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
                  {[
                    { step: "01", title: "Land & financing", desc: "Capital is pooled for land acquisition and financing." },
                    { step: "02", title: "Construction", desc: "Construction stages tracked with milestone reports." },
                    { step: "03", title: "Completion", desc: "Project delivery and asset valuation uplift." },
                    { step: "04", title: "Profit distribution", desc: "Returns distributed pro-rata after exit or sale." },
                  ].map((s, i) => (
                    <div key={i} className="p-3 rounded-lg border border-border bg-muted/30">
                      <div className="text-[10px] text-primary font-bold tracking-widest">{s.step}</div>
                      <div className="text-sm font-semibold mt-0.5">{s.title}</div>
                      <div className="text-xs text-muted-foreground mt-1 leading-relaxed">{s.desc}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="text-xs text-muted-foreground p-3 rounded-lg border border-border bg-primary/5">
                <Handshake className="w-3 h-3 inline mr-1 text-primary" />
                Partnership-based ownership — institutional real estate development exposure
                with developer-style participation and higher growth potential.
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Phase visual indicator */}
        <Card className="border-primary/10">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Layers className="w-5 h-5 text-primary" />
              <CardTitle>How phase-based pricing evolves</CardTitle>
            </div>
            <CardDescription>
              Pricing updates per construction phase — each backed by independent valuation reports.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              {[
                { phase: "Phase 1 · Foundations", price: "$100", progress: 100, status: "Completed" },
                { phase: "Phase 2 · Structure", price: "$118", progress: 46, status: "In progress" },
                { phase: "Phase 3 · Finishes", price: "$132", progress: 0, status: "Upcoming" },
                { phase: "Phase 4 · Delivery", price: "$148", progress: 0, status: "Final" },
              ].map((p, i) => (
                <div key={i} className="p-4 rounded-xl border border-border bg-card">
                  <div className="text-xs text-muted-foreground">{p.phase}</div>
                  <div className="text-lg font-bold mt-1">{p.price}</div>
                  <Progress value={p.progress} className="h-1.5 mt-2" />
                  <div className="text-[11px] text-muted-foreground mt-1">{p.status}</div>
                </div>
              ))}
            </div>
            <div className="text-xs text-muted-foreground p-3 rounded-lg border border-border">
              <Shield className="w-3 h-3 inline mr-1 text-primary" />
              Every phase price update is supported by independent valuation reports and verified
              construction milestones.
            </div>
          </CardContent>
        </Card>

        {/* Comparison */}
        <Card className="border-primary/10">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Scale className="w-5 h-5 text-primary" />
              <CardTitle>Compare all property models</CardTitle>
            </div>
            <CardDescription>Risk, return and horizon at a glance.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[760px]">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 pr-3 text-muted-foreground font-semibold">Attribute</th>
                    {ALL_MODELS.map((m) => (
                      <th key={m.id} className="text-left py-2 px-3 font-semibold">
                        <div className="flex items-center gap-1">
                          <m.icon className="w-3.5 h-3.5 text-primary" />
                          <span className="truncate">{m.title.replace(" Property", "")}</span>
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {compareRows.map((row, i) => (
                    <tr key={i} className={cn("border-b last:border-0", i % 2 === 0 && "bg-muted/20")}>
                      <td className="py-2 pr-3 text-muted-foreground">{row.label}</td>
                      {row.values.map((v, j) => (
                        <td key={j} className="py-2 px-3">{v}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Educational */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <GraduationCap className="w-5 h-5 text-primary" />
            <h2 className="text-2xl font-bold">Choosing the right model</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              {
                icon: Wallet,
                title: "Income vs. growth",
                desc: "Ready-rented properties produce stable rental income. Under-construction models target capital appreciation and longer-horizon returns.",
              },
              {
                icon: Shield,
                title: "Risk profile",
                desc: "Each model carries a different risk profile. Operational assets are lowest risk; future and shared development models offer higher upside with higher uncertainty.",
              },
              {
                icon: Clock,
                title: "Time horizon",
                desc: "Match your investment horizon to the model. Options and ready-rented are flexible, phase and future-based models reward patience until delivery.",
              },
            ].map((b, i) => (
              <Card key={i} className="border-primary/10">
                <CardHeader>
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                      <b.icon className="w-5 h-5 text-primary" />
                    </div>
                    <CardTitle className="text-base">{b.title}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground leading-relaxed">
                  {b.desc}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        {/* CTA */}
        <Card className="border-primary/20 bg-gradient-to-br from-primary/5 via-background to-accent/5">
          <CardContent className="p-6 md:p-8 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <h3 className="text-xl font-bold mb-1">Find a property that fits your strategy</h3>
              <p className="text-sm text-muted-foreground">
                Browse the marketplace and filter by ownership model, yield, location and horizon.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button asChild variant="outline" className="gap-2">
                <Link to="/how-it-works">
                  <GraduationCap className="w-4 h-4" /> How It Works
                </Link>
              </Button>
              <Button asChild className="gap-2">
                <Link to="/marketplace">
                  <Building2 className="w-4 h-4" /> Browse Marketplace
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
