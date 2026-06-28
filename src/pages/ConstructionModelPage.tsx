import { useMemo } from "react";
import { Link, useParams, Navigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ArrowRight,
  CheckCircle2,
  Layers,
  TrendingUp,
  Wallet,
  Repeat,
  AlertTriangle,
  Building2,
  Handshake,
  Timer,
  Target,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import PropertyGrid from "@/components/marketplace/PropertyGrid";
import type { OwnershipModel } from "@/pages/Marketplace";
import { propertyApi } from "@/lib/api";
import { toMarketplaceProperty } from "@/lib/properties";

type ModelKey = "installment" | "future" | "option" | "partnership";

interface ModelConfig {
  key: ModelKey;
  ownershipModel: OwnershipModel;
  title: string;
  tagline: string;
  description: string;
  badge: string;
  accent: string; // tailwind text color class
  badgeTone: string;
  metrics: { label: string; value: string }[];
  howItWorks: { title: string; desc: string }[];
  benefits: string[];
  risks: { label: string; level: "low" | "medium" | "high"; note: string }[];
  exits: { name: string; desc: string; eta: string }[];
  faq: { q: string; a: string }[];
}

const models: Record<ModelKey, ModelConfig> = {
  installment: {
    key: "installment",
    ownershipModel: "installment",
    title: "Installment Ownership Model",
    tagline:
      "Acquire fractional ownership progressively while paying in milestone-aligned installments.",
    description:
      "The Installment model lets investors lock in today's price and pay gradually as the property is built. Ownership vests proportionally with each installment, fully transferring at handover.",
    badge: "Under Construction • Installment",
    accent: "text-amber-500",
    badgeTone: "bg-amber-500/10 text-amber-600 border-amber-500/30",
    metrics: [
      { label: "Down Payment", value: "10–20%" },
      { label: "Plan Length", value: "12–36 months" },
      { label: "Vesting", value: "Progressive" },
      { label: "Final Settlement", value: "On handover" },
    ],
    howItWorks: [
      { title: "Reserve", desc: "Pay the down payment to lock in your unit allocation at today's price." },
      { title: "Installment Plan", desc: "Equal monthly payments tracked on-chain and held in regulated escrow." },
      { title: "Milestone Audits", desc: "Independent inspectors verify construction stages before each developer draw." },
      { title: "Handover & Title", desc: "Final installment unlocks full ownership and rental income begins." },
    ],
    benefits: [
      "Predictable monthly cashflow commitment",
      "Capture appreciation between subscription and delivery",
      "Capital protected by escrow + milestone gating",
      "Position can be transferred at any time on the secondary market",
    ],
    risks: [
      { label: "Construction delay", level: "medium", note: "Mitigated by escrow, milestone audits, and developer guarantees." },
      { label: "Payment default", level: "medium", note: "Position can be re-listed; partial recovery from paid installments." },
      { label: "Market cycle", level: "medium", note: "Delivery-period valuations subject to local market trends." },
    ],
    exits: [
      { name: "Transfer Installment Position", desc: "Sell your remaining position to another investor on the secondary market.", eta: "3–10 days" },
      { name: "Liquidity Provider", desc: "Instant exit at a discount; LP assumes the remaining installment schedule.", eta: "Same day" },
      { name: "Hold to Delivery", desc: "Complete payments and receive title + monthly rental yield.", eta: "On handover" },
    ],
    faq: [
      { q: "What if I miss an installment?", a: "A grace period applies. Persistent default triggers an automated re-listing of your position; recovered proceeds (less fees) are returned to you." },
      { q: "Do I earn during construction?", a: "No rental yield until handover, but NAV-based capital appreciation is reflected at each milestone." },
    ],
  },
  future: {
    key: "future",
    ownershipModel: "future",
    title: "Future Ownership Model",
    tagline:
      "A forward purchase agreement that locks today's price for delivery at a defined future date.",
    description:
      "The Future model is a structured forward contract: the investor commits to acquire the unit at a locked-in price, settled at a future delivery date. All appreciation between subscription and settlement accrues to the holder.",
    badge: "Forward Contract • Settlement on Delivery",
    accent: "text-blue-500",
    badgeTone: "bg-blue-500/10 text-blue-500 border-blue-500/30",
    metrics: [
      { label: "Reservation", value: "10% of forward value" },
      { label: "Settlement", value: "T + 18–36 months" },
      { label: "Locked-in Price", value: "Today's NAV" },
      { label: "Projected IRR", value: "12–18%" },
    ],
    howItWorks: [
      { title: "Lock the Price", desc: "Sign a forward contract at today's NAV with a small reservation deposit." },
      { title: "Construction Window", desc: "NAV is re-marked at each milestone (foundation, structure, fit-out, handover)." },
      { title: "Settle or Assign", desc: "At maturity, settle by funding the balance — or assign the contract on the secondary market." },
      { title: "Capture Appreciation", desc: "Delta between locked price and delivery value is the investor's return." },
    ],
    benefits: [
      "Lock today's price; benefit from full delivery-period appreciation",
      "Lower upfront capital than full installment plans",
      "Transparent NAV step-ups at each construction milestone",
      "Tradable position before settlement",
    ],
    risks: [
      { label: "Settlement obligation", level: "high", note: "Investor must fund the balance or assign the contract before delivery." },
      { label: "Market volatility", level: "medium", note: "Future appreciation is not guaranteed; downside if market falls." },
      { label: "Construction risk", level: "medium", note: "Milestone audits, escrow, and developer guarantees mitigate exposure." },
    ],
    exits: [
      { name: "Assign Forward Contract", desc: "Transfer the contract to another investor on the secondary market.", eta: "5–14 days" },
      { name: "Liquidity Provider", desc: "Discounted instant assignment to a market-making LP.", eta: "Same day" },
      { name: "Settle & Hold", desc: "Take title at delivery and earn rental yield going forward.", eta: "On settlement" },
    ],
    faq: [
      { q: "What happens at settlement?", a: "You either pay the locked-in balance and take title, or assign the contract to another investor for the difference between locked and market price." },
      { q: "Can the developer change the price?", a: "No. The forward price is contractually locked from day one and held by an independent custodian." },
    ],
  },
  option: {
    key: "option",
    ownershipModel: "option",
    title: "Option Ownership Model",
    tagline:
      "Pay a small option premium today for the right — but not the obligation — to acquire the unit later.",
    description:
      "The Option model is a call-style real-estate option: the investor pays an option premium that locks a strike price for a defined activation window. If markets perform, activate the option; if not, the loss is capped at the premium.",
    badge: "Option Position • Capped Downside",
    accent: "text-violet-500",
    badgeTone: "bg-violet-500/10 text-violet-500 border-violet-500/30",
    metrics: [
      { label: "Option Premium", value: "3–10% of strike" },
      { label: "Activation Window", value: "6–18 months" },
      { label: "Max Loss", value: "Premium paid" },
      { label: "Projected Upside", value: "20–35%" },
    ],
    howItWorks: [
      { title: "Pay Premium", desc: "Pay a small option premium that locks the strike price for the chosen window." },
      { title: "Hold & Observe", desc: "Watch NAV evolve as construction milestones complete and the market moves." },
      { title: "Decide", desc: "Activate (acquire at strike), assign on secondary market, or let expire." },
      { title: "Activate or Walk Away", desc: "If activated: take ownership at the locked price. If not: maximum loss is the premium." },
    ],
    benefits: [
      "Asymmetric payoff: capped downside, leveraged upside",
      "Low capital outlay relative to property value",
      "Flexibility to convert, transfer, or walk away",
      "Hedge against future price increases in target areas",
    ],
    risks: [
      { label: "Time decay", level: "high", note: "Option value decays as the activation deadline approaches." },
      { label: "Activation funding", level: "medium", note: "Investor must fund the strike on activation or assign the position." },
      { label: "Market volatility", level: "medium", note: "Underlying NAV swings drive option value." },
    ],
    exits: [
      { name: "Activate", desc: "Convert the option into full unit ownership at the strike price.", eta: "On activation" },
      { name: "Sell Option", desc: "Transfer the option position on the secondary market at intrinsic + time value.", eta: "1–7 days" },
      { name: "Let Expire", desc: "Walk away at the deadline — loss is capped at the premium paid.", eta: "Deadline" },
    ],
    faq: [
      { q: "Is the premium refundable?", a: "No. The premium is the cost of the right to buy. It is the maximum possible loss on the position." },
      { q: "Can I sell the option before expiry?", a: "Yes — the option can be assigned to another investor on the secondary market at any time before expiry." },
    ],
  },
  partnership: {
    key: "partnership",
    ownershipModel: "shared-development",
    title: "Partnership with Developer Model",
    tagline:
      "Co-invest with the developer in both land and construction; share profits pro-rata after a preferred return.",
    description:
      "In the Partnership (Shared Development) model, investors and the developer co-fund land acquisition and construction expenses. Profits are split pro-rata after a preferred return, with the developer aligned through skin-in-the-game and milestone-based draws.",
    badge: "Joint Venture • Profit Sharing",
    accent: "text-fuchsia-500",
    badgeTone: "bg-fuchsia-500/10 text-fuchsia-500 border-fuchsia-500/30",
    metrics: [
      { label: "Capital Stack", value: "60% land / 40% build" },
      { label: "Preferred Return", value: "8% pref" },
      { label: "Profit Split", value: "70 / 30 LP / GP" },
      { label: "Hold Period", value: "24–36 months" },
    ],
    howItWorks: [
      { title: "Joint SPV", desc: "Investors join an SPV alongside the developer as Limited Partners (LPs)." },
      { title: "Capital Calls", desc: "Capital is drawn in tranches against land closing and construction milestones." },
      { title: "Construction & Sales", desc: "Developer (GP) executes; LPs receive quarterly reporting and voting rights on major decisions." },
      { title: "Distribution", desc: "Net profits distribute pro-rata after the preferred return is paid." },
    ],
    benefits: [
      "True economic alignment with the developer (GP skin-in-the-game)",
      "Preferred return paid before profit sharing",
      "Higher upside than pure income properties",
      "Governance rights on major project decisions",
    ],
    risks: [
      { label: "Development risk", level: "high", note: "Cost overruns, permitting, sales velocity all impact returns." },
      { label: "Liquidity", level: "high", note: "Partnership positions are less liquid than tokenized units." },
      { label: "Sponsor risk", level: "medium", note: "Mitigated by GP track record, audits, and fiduciary controls." },
    ],
    exits: [
      { name: "Secondary Market", desc: "Transfer LP units to another qualified investor on the platform.", eta: "10–30 days" },
      { name: "Project Wind-up", desc: "Receive pro-rata share of profits when the project is sold or refinanced.", eta: "End of hold period" },
      { name: "Refinance Distribution", desc: "Capital can be partially returned via construction-end refinancing.", eta: "On refinance event" },
    ],
    faq: [
      { q: "Am I personally liable as a partner?", a: "No. Investors hold Limited Partner units inside the SPV; liability is limited to capital committed." },
      { q: "When do I get paid?", a: "After the preferred return is met, profits are distributed at refinance, sale, or end of project — per the LP agreement." },
    ],
  },
};

const ConstructionModelPage = () => {
  const { model } = useParams<{ model: ModelKey }>();
  const config = model ? models[model] : undefined;

  const { data, isLoading } = useQuery({
    queryKey: ["properties", "model", config?.ownershipModel],
    queryFn: () => propertyApi.list({ model: config!.ownershipModel, limit: 50 }),
    enabled: !!config,
  });
  const listings = useMemo(
    () => (data?.items ?? []).map(toMarketplaceProperty),
    [data],
  );

  if (!config) return <Navigate to="/marketplace" replace />;

  const otherModels = (Object.keys(models) as ModelKey[]).filter((k) => k !== config.key);

  return (
    <div className="min-h-screen bg-background">
      {/* Hero */}
      <section className="bg-gradient-hero text-primary-foreground py-16">
        <div className="container mx-auto px-4">
          <div className="flex items-center gap-2 mb-4">
            <Link to="/marketplace" className="text-primary-foreground/70 hover:text-primary-foreground text-sm">
              ← Back to Marketplace
            </Link>
          </div>
          <Badge className="mb-4 bg-background/20 backdrop-blur-sm border-primary-foreground/20">
            {config.badge}
          </Badge>
          <h1 className="text-3xl md:text-5xl font-bold mb-4 max-w-3xl">{config.title}</h1>
          <p className="text-lg text-primary-foreground/85 max-w-3xl">{config.tagline}</p>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-10 max-w-4xl">
            {config.metrics.map((m) => (
              <div key={m.label} className="bg-background/10 backdrop-blur-sm rounded-xl p-4 border border-primary-foreground/10">
                <div className="text-xs uppercase tracking-wide text-primary-foreground/70">{m.label}</div>
                <div className="text-lg md:text-xl font-semibold mt-1">{m.value}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="container mx-auto px-4 py-12 space-y-12">
        {/* Description */}
        <section>
          <Card className="border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Layers className={`h-5 w-5 ${config.accent}`} />
                Model Overview
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground leading-relaxed">{config.description}</p>
            </CardContent>
          </Card>
        </section>

        {/* How it works */}
        <section>
          <h2 className="text-2xl font-bold text-foreground mb-6 flex items-center gap-2">
            <Target className={`h-6 w-6 ${config.accent}`} />
            How the Model Works
          </h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
            {config.howItWorks.map((step, i) => (
              <Card key={step.title} className="border-border">
                <CardContent className="pt-6">
                  <div className={`h-9 w-9 rounded-full bg-secondary flex items-center justify-center font-bold ${config.accent} mb-3`}>
                    {i + 1}
                  </div>
                  <div className="font-semibold text-foreground mb-1">{step.title}</div>
                  <div className="text-sm text-muted-foreground">{step.desc}</div>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        {/* Benefits + Risks */}
        <section className="grid md:grid-cols-2 gap-6">
          <Card className="border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-success" />
                Benefits
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3">
                {config.benefits.map((b) => (
                  <li key={b} className="flex items-start gap-2 text-sm">
                    <CheckCircle2 className="h-4 w-4 text-success mt-0.5 flex-shrink-0" />
                    <span className="text-foreground">{b}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card className="border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-warning" />
                Risk Indicators
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3">
                {config.risks.map((r) => (
                  <li key={r.label} className="flex items-start justify-between gap-3 text-sm border-b border-border last:border-0 pb-3 last:pb-0">
                    <div>
                      <div className="font-semibold text-foreground">{r.label}</div>
                      <div className="text-muted-foreground text-xs mt-0.5">{r.note}</div>
                    </div>
                    <Badge
                      className={
                        r.level === "high"
                          ? "bg-destructive/10 text-destructive border-destructive/30"
                          : r.level === "medium"
                          ? "bg-warning/10 text-warning border-warning/30"
                          : "bg-success/10 text-success border-success/30"
                      }
                      variant="outline"
                    >
                      {r.level}
                    </Badge>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </section>

        {/* How to Exit */}
        <section>
          <h2 className="text-2xl font-bold text-foreground mb-2 flex items-center gap-2">
            <Repeat className={`h-6 w-6 ${config.accent}`} />
            How to Exit
          </h2>
          <p className="text-muted-foreground mb-6 max-w-3xl">
            Every position on the platform comes with multiple exit paths so you stay liquid throughout the lifecycle.
          </p>
          <div className="grid md:grid-cols-3 gap-4">
            {config.exits.map((e) => (
              <Card key={e.name} className="border-border">
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Wallet className={`h-4 w-4 ${config.accent}`} />
                    {e.name}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground mb-4">{e.desc}</p>
                  <div className="flex items-center gap-2 text-xs text-foreground">
                    <Timer className="h-3.5 w-3.5" />
                    <span className="font-semibold">ETA:</span>
                    <span className="text-muted-foreground">{e.eta}</span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        {/* FAQ */}
        <section>
          <h2 className="text-2xl font-bold text-foreground mb-6">Frequently Asked Questions</h2>
          <div className="grid md:grid-cols-2 gap-4">
            {config.faq.map((f) => (
              <Card key={f.q} className="border-border">
                <CardContent className="pt-6">
                  <div className="font-semibold text-foreground mb-2">{f.q}</div>
                  <div className="text-sm text-muted-foreground">{f.a}</div>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        {/* Listings */}
        <section>
          <div className="flex items-end justify-between flex-wrap gap-3 mb-6">
            <div>
              <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
                <Building2 className={`h-6 w-6 ${config.accent}`} />
                Available {config.title.replace(" Ownership Model", "").replace(" Model", "")} Properties
              </h2>
              <p className="text-muted-foreground text-sm mt-1">
                {listings.length} opportunit{listings.length === 1 ? "y" : "ies"} matching this model
              </p>
            </div>
            <Link to="/marketplace">
              <Button variant="outline" size="sm">
                Browse all properties
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : (
            <PropertyGrid properties={listings} viewMode="grid" />
          )}
        </section>

        {/* Other models */}
        <section>
          <h2 className="text-2xl font-bold text-foreground mb-6 flex items-center gap-2">
            <Handshake className="h-6 w-6 text-primary" />
            Explore Other Construction Models
          </h2>
          <div className="grid sm:grid-cols-3 gap-4">
            {otherModels.map((k) => {
              const m = models[k];
              return (
                <Link key={k} to={`/properties/${k}`}>
                  <Card className="border-border hover:border-primary transition-colors h-full">
                    <CardContent className="pt-6">
                      <Badge variant="outline" className={m.badgeTone}>
                        {m.title.replace(" Ownership Model", "").replace(" Model", "")}
                      </Badge>
                      <p className="text-sm text-muted-foreground mt-3">{m.tagline}</p>
                      <div className="text-xs text-primary mt-4 flex items-center gap-1">
                        Learn more <ArrowRight className="h-3 w-3" />
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
};

export default ConstructionModelPage;
