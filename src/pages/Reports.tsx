import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
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
  PieChart,
  Calendar,
  DollarSign,
  Download,
  Loader2,
  FileText,
} from "lucide-react";
import {
  investApi,
  returnsApi,
  installmentsApi,
  walletApi,
  type PortfolioSummary,
  type MyReturns,
  type InstallmentPlan,
  type WalletResponse,
} from "@/lib/api";

const monthLabel = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  return new Date(y, m - 1, 1).toLocaleString("en", { month: "short", year: "2-digit" });
};

const num = (s: string | undefined | null) => Number(s ?? 0);

const money = (s: string | number | undefined | null) =>
  `$${num(typeof s === "number" ? String(s) : s).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

/** Trigger a browser download for a fetched Blob (installment schedule PDF). */
const saveBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

const Reports = () => {
  const { data: portfolio, isLoading: loadingPortfolio } = useQuery({
    queryKey: ["reports", "portfolio"],
    queryFn: investApi.portfolio,
  });
  const { data: returns, isLoading: loadingReturns } = useQuery({
    queryKey: ["reports", "returns"],
    queryFn: returnsApi.getMine,
  });
  const { data: plans, isLoading: loadingPlans } = useQuery({
    queryKey: ["reports", "installments"],
    queryFn: installmentsApi.list,
  });
  const { data: wallet } = useQuery({
    queryKey: ["reports", "wallet"],
    queryFn: walletApi.getMe,
  });

  const loading = loadingPortfolio || loadingReturns || loadingPlans;

  const p: PortfolioSummary = portfolio ?? {
    invested: "0",
    current_value: "0",
    total_returns: "0",
    properties: 0,
    units: 0,
  };
  const r: MyReturns = returns ?? {
    total_net: "0",
    total_management_fee: "0",
    count: 0,
    monthly: [],
    items: [],
  };
  const w: WalletResponse | undefined = wallet;
  const installmentPlans: InstallmentPlan[] = plans ?? [];

  // Return-on-investment (net returns / invested), only when there's an invested base.
  const investedNum = num(p.invested);
  const roiPct = investedNum > 0 ? (num(p.total_returns) / investedNum) * 100 : null;
  const gainNum = num(p.current_value) - investedNum;

  const monthlyReturns = r.monthly.map((m) => ({ month: monthLabel(m.month), returns: num(m.net) }));
  let running = 0;
  const cumulativeReturns = r.monthly.map((m) => {
    running += num(m.net);
    return { month: monthLabel(m.month), total: running };
  });

  const downloadPlan = async (plan: InstallmentPlan) => {
    try {
      const blob = await installmentsApi.downloadSchedule(plan.id);
      const safe = (plan.property_title || "installment-plan").replace(/[^\w-]+/g, "-").toLowerCase();
      saveBlob(blob, `capimax-installments-${safe}.pdf`);
    } catch {
      toast.error("Could not download the schedule. Please try again.");
    }
  };

  const kpis = [
    { title: "Total Invested", value: money(p.invested), icon: Building2, sub: `${p.properties} ${p.properties === 1 ? "property" : "properties"} · ${p.units} units` },
    { title: "Current Value", value: money(p.current_value), icon: PieChart, sub: `${gainNum >= 0 ? "+" : ""}${money(gainNum)} vs invested` },
    { title: "Total Returns (net)", value: money(p.total_returns), icon: TrendingUp, sub: roiPct !== null ? `${roiPct.toFixed(1)}% ROI` : "No returns yet" },
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
              <div className="flex items-center gap-2 mb-1">
                <BarChart3 className="h-6 w-6 text-primary" />
                <h1 className="text-3xl font-bold text-foreground">Reports &amp; Analytics</h1>
              </div>
              <p className="text-muted-foreground">
                Your portfolio, returns and installment statements — all figures are live from your account.
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

        {/* Returns charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-lg">Monthly Returns</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-[300px]">
                {monthlyReturns.length === 0 ? (
                  <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                    No distributions yet.
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={monthlyReturns}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="month" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                      <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} tickFormatter={(v) => `$${v}`} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "8px" }}
                        formatter={(value: number) => [`$${value.toLocaleString()}`, "Returns"]}
                      />
                      <Bar dataKey="returns" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-lg">Cumulative Returns</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-[300px]">
                {cumulativeReturns.length === 0 ? (
                  <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                    No distributions yet.
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={cumulativeReturns}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="month" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                      <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} tickFormatter={(v) => `$${v / 1000}k`} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "8px" }}
                        formatter={(value: number) => [`$${value.toLocaleString()}`, "Total Returns"]}
                      />
                      <defs>
                        <linearGradient id="reportReturns" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <Area type="monotone" dataKey="total" stroke="hsl(var(--primary))" strokeWidth={2} fill="url(#reportReturns)" />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Distribution history */}
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">Distribution History</CardTitle>
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
                        No distributions received yet. Returns appear here once your properties pay out.
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

        {/* Installment statements */}
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              Installment Statements
            </CardTitle>
          </CardHeader>
          <CardContent>
            {installmentPlans.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                You have no installment plans yet.
              </p>
            ) : (
              <div className="space-y-3">
                {installmentPlans.map((plan) => {
                  const paid = plan.payments.filter((pm) => pm.status === "paid").length;
                  const total = plan.payments.length;
                  return (
                    <div
                      key={plan.id}
                      className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-lg border border-border p-4"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground truncate">{plan.property_title}</span>
                          <Badge variant={plan.status === "completed" ? "default" : "secondary"} className="capitalize">
                            {plan.status}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                          {plan.property_location || plan.property_city || "—"} · {plan.units_total} units · {plan.duration_months} months
                          {total > 0 && ` · ${paid}/${total} paid`}
                        </p>
                      </div>
                      <Button variant="outline" size="sm" className="gap-2 no-print shrink-0" onClick={() => downloadPlan(plan)}>
                        <Download className="h-4 w-4" />
                        Download PDF
                      </Button>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <p className="text-xs text-muted-foreground text-center">
          All figures are generated live from your account records. CapiMax PropShare · confidential statement.
        </p>
      </div>
    </div>
  );
};

export default Reports;
