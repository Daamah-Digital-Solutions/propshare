import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  BarChart3,
  Printer,
  TrendingUp,
  Wallet,
  Building2,
  PiggyBank,
  Calendar,
  DollarSign,
  Loader2,
} from "lucide-react";
import {
  liquidityApi,
  returnsApi,
  walletApi,
  type MyReturns,
  type WalletResponse,
} from "@/lib/api";

const monthLabel = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  return new Date(y, m - 1, 1).toLocaleString("en", { month: "short", year: "2-digit" });
};

const num = (s: string | number | undefined | null) => Number(s ?? 0);

const money = (s: string | number | undefined | null) =>
  `$${num(s).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const LpReports = () => {
  const { data: holdings, isLoading: loadingHoldings } = useQuery({
    queryKey: ["lp-reports", "holdings"],
    queryFn: () => liquidityApi.holdings(),
  });
  const { data: positions, isLoading: loadingPositions } = useQuery({
    queryKey: ["lp-reports", "positions"],
    queryFn: () => liquidityApi.positions(),
  });
  const { data: returns, isLoading: loadingReturns } = useQuery({
    queryKey: ["lp-reports", "returns"],
    queryFn: () => returnsApi.getMine(),
  });
  const { data: wallet } = useQuery({
    queryKey: ["lp-reports", "wallet"],
    queryFn: walletApi.getMe,
  });

  const loading = loadingHoldings || loadingPositions || loadingReturns;

  const holdingItems = useMemo(() => holdings?.items ?? [], [holdings]);
  const positionItems = useMemo(() => positions?.items ?? [], [positions]);
  const r: MyReturns = returns ?? {
    total_net: "0",
    total_management_fee: "0",
    count: 0,
    monthly: [],
    items: [],
  };
  const w: WalletResponse | undefined = wallet;

  // property_id -> title, for labelling funded buyouts (current holdings are the source).
  const titleFor = useMemo(() => {
    const m = new Map<string, string>();
    holdingItems.forEach((h) => h.title && m.set(h.property_id, h.title));
    return m;
  }, [holdingItems]);

  const holdingsValue = holdingItems.reduce((s, h) => s + h.units * num(h.unit_price), 0);
  const capitalDeployed = positionItems.reduce((s, pos) => s + num(pos.principal), 0);

  const monthlyDist = r.monthly.map((m) => ({ month: monthLabel(m.month), net: num(m.net) }));
  let running = 0;
  const cumulativeDist = r.monthly.map((m) => {
    running += num(m.net);
    return { month: monthLabel(m.month), total: running };
  });

  const kpis = [
    { title: "Holdings Value (Active)", value: money(holdingsValue), icon: Building2, sub: `${holdingItems.length} backed ${holdingItems.length === 1 ? "asset" : "assets"}` },
    { title: "Rental Distributions", value: money(r.total_net), icon: TrendingUp, sub: `${r.count} received · net of fees` },
    { title: "Capital Deployed", value: money(capitalDeployed), icon: PiggyBank, sub: `${positionItems.length} funded ${positionItems.length === 1 ? "buyout" : "buyouts"}` },
    { title: "Wallet Balance", value: w ? money(w.balance) : "—", icon: Wallet, sub: w ? `${money(w.pending_balance)} pending` : "Live balance" },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Print stylesheet: hide app chrome so "Save as PDF" produces a clean statement. */}
      <style>{`@media print {
        [data-sidebar], header, nav, .no-print { display: none !important; }
        main { padding: 0 !important; }
        body { background: #fff !important; }
      }`}</style>

      {/* Header */}
      <section className="bg-gradient-to-br from-primary/10 via-background to-accent/5 py-8 border-b border-border">
        <div className="container mx-auto px-4">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <Badge className="bg-primary text-primary-foreground mb-2">Liquidity Provider</Badge>
              <div className="flex items-center gap-2 mb-1">
                <BarChart3 className="h-6 w-6 text-primary" />
                <h1 className="text-3xl font-bold text-foreground">LP Reports &amp; Analytics</h1>
              </div>
              <p className="text-muted-foreground">
                The ownership you've acquired by funding instant exits, and your realized cash flows — all live from your account.
              </p>
            </div>
            <Button className="gap-2 no-print" onClick={() => window.print()}>
              <Printer className="h-4 w-4" />
              Print / Save as PDF
            </Button>
          </div>
        </div>
      </section>

      <div className="container mx-auto px-4 py-8 space-y-8">
        {/* KPI cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {kpis.map((k) => (
            <Card key={k.title} className="bg-card border-border">
              <CardContent className="p-6">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm text-muted-foreground">{k.title}</p>
                  <k.icon className="h-4 w-4 text-primary" />
                </div>
                <p className="text-2xl font-bold text-foreground">{k.value}</p>
                <p className="text-xs text-muted-foreground mt-1">{k.sub}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Distribution charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-lg">Monthly Rental Distributions</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-[300px]">
                {monthlyDist.length === 0 ? (
                  <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                    No distributions yet.
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={monthlyDist}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="month" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                      <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} tickFormatter={(v) => `$${v}`} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "8px" }}
                        formatter={(value: number) => [`$${value.toLocaleString()}`, "Net received"]}
                      />
                      <Bar dataKey="net" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-lg">Cumulative Distributions</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-[300px]">
                {cumulativeDist.length === 0 ? (
                  <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                    No distributions yet.
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={cumulativeDist}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="month" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                      <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} tickFormatter={(v) => `$${v / 1000}k`} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "8px" }}
                        formatter={(value: number) => [`$${value.toLocaleString()}`, "Total received"]}
                      />
                      <defs>
                        <linearGradient id="lpDist" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <Area type="monotone" dataKey="total" stroke="hsl(var(--primary))" strokeWidth={2} fill="url(#lpDist)" />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Backed assets (live from ownership ledger) */}
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">Backed Assets</CardTitle>
            <CardDescription>
              Units you currently hold — read from the ownership ledger, so resold units drop off immediately.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Property</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Units</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Unit Price</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Holdings Value</th>
                  </tr>
                </thead>
                <tbody>
                  {holdingItems.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
                        You don't hold any units yet. Fund an instant-exit request on the Liquidity Market to acquire ownership.
                      </td>
                    </tr>
                  ) : (
                    holdingItems.map((h) => (
                      <tr key={h.property_id} className="border-b border-border/50 hover:bg-muted/50">
                        <td className="py-3 px-4">
                          <div className="text-sm font-medium text-foreground">{h.title ?? "Property"}</div>
                          <div className="text-xs text-muted-foreground">{h.location ?? "—"}</div>
                        </td>
                        <td className="py-3 px-4 text-right text-sm">{h.units}</td>
                        <td className="py-3 px-4 text-right text-sm text-muted-foreground">{money(h.unit_price)}</td>
                        <td className="py-3 px-4 text-right text-sm font-semibold text-primary">
                          {money(h.units * num(h.unit_price))}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
                {holdingItems.length > 0 && (
                  <tfoot>
                    <tr className="border-t-2 border-border font-semibold">
                      <td className="py-3 px-4 text-sm">Total</td>
                      <td className="py-3 px-4" />
                      <td className="py-3 px-4" />
                      <td className="py-3 px-4 text-right text-sm text-primary">{money(holdingsValue)}</td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Funded buyouts history (acquisition audit — not current holdings) */}
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">Funded Buyouts</CardTitle>
            <CardDescription>
              Instant-exit requests you funded. "Entry spread" is the discount captured at acquisition —
              a recorded acquisition metric, not a realized profit figure.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Property</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Type</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Units</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Principal</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Entry Spread</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {positionItems.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                        No funded buyouts yet.
                      </td>
                    </tr>
                  ) : (
                    positionItems.map((pos) => (
                      <tr key={pos.position_id} className="border-b border-border/50 hover:bg-muted/50">
                        <td className="py-3 px-4 text-sm font-medium text-foreground">
                          {pos.property_id ? (titleFor.get(pos.property_id) ?? `Property ${pos.property_id.slice(0, 8)}`) : "—"}
                        </td>
                        <td className="py-3 px-4">
                          <Badge variant="outline" className="capitalize">{pos.classification}</Badge>
                        </td>
                        <td className="py-3 px-4 text-right text-sm">{pos.units_acquired ?? "—"}</td>
                        <td className="py-3 px-4 text-right text-sm text-muted-foreground">{money(pos.principal)}</td>
                        <td className="py-3 px-4 text-right text-sm text-primary">
                          {pos.spread_at_entry != null ? money(pos.spread_at_entry) : "—"}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <Calendar className="h-4 w-4" />
                            {pos.created_at ? new Date(pos.created_at).toLocaleDateString() : "—"}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Rental distribution history */}
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">Rental Distribution History</CardTitle>
            <CardDescription>
              Realized cash flows on units you hold. This is not a profit calculation — there is no
              per-deal P&amp;L (acquisitions can't be matched to specific resales).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Period</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Gross</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Mgmt Fee</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Net</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {r.items.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                        No distributions received yet.
                      </td>
                    </tr>
                  ) : (
                    r.items.map((item) => (
                      <tr key={item.distribution_id} className="border-b border-border/50 hover:bg-muted/50">
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <DollarSign className="h-4 w-4 text-primary" />
                            <span className="text-sm font-medium capitalize">{item.kind} · {item.period_key}</span>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-right text-sm text-muted-foreground">{money(item.gross_amount)}</td>
                        <td className="py-3 px-4 text-right text-sm text-muted-foreground">{money(item.management_fee)}</td>
                        <td className="py-3 px-4 text-right text-sm font-semibold text-primary">+{money(item.net_amount)}</td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <Calendar className="h-4 w-4" />
                            {item.period_end}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
                {r.items.length > 0 && (
                  <tfoot>
                    <tr className="border-t-2 border-border font-semibold">
                      <td className="py-3 px-4 text-sm">Total ({r.count})</td>
                      <td className="py-3 px-4" />
                      <td className="py-3 px-4 text-right text-sm text-muted-foreground">{money(r.total_management_fee)}</td>
                      <td className="py-3 px-4 text-right text-sm text-primary">{money(r.total_net)}</td>
                      <td className="py-3 px-4" />
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </CardContent>
        </Card>

        <p className="text-xs text-muted-foreground text-center">
          Realized cash flows only — resale proceeds settle to your wallet per sale (Wallet → Transactions).
          All figures are live from your account. CapiMax PropShare · confidential statement.
        </p>
      </div>
    </div>
  );
};

export default LpReports;
