import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  PiggyBank,
  TrendingUp,
  Building2,
  Wallet,
  BarChart3,
  FileText,
  Lock,
  CreditCard,
  Droplet,
  Droplets,
  ArrowRightLeft,
  Tag,
  Zap,
} from "lucide-react";
import { VirtualCardRequest } from "@/components/dashboard/VirtualCardRequest";
import { InvestorWallet } from "@/components/dashboard/InvestorWallet";
import { liquidityApi, returnsApi, walletApi } from "@/lib/api";

const num = (s: string | null | undefined) => Number(s ?? 0);

// ?tab= deep links (sidebar, return from a hosted checkout, the assistant's prepared deposit)
const LP_TABS = ["overview", "assets", "returns", "wallet", "cards", "provide"];

// The liquidity provider's cycle, end to end — every step links to where it happens.
const CYCLE = [
  {
    icon: Wallet,
    title: "1. Fund your wallet",
    text: "Deposit by card, crypto or bank transfer. Your wallet balance is what you fund exit requests with.",
    cta: "Open my wallet",
    to: "/liquidity-dashboard?tab=wallet",
  },
  {
    icon: Droplets,
    title: "2. Choose an exit request",
    text: "Investors who want to sell instantly post requests on the Liquidity Market: the property, the units and the price.",
    cta: "Open the Liquidity Market",
    to: "/liquidity-market",
  },
  {
    icon: Zap,
    title: "3. Buy the units",
    text: "Fund a request from your wallet at the price shown. The seller is paid at once and the units move to you.",
    cta: "See open requests",
    to: "/liquidity-market",
  },
  {
    icon: Building2,
    title: "4. Hold them",
    text: "The units show under Backed Assets; rental distributions on them are paid into your wallet.",
    cta: "My backed assets",
    to: "/liquidity-dashboard?tab=assets",
  },
  {
    icon: ArrowRightLeft,
    title: "5. Exit on the Secondary Market",
    text: "When you want out, list your units on the Secondary Market at your price; the proceeds go to your wallet when a buyer pays.",
    cta: "Sell units",
    to: "/secondary-market?tab=sell",
  },
];

const LiquidityDashboard = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState(() =>
    LP_TABS.includes(tabFromUrl || "") ? tabFromUrl! : "overview",
  );
  useEffect(() => {
    if (tabFromUrl && LP_TABS.includes(tabFromUrl) && tabFromUrl !== activeTab) {
      setActiveTab(tabFromUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tabFromUrl]);
  const handleTabChange = (value: string) => {
    setActiveTab(value);
    setSearchParams({ tab: value });
  };

  const { data: holdings } = useQuery({
    queryKey: ["liquidity", "holdings"],
    queryFn: () => liquidityApi.holdings(),
  });
  const { data: positions } = useQuery({
    queryKey: ["liquidity", "positions"],
    queryFn: () => liquidityApi.positions(),
  });
  const { data: returns } = useQuery({
    queryKey: ["liquidity", "returns"],
    queryFn: () => returnsApi.getMine(),
  });
  const { data: settings } = useQuery({
    queryKey: ["liquidity", "settings"],
    queryFn: () => liquidityApi.settings(),
  });
  const { data: wallet } = useQuery({ queryKey: ["wallet"], queryFn: walletApi.getMe });

  const holdingItems = useMemo(() => holdings?.items ?? [], [holdings]);
  const passiveEnabled = settings?.passive_enabled ?? false;

  const stats = useMemo(() => {
    const holdingsValue = holdingItems.reduce((s, h) => s + h.units * num(h.unit_price), 0);
    return [
      { title: "Wallet Balance (to fund requests)", value: `$${num(wallet?.balance).toLocaleString()}` },
      { title: "Holdings Value (Active)", value: `$${holdingsValue.toLocaleString()}` },
      { title: "Rental Distributions", value: `$${num(returns?.total_net).toLocaleString()}` },
      { title: "Backed Assets", value: String(holdingItems.length) },
    ];
  }, [holdingItems, returns, wallet]);

  return (
    <div className="min-h-screen bg-background">
      <section className="bg-gradient-to-br from-primary/10 via-background to-accent/5 py-8 border-b border-border">
        <div className="container mx-auto px-4">
          <Badge className="bg-primary text-primary-foreground mb-2">Liquidity Provider</Badge>
          <h1 className="text-3xl font-bold text-foreground">Liquidity Provider Dashboard</h1>
          <p className="text-muted-foreground mt-1">
            Track the ownership you've acquired by funding instant exits, and your realized cash flows.
          </p>
        </div>
      </section>

      <section className="py-8">
        <div className="container mx-auto px-4">
          <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-8">
            <TabsList className="w-full flex flex-wrap justify-start gap-2 h-auto p-2 bg-muted/50">
              <TabsTrigger value="overview" className="gap-2"><BarChart3 className="h-4 w-4" />Overview</TabsTrigger>
              <TabsTrigger value="assets" className="gap-2"><Building2 className="h-4 w-4" />Backed Assets</TabsTrigger>
              <TabsTrigger value="returns" className="gap-2"><TrendingUp className="h-4 w-4" />Realized Cash Flows</TabsTrigger>
              <TabsTrigger value="wallet" className="gap-2"><Wallet className="h-4 w-4" />Wallet</TabsTrigger>
              <TabsTrigger value="cards" className="gap-2"><CreditCard className="h-4 w-4" />Virtual Cards</TabsTrigger>
              <TabsTrigger value="provide" className="gap-2"><PiggyBank className="h-4 w-4" />Fixed-Yield Pool (planned)</TabsTrigger>
            </TabsList>

            {/* Overview */}
            <TabsContent value="overview" className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {stats.map((stat, index) => (
                  <Card key={index} className="bg-card border-border">
                    <CardContent className="p-6">
                      <p className="text-sm text-muted-foreground">{stat.title}</p>
                      <p className="text-2xl font-bold text-foreground mt-1">{stat.value}</p>
                    </CardContent>
                  </Card>
                ))}
              </div>
              <Card className="bg-card border-border" data-testid="lp-cycle">
                <CardHeader>
                  <CardTitle>How it works</CardTitle>
                  <CardDescription>
                    Your cycle as a liquidity provider, from funding your wallet to selling the units
                    you bought. Figures here are realized cash flows, never a projected or guaranteed
                    return.
                  </CardDescription>
                </CardHeader>
                <CardContent className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
                  {CYCLE.map((step) => (
                    <div key={step.title} className="rounded-xl border border-border p-4 flex flex-col gap-2">
                      <step.icon className="h-5 w-5 text-primary" />
                      <p className="font-semibold text-sm">{step.title}</p>
                      <p className="text-xs text-muted-foreground flex-1">{step.text}</p>
                      <Button asChild size="sm" variant="outline" className="mt-1">
                        <Link to={step.to}>{step.cta}</Link>
                      </Button>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Backed Assets (live, from ownership_ledger) */}
            <TabsContent value="assets" className="space-y-4">
              {holdingItems.length === 0 ? (
                <Card className="bg-card border-border">
                  <CardContent className="py-16 text-center text-muted-foreground space-y-4">
                    <p>
                      You don't hold any units yet. Fund an instant-exit request on the Liquidity
                      Market to acquire ownership.
                    </p>
                    <Button asChild>
                      <Link to="/liquidity-market">Open the Liquidity Market</Link>
                    </Button>
                  </CardContent>
                </Card>
              ) : (
                holdingItems.map((asset) => (
                  <Card key={asset.property_id} className="bg-card border-border">
                    <CardContent className="p-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
                      <div>
                        <h3 className="text-lg font-semibold">{asset.title ?? "Property"}</h3>
                        <p className="text-sm text-muted-foreground">{asset.location ?? "—"}</p>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                        <div>
                          <p className="text-sm text-muted-foreground">Units Held</p>
                          <p className="text-lg font-semibold">{asset.units}</p>
                        </div>
                        <div>
                          <p className="text-sm text-muted-foreground">Unit Price</p>
                          <p className="text-lg font-semibold">${num(asset.unit_price).toLocaleString()}</p>
                        </div>
                        <div>
                          <p className="text-sm text-muted-foreground">Holdings Value</p>
                          <p className="text-lg font-semibold text-primary">
                            ${(asset.units * num(asset.unit_price)).toLocaleString()}
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-muted-foreground">Listed / Sellable</p>
                          <p className="text-lg font-semibold">
                            {asset.listed_units} / {asset.sellable_units}
                          </p>
                        </div>
                      </div>
                      {asset.sellable_units > 0 ? (
                        <Button asChild variant="outline" size="sm" className="gap-1.5 shrink-0">
                          <Link to={`/secondary-market?tab=sell&property=${asset.property_id}`}>
                            <Tag className="h-3 w-3" />
                            Sell on Secondary Market
                          </Link>
                        </Button>
                      ) : (
                        <Button variant="outline" size="sm" className="gap-1.5 shrink-0" disabled>
                          <Tag className="h-3 w-3" />
                          All units listed
                        </Button>
                      )}
                    </CardContent>
                  </Card>
                ))
              )}
              <p className="text-xs text-muted-foreground px-1">
                Holdings are read from the ownership ledger (the source of truth) — not from
                acquisition records, so resold units are reflected immediately.
              </p>
            </TabsContent>

            {/* Realized Cash Flows (Decision 1: no per-deal P&L, no "profit"/"returns" labels) */}
            <TabsContent value="returns" className="space-y-6">
              <div className="grid lg:grid-cols-3 gap-4">
                <Card className="bg-gradient-to-br from-primary to-primary/80 text-primary-foreground">
                  <CardContent className="p-6">
                    <TrendingUp className="h-8 w-8 mb-3" />
                    <p className="text-sm opacity-90">Rental Distributions Received</p>
                    <p className="text-3xl font-bold mt-1">${num(returns?.total_net).toLocaleString()}</p>
                    <p className="text-sm opacity-70 mt-1">Net of management fee</p>
                  </CardContent>
                </Card>
                <Card className="bg-card border-border">
                  <CardContent className="p-6">
                    <FileText className="h-8 w-8 text-primary mb-3" />
                    <p className="text-sm text-muted-foreground">Distributions Count</p>
                    <p className="text-3xl font-bold mt-1">{returns?.count ?? 0}</p>
                  </CardContent>
                </Card>
                <Card className="bg-card border-border">
                  <CardContent className="p-6">
                    <Wallet className="h-8 w-8 text-accent mb-3" />
                    <p className="text-sm text-muted-foreground">Resale Proceeds</p>
                    <p className="text-base font-medium mt-2 text-muted-foreground">
                      Settle to your wallet on each secondary-market sale (see{" "}
                      <Link to="/liquidity-dashboard?tab=wallet" className="text-primary hover:underline">
                        Wallet → Transactions
                      </Link>
                      ).
                    </p>
                  </CardContent>
                </Card>
              </div>

              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle>Rental Distribution History</CardTitle>
                  <CardDescription>
                    Realized cash flows on units you hold. This is not a profit calculation — there is
                    no per-deal P&amp;L (acquisitions can't be matched to specific resales).
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {(returns?.items ?? []).length === 0 ? (
                    <div className="py-10 text-center text-sm text-muted-foreground">
                      No distributions yet.
                    </div>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Period</TableHead>
                          <TableHead>Kind</TableHead>
                          <TableHead className="text-right">Gross</TableHead>
                          <TableHead className="text-right">Mgmt Fee</TableHead>
                          <TableHead className="text-right">Net Received</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {(returns?.items ?? []).map((item) => (
                          <TableRow key={item.distribution_id}>
                            <TableCell>{item.period_key}</TableCell>
                            <TableCell><Badge variant="outline" className="capitalize">{item.kind}</Badge></TableCell>
                            <TableCell className="text-right">${num(item.gross_amount).toLocaleString()}</TableCell>
                            <TableCell className="text-right text-muted-foreground">-${num(item.management_fee).toLocaleString()}</TableCell>
                            <TableCell className="text-right font-semibold text-primary">+${num(item.net_amount).toLocaleString()}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Fixed-Yield Pool (PASSIVE) — hard-gated OFF, no fake success, APY not "guaranteed" */}
            <TabsContent value="provide" className="space-y-6">
              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Lock className="h-5 w-5 text-muted-foreground" />
                    Fixed-Yield Liquidity Pool
                  </CardTitle>
                  <CardDescription>
                    A locked-term pool with indicative fixed rates. Not yet open for deposits.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {(settings?.tiers ?? []).map((tier) => (
                      <div key={tier.period_months} className="p-4 rounded-xl border border-border">
                        <div className="flex justify-between items-center mb-2">
                          <span className="font-semibold">{tier.period_months} mo</span>
                          <Badge variant="secondary" className="bg-muted text-muted-foreground">
                            {tier.apy_pct}% target
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Min: ${num(tier.min_amount).toLocaleString()}
                        </p>
                      </div>
                    ))}
                  </div>

                  <div className="flex items-start gap-3 p-4 rounded-xl border border-amber-500/30 bg-amber-500/5 text-sm">
                    <Droplet className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                    <div className="text-muted-foreground">
                      <p className="font-medium text-foreground">Not yet available</p>
                      The fixed-yield pool opens once the treasury yield source, reserve buffer and
                      asset-liability rules are finalized. The rates above are <strong>indicative
                      targets, not guaranteed</strong>.
                    </div>
                  </div>

                  <Button className="w-full" size="lg" disabled>
                    {passiveEnabled ? "Provide Liquidity" : "Deposits not yet open"}
                  </Button>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Wallet — the real per-user wallet (shared across roles): deposit, withdraw,
                saved cards and payout accounts. It funds exit requests and receives proceeds. */}
            <TabsContent value="wallet" className="space-y-6">
              <InvestorWallet />
            </TabsContent>

            <TabsContent value="cards" className="space-y-6">
              <VirtualCardRequest role="liquidity" />
            </TabsContent>
          </Tabs>
        </div>
      </section>
    </div>
  );
};

export default LiquidityDashboard;
