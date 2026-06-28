import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Handshake,
  Users,
  DollarSign,
  Wallet,
  BarChart3,
  Percent,
  Copy,
  CreditCard,
  CheckCircle2,
} from "lucide-react";
import { VirtualCardRequest } from "@/components/dashboard/VirtualCardRequest";
import { InvestorWallet } from "@/components/dashboard/InvestorWallet";
import { brokerApi } from "@/lib/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const EVENT_LABEL: Record<string, string> = {
  investment_platform_fee: "Purchase fee",
  distribution_mgmt_fee: "Management fee",
};

const BrokerDashboard = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get("tab") || "overview";
  const setActiveTab = (tab: string) => setSearchParams({ tab }, { replace: true });

  const { data: dashboard } = useQuery({ queryKey: ["broker", "dashboard"], queryFn: brokerApi.dashboard });
  const { data: code } = useQuery({ queryKey: ["broker", "code"], queryFn: brokerApi.referralCode });
  const { data: referrals } = useQuery({ queryKey: ["broker", "referrals"], queryFn: brokerApi.referrals });
  const { data: commissions } = useQuery({
    queryKey: ["broker", "commissions"],
    queryFn: brokerApi.commissions,
  });

  // Monthly commission totals, aggregated live from the real commission ledger.
  const monthly = useMemo(() => {
    const m: Record<string, number> = {};
    (commissions?.items ?? []).forEach((c) => {
      const key = (c.created_at || "").slice(0, 7); // YYYY-MM
      if (key) m[key] = (m[key] ?? 0) + parseFloat(c.commission_amount);
    });
    return Object.entries(m)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([month, commission]) => ({ month, commission }));
  }, [commissions]);

  const stats = [
    { title: "Referred Clients", value: dashboard ? String(dashboard.total_referrals) : "—", icon: Users },
    {
      title: "Total Commission",
      value: dashboard ? `$${Number(dashboard.total_commission).toLocaleString()}` : "—",
      icon: DollarSign,
    },
    {
      title: "Commission Rate",
      value: dashboard ? `${dashboard.commission_rate}%` : "—",
      icon: Percent,
    },
  ];

  const copyLink = async () => {
    if (!code?.share_link) return;
    await navigator.clipboard.writeText(code.share_link);
    toast.success("Referral link copied");
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Dashboard Header */}
      <section className="bg-gradient-to-br from-accent/10 via-background to-primary/5 py-8 border-b border-border">
        <div className="container mx-auto px-4">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <Badge className="bg-accent text-accent-foreground mb-2">Broker</Badge>
              <h1 className="text-3xl font-bold text-foreground">Broker Dashboard</h1>
              <p className="text-muted-foreground mt-1">Track your referrals and commissions</p>
            </div>
          </div>
        </div>
      </section>

      {/* Dashboard Content */}
      <section className="py-8">
        <div className="container mx-auto px-4">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-8">
            <TabsList className="w-full flex flex-wrap justify-start gap-2 h-auto p-2 bg-muted/50">
              <TabsTrigger value="overview" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                <BarChart3 className="h-4 w-4" />
                Overview
              </TabsTrigger>
              <TabsTrigger value="referrals" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                <Handshake className="h-4 w-4" />
                Referrals
              </TabsTrigger>
              <TabsTrigger value="commissions" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                <DollarSign className="h-4 w-4" />
                Commissions
              </TabsTrigger>
              <TabsTrigger value="wallet" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                <Wallet className="h-4 w-4" />
                Wallet
              </TabsTrigger>
              <TabsTrigger value="cards" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                <CreditCard className="h-4 w-4" />
                Virtual Cards
              </TabsTrigger>
            </TabsList>

            <TabsContent value="cards" className="space-y-6">
              <VirtualCardRequest role="broker" />
            </TabsContent>

            <TabsContent value="overview" className="space-y-6">
              {/* Referral link */}
              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle className="text-base">Your referral link</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                    <code className="flex-1 px-3 py-2 rounded-md bg-muted text-sm break-all">
                      {code?.share_link ?? "Generating…"}
                    </code>
                    <Button onClick={copyLink} disabled={!code} className="gap-2">
                      <Copy className="h-4 w-4" />
                      Copy link
                    </Button>
                  </div>
                  <p className="text-sm text-muted-foreground mt-2">
                    Clients who sign up with your code are linked to you. You earn{" "}
                    {dashboard ? `${dashboard.commission_rate}%` : "a share"} of the platform
                    revenue from their investments — never a cut of their capital.
                  </p>
                </CardContent>
              </Card>

              {/* Stats */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {stats.map((stat, index) => (
                  <Card key={index} className="bg-card border-border">
                    <CardContent className="p-6">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm text-muted-foreground">{stat.title}</p>
                          <p className="text-2xl font-bold text-foreground mt-1">{stat.value}</p>
                        </div>
                        <div className="h-12 w-12 rounded-full bg-accent/10 flex items-center justify-center">
                          <stat.icon className="h-6 w-6 text-accent" />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Commission Chart */}
              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle>Monthly Commissions</CardTitle>
                </CardHeader>
                <CardContent>
                  {monthly.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-12 text-center">
                      No commissions yet. They accrue as your referred clients invest and earn.
                    </p>
                  ) : (
                    <div className="h-[300px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={monthly}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                          <XAxis dataKey="month" stroke="hsl(var(--muted-foreground))" />
                          <YAxis
                            stroke="hsl(var(--muted-foreground))"
                            tickFormatter={(v) => `$${v}`}
                          />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: "hsl(var(--card))",
                              border: "1px solid hsl(var(--border))",
                              borderRadius: "8px",
                            }}
                            formatter={(value: number) => [`$${value.toLocaleString()}`, "Commission"]}
                          />
                          <Bar dataKey="commission" fill="hsl(var(--accent))" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="referrals" className="space-y-6">
              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle>Referred Clients</CardTitle>
                </CardHeader>
                <CardContent>
                  {(referrals?.items.length ?? 0) === 0 ? (
                    <p className="text-sm text-muted-foreground py-8 text-center">
                      No referrals yet. Share your link to start earning commissions.
                    </p>
                  ) : (
                    <div className="space-y-4">
                      {referrals?.items.map((ref) => (
                        <div
                          key={ref.referral_id}
                          className="flex items-center justify-between p-4 rounded-lg bg-muted/30"
                        >
                          <div className="flex items-center gap-4">
                            <div className="h-10 w-10 rounded-full bg-accent/10 flex items-center justify-center">
                              <CheckCircle2 className="h-5 w-5 text-accent" />
                            </div>
                            <div>
                              <p className="font-medium">{ref.client_masked}</p>
                              <p className="text-sm text-muted-foreground">
                                Joined {new Date(ref.created_at).toLocaleDateString()}
                              </p>
                            </div>
                          </div>
                          <div className="text-right">
                            <p className="font-semibold text-accent">
                              +${Number(ref.commission_to_date).toLocaleString()}
                            </p>
                            <p className="text-sm text-muted-foreground">commission to date</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="commissions" className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card className="bg-gradient-to-br from-accent to-accent/80 text-accent-foreground">
                  <CardContent className="p-6">
                    <DollarSign className="h-8 w-8 mb-3" />
                    <p className="text-sm opacity-90">Total Earned</p>
                    <p className="text-3xl font-bold mt-1">
                      ${dashboard ? Number(dashboard.total_commission).toLocaleString() : "0"}
                    </p>
                  </CardContent>
                </Card>
                <Card className="bg-card border-border">
                  <CardContent className="p-6">
                    <Percent className="h-8 w-8 text-accent mb-3" />
                    <p className="text-sm text-muted-foreground">Commission Rate</p>
                    <p className="text-3xl font-bold mt-1">
                      {dashboard ? `${dashboard.commission_rate}%` : "—"}
                    </p>
                  </CardContent>
                </Card>
              </div>

              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle>Commission Ledger</CardTitle>
                </CardHeader>
                <CardContent>
                  {(commissions?.items.length ?? 0) === 0 ? (
                    <p className="text-sm text-muted-foreground py-8 text-center">
                      No commissions recorded yet.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      {commissions?.items.map((c) => (
                        <div
                          key={c.id}
                          className="flex items-center justify-between p-3 rounded-lg bg-muted/30"
                        >
                          <div>
                            <p className="font-medium text-sm">
                              {EVENT_LABEL[c.revenue_event_type] ?? c.revenue_event_type}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {new Date(c.created_at).toLocaleDateString()} · {c.commission_rate}% of $
                              {Number(c.revenue_amount).toLocaleString()} platform revenue
                            </p>
                          </div>
                          <p className="font-semibold text-accent">
                            +${Number(c.commission_amount).toLocaleString()}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="wallet" className="space-y-6">
              {/* The wallet is per-user; commissions credit the same wallet. Withdrawals
                  use the live Phase-7 rails inside this shared component. */}
              <InvestorWallet />
            </TabsContent>
          </Tabs>
        </div>
      </section>
    </div>
  );
};

export default BrokerDashboard;
