import {
  ArrowLeftRight,
  Zap,
  Droplets,
  Store,
  Clock,
  TrendingUp,
  Shield,
  CheckCircle2,
  ArrowRight,
  Users,
  Activity,
  Scale,
  Sparkles,
  Wallet,
  Building2,
  GraduationCap,
  ChevronRight,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

const compareRows = [
  { label: "Exit speed", a: "Days to weeks", b: "Instant / minutes" },
  { label: "Pricing model", a: "Market-based (buyer demand)", b: "Liquidity-provider quoted" },
  { label: "Counterparty", a: "Another platform investor", b: "Institutional liquidity provider" },
  { label: "Typical fees", a: "1.0% – 1.5%", b: "1.8% – 2.5%" },
  { label: "Match required", a: "Yes — buyer must accept", b: "No — auto-matched" },
  { label: "Settlement", a: "On buyer payment", b: "Real-time settlement" },
  { label: "Best for", a: "Maximum value, no urgency", b: "Speed and certainty" },
];

const secondaryFlow = [
  { step: "List", text: "Investor lists ownership on the secondary market with target price." },
  { step: "Match", text: "Qualified platform investors browse and place purchase requests." },
  { step: "Transfer", text: "Ownership units are transferred via the SPV upon payment." },
  { step: "Settle", text: "Funds are credited to the seller's wallet — net of platform fees." },
];

const lpFlow = [
  { step: "Request", text: "Investor submits an instant exit request for full or partial ownership." },
  { step: "Match", text: "System auto-matches the request with available liquidity providers." },
  { step: "Acquire", text: "Liquidity provider acquires the ownership at a transparent quoted price." },
  { step: "Pay", text: "Investor receives funds in real time — settlement is immediate." },
];

export default function ExitMechanisms() {
  return (
    <div className="min-h-screen bg-background">
      {/* Hero */}
      <section className="relative border-b border-border bg-gradient-to-br from-primary/5 via-background to-accent/5">
        <div className="container mx-auto px-4 py-10 md:py-14">
          <Badge variant="outline" className="border-primary/30 text-primary mb-3">
            <ArrowLeftRight className="w-3 h-3 mr-1" /> Liquidity Infrastructure
          </Badge>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
            Exit Mechanisms
          </h1>
          <p className="text-muted-foreground max-w-3xl">
            Two transparent, asset-backed paths to exit your real estate ownership at any time —
            choose between maximum value on the secondary market, or instant liquidity through
            institutional providers.
          </p>

          {/* Quick stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-8">
            {[
              { label: "Avg. secondary exit", value: "4.6 days", icon: Clock },
              { label: "Instant exit speed", value: "< 5 min", icon: Zap },
              { label: "Active marketplace demand", value: "$3.4M", icon: Activity },
              { label: "Available liquidity", value: "$1.25M", icon: Droplets },
            ].map((s, i) => (
              <Card key={i} className="border-primary/10">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-1">
                    <s.icon className="w-4 h-4 text-primary" />
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                      Live
                    </span>
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
        {/* Two Exit Cards */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Secondary Market */}
          <Card className="relative overflow-hidden border-primary/10">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary to-accent" />
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center">
                    <Store className="w-6 h-6 text-primary" />
                  </div>
                  <div>
                    <CardTitle className="text-xl">Secondary Market Exit</CardTitle>
                    <CardDescription>Market-based pricing · investor-to-investor</CardDescription>
                  </div>
                </div>
                <Badge variant="outline" className="border-primary/30 text-primary">
                  Lower fees
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <p className="text-sm text-muted-foreground leading-relaxed">
                List your ownership allocation on the secondary market and let qualified platform
                investors purchase it at a price you set. Best when you want to maximize value and
                are flexible on timing.
              </p>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <Stat label="Estimated fees" value="1.0% – 1.5%" />
                <Stat label="Avg. timeframe" value="4 – 7 days" />
                <Stat label="Marketplace demand" value="High" valueClass="text-primary" />
                <Stat label="Pricing" value="Set by seller" />
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-muted-foreground">Active buyer demand</span>
                  <span className="font-medium">82%</span>
                </div>
                <Progress value={82} className="h-2" />
              </div>

              <div className="space-y-2">
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Highlights
                </div>
                {[
                  "Lower platform fees",
                  "Market-based, transparent pricing",
                  "Requires a buyer / investor match",
                  "Ownership transferred via SPV",
                ].map((t, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
                    <span>{t}</span>
                  </div>
                ))}
              </div>

              <Button asChild className="w-full gap-2">
                <Link to="/secondary-market">
                  Open Secondary Market <ArrowRight className="w-4 h-4" />
                </Link>
              </Button>
            </CardContent>
          </Card>

          {/* Liquidity Provider Exit */}
          <Card className="relative overflow-hidden border-primary/10">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-accent to-primary" />
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center">
                    <Zap className="w-6 h-6 text-primary" />
                  </div>
                  <div>
                    <CardTitle className="text-xl">Liquidity Provider Exit</CardTitle>
                    <CardDescription>Instant exits · provider-backed</CardDescription>
                  </div>
                </div>
                <Badge variant="outline" className="border-primary/30 text-primary">
                  <Sparkles className="w-3 h-3 mr-1" /> Instant
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <p className="text-sm text-muted-foreground leading-relaxed">
                Exit instantly through institutional liquidity providers. Your ownership is acquired
                at a transparent quoted price and you receive funds in real time — best when you
                need speed and certainty.
              </p>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <Stat label="Liquidity fees" value="1.8% – 2.5%" />
                <Stat label="Settlement" value="Real-time" valueClass="text-primary" />
                <Stat label="Liquidity available" value="$1.25M" />
                <Stat label="Pricing" value="Provider-quoted" />
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-muted-foreground">Liquidity availability</span>
                  <span className="font-medium">94%</span>
                </div>
                <Progress value={94} className="h-2" />
              </div>

              <div className="space-y-2">
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Highlights
                </div>
                {[
                  "Instant or fast liquidity access",
                  "Immediate exit execution",
                  "Backed by institutional providers",
                  "Faster settlement process",
                ].map((t, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
                    <span>{t}</span>
                  </div>
                ))}
              </div>

              <Button asChild className="w-full gap-2">
                <Link to="/liquidity-market">
                  Explore Liquidity Market <ArrowRight className="w-4 h-4" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Comparison */}
        <Card className="border-primary/10">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Scale className="w-5 h-5 text-primary" />
              <CardTitle>Side-by-side comparison</CardTitle>
            </div>
            <CardDescription>
              Pick the right exit path based on speed, value and certainty.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4 text-sm border-b pb-3 mb-3 font-semibold">
              <div className="text-muted-foreground">Attribute</div>
              <div className="flex items-center gap-2">
                <Store className="w-4 h-4 text-primary" /> Secondary Market
              </div>
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4 text-primary" /> Liquidity Provider
              </div>
            </div>
            <div className="space-y-2">
              {compareRows.map((row, i) => (
                <div
                  key={i}
                  className={cn(
                    "grid grid-cols-3 gap-4 text-sm py-2 rounded-md",
                    i % 2 === 0 && "bg-muted/30 px-3"
                  )}
                >
                  <div className="text-muted-foreground">{row.label}</div>
                  <div>{row.a}</div>
                  <div>{row.b}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* How it works flows */}
        <Tabs defaultValue="secondary" className="space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <h2 className="text-2xl font-bold">How each exit works</h2>
            <TabsList className="bg-muted/50">
              <TabsTrigger value="secondary" className="gap-2">
                <Store className="w-4 h-4" /> Secondary Market
              </TabsTrigger>
              <TabsTrigger value="lp" className="gap-2">
                <Zap className="w-4 h-4" /> Liquidity Provider
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="secondary">
            <FlowSteps steps={secondaryFlow} accent="from-primary to-accent" />
          </TabsContent>
          <TabsContent value="lp">
            <FlowSteps steps={lpFlow} accent="from-accent to-primary" />
          </TabsContent>
        </Tabs>

        {/* Educational / Trust */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <GraduationCap className="w-5 h-5 text-primary" />
            <h2 className="text-2xl font-bold">Understand the liquidity ecosystem</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              {
                icon: Droplets,
                title: "What is liquidity?",
                desc: "Liquidity is the ability to convert your ownership into cash. The platform combines secondary buyers and institutional providers so you always have a path to exit.",
              },
              {
                icon: ArrowLeftRight,
                title: "How ownership transfers",
                desc: "Every transfer is recorded through the property's SPV. Ownership rights, rental income and capital appreciation move to the new holder upon settlement.",
              },
              {
                icon: Store,
                title: "Secondary market operations",
                desc: "A peer marketplace where investors buy and sell ownership units. Pricing is transparent and discovery-driven by demand and supply.",
              },
              {
                icon: Zap,
                title: "Instant exits explained",
                desc: "Institutional providers stand ready to acquire your ownership immediately at a quoted price — turning real estate into a liquid asset.",
              },
              {
                icon: TrendingUp,
                title: "Market-based exits",
                desc: "Set your asking price and let market demand match you with a buyer. Ideal when you want to capture maximum value and don't need urgency.",
              },
              {
                icon: Shield,
                title: "Investor flexibility",
                desc: "You're never locked in. Combine partial secondary sales with instant liquidity to manage your exposure and cash needs over time.",
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
              <h3 className="text-xl font-bold mb-1">Ready to exit?</h3>
              <p className="text-sm text-muted-foreground">
                Choose the path that fits your goals — list on the marketplace or request an
                instant exit through liquidity providers.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button asChild variant="outline" className="gap-2">
                <Link to="/secondary-market">
                  <Store className="w-4 h-4" /> Secondary Market
                </Link>
              </Button>
              <Button asChild className="gap-2">
                <Link to="/liquidity-market">
                  <Zap className="w-4 h-4" /> Instant Exit
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Stat({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="p-3 rounded-lg bg-muted/40">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn("font-semibold", valueClass)}>{value}</div>
    </div>
  );
}

function FlowSteps({ steps, accent }: { steps: { step: string; text: string }[]; accent: string }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
      {steps.map((s, i) => (
        <div key={i} className="relative">
          <Card className="border-primary/10 h-full">
            <CardContent className="p-5 space-y-2">
              <div className={cn("inline-flex items-center justify-center w-9 h-9 rounded-lg bg-gradient-to-br text-primary-foreground font-bold", accent)}>
                {i + 1}
              </div>
              <div className="font-semibold">{s.step}</div>
              <p className="text-sm text-muted-foreground leading-relaxed">{s.text}</p>
            </CardContent>
          </Card>
          {i < steps.length - 1 && (
            <ChevronRight className="hidden md:block w-5 h-5 text-muted-foreground absolute -right-3 top-1/2 -translate-y-1/2" />
          )}
        </div>
      ))}
    </div>
  );
}
