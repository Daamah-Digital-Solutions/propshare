import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, DollarSign, Building2, PiggyBank, BarChart3 } from "lucide-react";
import { ExitButton } from "@/components/exit/ExitButton";
import { investApi, returnsApi } from "@/lib/api";

const money = (v: string | number) => `$${Number(v).toLocaleString()}`;

export const PortfolioOverview = () => {
  // Server-authoritative portfolio summary (ownership_ledger + wallet) — no client math.
  const { data: portfolio } = useQuery({
    queryKey: ["portfolio", "summary"],
    queryFn: investApi.portfolio,
  });
  const { data: investments } = useQuery({ queryKey: ["investments", "list"], queryFn: investApi.list });
  const { data: returns } = useQuery({ queryKey: ["returns", "mine"], queryFn: returnsApi.getMine });

  const stats = [
    { title: "Total Invested", value: portfolio ? money(portfolio.invested) : "—", icon: DollarSign },
    { title: "Current Value", value: portfolio ? money(portfolio.current_value) : "—", icon: BarChart3 },
    { title: "Total Returns", value: portfolio ? money(portfolio.total_returns) : "—", icon: TrendingUp },
    { title: "Active Properties", value: portfolio ? String(portfolio.properties) : "—", icon: Building2 },
  ];

  // Recent activity merged from the real investment + return histories.
  const activity = [
    ...(investments?.items ?? []).map((i) => ({
      id: `inv-${i.id}`,
      label: "Investment",
      amount: `-${money(i.total_charged)}`,
      date: i.created_at,
      positive: false,
    })),
    ...(returns?.items ?? []).map((r) => ({
      id: `ret-${r.distribution_id}-${r.property_id}`,
      label: `Return (${r.kind})`,
      amount: `+${money(r.net_amount)}`,
      date: r.period_end,
      positive: true,
    })),
  ]
    .sort((a, b) => (b.date || "").localeCompare(a.date || ""))
    .slice(0, 6);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-bold">Portfolio Overview</h2>
          <p className="text-sm text-muted-foreground">
            Track performance, allocation and exit ownership positions.
          </p>
        </div>
        <ExitButton variant="default" label="Exit Position" />
      </div>

      {/* Stats Grid — live from the server */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, index) => (
          <Card key={index} className="bg-card border-border">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">{stat.title}</p>
                  <p className="text-2xl font-bold text-foreground mt-1">{stat.value}</p>
                  {stat.title === "Current Value" && portfolio && (
                    <p className="text-xs text-muted-foreground mt-2">
                      {portfolio.units} unit(s) held
                    </p>
                  )}
                </div>
                <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
                  <stat.icon className="h-6 w-6 text-primary" />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Allocation — no per-model breakdown source yet; honest-disabled (not removed). */}
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">Portfolio Allocation</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground py-12 text-center">
              Allocation breakdown is not available yet.
            </p>
          </CardContent>
        </Card>

        {/* Recent Activity — live from investments + returns */}
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">Recent Activity</CardTitle>
          </CardHeader>
          <CardContent>
            {activity.length === 0 ? (
              <p className="text-sm text-muted-foreground py-8 text-center">No activity yet.</p>
            ) : (
              <div className="space-y-4">
                {activity.map((a) => (
                  <div
                    key={a.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`h-10 w-10 rounded-full flex items-center justify-center ${
                          a.positive ? "bg-primary/10" : "bg-accent/10"
                        }`}
                      >
                        {a.positive ? (
                          <PiggyBank className="h-5 w-5 text-primary" />
                        ) : (
                          <Building2 className="h-5 w-5 text-accent" />
                        )}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-foreground">{a.label}</p>
                        <p className="text-xs text-muted-foreground">
                          {a.date ? new Date(a.date).toLocaleDateString() : ""}
                        </p>
                      </div>
                    </div>
                    <p
                      className={`text-sm font-semibold ${
                        a.positive ? "text-primary" : "text-foreground"
                      }`}
                    >
                      {a.amount}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Investment Goals — no goals backend yet; honest-disabled (not removed). */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-lg">Investment Goals</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground py-8 text-center">
            Goal tracking is not available yet.
          </p>
        </CardContent>
      </Card>
    </div>
  );
};
