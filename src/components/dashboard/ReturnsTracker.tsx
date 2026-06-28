import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useQuery } from "@tanstack/react-query";
import {
  TrendingUp,
  Download,
  Calendar,
  DollarSign,
  ArrowUpRight,
  RefreshCcw,
  Loader2,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
} from "recharts";
import { ReinvestReturns } from "./ReinvestReturns";
import { returnsApi, type MyReturns } from "@/lib/api";

const monthLabel = (ym: string) => {
  // "2026-01" -> "Jan" (falls back to the raw key if unparseable)
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  return new Date(y, m - 1, 1).toLocaleString("en", { month: "short" });
};

const num = (s: string) => Number(s);

export const ReturnsTracker = () => {
  const { data, isLoading } = useQuery({ queryKey: ["returns"], queryFn: returnsApi.getMine });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const returns: MyReturns = data ?? {
    total_net: "0",
    total_management_fee: "0",
    count: 0,
    monthly: [],
    items: [],
  };

  // Live chart data derived from real distribution_items.
  const monthlyReturns = returns.monthly.map((m) => ({
    month: monthLabel(m.month),
    returns: num(m.net),
  }));
  let running = 0;
  const cumulativeReturns = returns.monthly.map((m) => {
    running += num(m.net);
    return { month: monthLabel(m.month), total: running };
  });

  const totalReturns = num(returns.total_net);
  const monthsCount = returns.monthly.length || 1;
  const thisMonth = returns.monthly.length ? num(returns.monthly[returns.monthly.length - 1].net) : 0;
  const avgMonthly = totalReturns / monthsCount;

  const summary = [
    { title: "Total Returns", value: `$${totalReturns.toLocaleString()}` },
    { title: "This Month", value: `$${thisMonth.toLocaleString()}` },
    { title: "Average Monthly", value: `$${avgMonthly.toLocaleString(undefined, { maximumFractionDigits: 2 })}` },
    { title: "Mgmt Fees Paid", value: `$${num(returns.total_management_fee).toLocaleString()}` },
  ];

  return (
    <div className="space-y-6">
      {/* Reinvest Returns CTA Banner — reinvest = invest from wallet balance (no discount in v1) */}
      <Card className="bg-gradient-to-r from-primary/10 via-primary/5 to-accent/10 border-primary/30">
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 bg-primary/20 rounded-full flex items-center justify-center">
                <RefreshCcw className="h-5 w-5 text-primary" />
              </div>
              <div>
                <p className="font-semibold text-foreground">Reinvest Your Returns</p>
                <p className="text-sm text-muted-foreground">
                  Your ${totalReturns.toLocaleString()} in returns is available in your wallet to reinvest.
                </p>
              </div>
            </div>
            <ReinvestReturns availableReturns={totalReturns} variant="compact" />
          </div>
        </CardContent>
      </Card>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {summary.map((stat, index) => (
          <Card key={index} className="bg-card border-border">
            <CardContent className="p-6">
              <p className="text-sm text-muted-foreground">{stat.title}</p>
              <div className="flex items-end justify-between mt-2">
                <p className="text-2xl font-bold text-foreground">{stat.value}</p>
                <div className="flex items-center gap-1 text-primary">
                  <TrendingUp className="h-4 w-4" />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Monthly Returns Chart */}
        <Card className="bg-card border-border">
          <CardHeader className="flex flex-row items-center justify-between">
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
                    <YAxis
                      stroke="hsl(var(--muted-foreground))"
                      fontSize={12}
                      tickFormatter={(value) => `$${value}`}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "8px",
                      }}
                      formatter={(value: number) => [`$${value.toLocaleString()}`, "Returns"]}
                    />
                    <Bar dataKey="returns" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Cumulative Returns Chart */}
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
                    <YAxis
                      stroke="hsl(var(--muted-foreground))"
                      fontSize={12}
                      tickFormatter={(value) => `$${value / 1000}k`}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "8px",
                      }}
                      formatter={(value: number) => [`$${value.toLocaleString()}`, "Total Returns"]}
                    />
                    <defs>
                      <linearGradient id="colorReturns" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <Area
                      type="monotone"
                      dataKey="total"
                      stroke="hsl(var(--primary))"
                      strokeWidth={2}
                      fill="url(#colorReturns)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Distribution History */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Distribution History</CardTitle>
          <Button variant="outline" size="sm" className="gap-2" disabled>
            <Download className="h-4 w-4" />
            Download Statement
          </Button>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Period</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Net Amount</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Mgmt Fee</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Date</th>
                </tr>
              </thead>
              <tbody>
                {returns.items.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
                      No distributions received yet.
                    </td>
                  </tr>
                ) : (
                  returns.items.map((item) => (
                    <tr key={item.distribution_id} className="border-b border-border/50 hover:bg-muted/50">
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <DollarSign className="h-4 w-4 text-primary" />
                          <span className="text-sm font-medium capitalize">
                            {item.kind} · {item.period_key}
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-sm font-semibold text-primary">+${item.net_amount}</span>
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-sm text-muted-foreground">${item.management_fee}</span>
                      </td>
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
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
