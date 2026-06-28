import { useMemo } from "react";
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
  CheckCircle2,
  Lock,
  CreditCard,
  Droplet,
} from "lucide-react";
import { VirtualCardRequest } from "@/components/dashboard/VirtualCardRequest";
import { liquidityApi, returnsApi } from "@/lib/api";

const num = (s: string | null | undefined) => Number(s ?? 0);

const LiquidityDashboard = () => {
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

  const holdingItems = useMemo(() => holdings?.items ?? [], [holdings]);
  const passiveEnabled = settings?.passive_enabled ?? false;

  const stats = useMemo(() => {
    const holdingsValue = holdingItems.reduce((s, h) => s + h.units * num(h.unit_price), 0);
    return [
      { title: "Holdings Value (Active)", value: `$${holdingsValue.toLocaleString()}` },
      { title: "Rental Distributions", value: `$${num(returns?.total_net).toLocaleString()}` },
      { title: "Backed Assets", value: String(holdingItems.length) },
      { title: "Active Positions", value: String((positions?.items ?? []).length) },
    ];
  }, [holdingItems, returns, positions]);

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
          <Tabs defaultValue="overview" className="space-y-8">
            <TabsList className="w-full flex flex-wrap justify-start gap-2 h-auto p-2 bg-muted/50">
              <TabsTrigger value="overview" className="gap-2"><BarChart3 className="h-4 w-4" />Overview</TabsTrigger>
              <TabsTrigger value="assets" className="gap-2"><Building2 className="h-4 w-4" />Backed Assets</TabsTrigger>
              <TabsTrigger value="returns" className="gap-2"><TrendingUp className="h-4 w-4" />Realized Cash Flows</TabsTrigger>
              <TabsTrigger value="provide" className="gap-2"><PiggyBank className="h-4 w-4" />Fixed-Yield Pool</TabsTrigger>
              <TabsTrigger value="wallet" className="gap-2"><Wallet className="h-4 w-4" />Wallet</TabsTrigger>
              <TabsTrigger value="cards" className="gap-2"><CreditCard className="h-4 w-4" />Virtual Cards</TabsTrigger>
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
              <Card className="bg-card border-border">
                <CardContent className="p-6 text-sm text-muted-foreground">
                  Find fundable instant-exit opportunities on the{" "}
                  <a href="/liquidity-market" className="text-primary hover:underline">Liquidity Market</a>.
                  Returns shown here are realized cash flows (rental distributions + resale proceeds),
                  not a projected or guaranteed figure.
                </CardContent>
              </Card>
            </TabsContent>

            {/* Backed Assets (live, from ownership_ledger) */}
            <TabsContent value="assets" className="space-y-4">
              {holdingItems.length === 0 ? (
                <Card className="bg-card border-border">
                  <CardContent className="py-16 text-center text-muted-foreground">
                    You don't hold any units yet. Fund an instant-exit request on the Liquidity Market to acquire ownership.
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
                      <div className="grid grid-cols-3 gap-6">
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
                      </div>
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
                      Settle to your wallet on each secondary-market sale (see Wallet → Transactions).
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

            {/* Wallet */}
            <TabsContent value="wallet" className="space-y-6">
              <Card className="bg-card border-border">
                <CardContent className="p-6 space-y-3">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-primary" />
                    <p className="font-medium">Your wallet is shared across roles.</p>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Deposit, view your balance and ledger, and withdraw to bank/crypto from the
                    investor <a href="/dashboard" className="text-primary hover:underline">Wallet</a> tab —
                    the same balance funds your liquidity allocations and receives your proceeds.
                  </p>
                </CardContent>
              </Card>
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
