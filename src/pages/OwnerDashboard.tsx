import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Building2,
  TrendingUp,
  DollarSign,
  Users,
  FileText,
  Wallet,
  Bell,
  Settings,
  Plus,
  Upload,
  Eye,
  Download,
  Calendar,
  CheckCircle2,
  Clock,
  AlertCircle,
  ArrowUpRight,
  BarChart3,
  PieChart,
  MapPin,
  CreditCard,
  Bitcoin,
  ArrowDownLeft,
  RefreshCcw,
  Send,
} from "lucide-react";
import { VirtualCardRequest } from "@/components/dashboard/VirtualCardRequest";
import { InvestorWallet } from "@/components/dashboard/InvestorWallet";
import { OwnerFinancials } from "@/components/dashboard/OwnerFinancials";
import { OwnerDocuments } from "@/components/dashboard/OwnerDocuments";
import { PropertyCreationForm } from "@/components/developer/PropertyCreationForm";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { ownerStatsApi, propertyApi, type PropertyDetail } from "@/lib/api";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const OWNER_READY = new Set(["ready-income", "ready-portfolio"]);

const MONTH_ABBR = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];
const monthLabel = (ym: string) => MONTH_ABBR[Number(ym.slice(5, 7)) - 1] ?? ym;

const toOwnerPropertyCard = (p: PropertyDetail) => ({
  id: p.id,
  name: p.title,
  location: p.location,
  image: p.image ?? p.images?.[0] ?? "",
  status: p.status === "active" || p.status === "funded" ? "active" : "funding",
  fundingProgress: Math.round(p.funding_progress),
  investors: p.investors_count,
  // Revenue/occupancy are post-investment operating metrics with no backend yet
  // (no per-owner rental ledger). Shown as "not available" rather than faked.
  nextPayout: OWNER_READY.has(p.model) ? "—" : "After completion",
});

// Server-authoritative money formatting; never fabricates a value.
const fmtMoney = (n: number) =>
  n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M` : `$${Math.round(n).toLocaleString()}`;

// "Not available yet" — no backend source for this metric (do NOT fake a number).
const NA = "Not available yet";

const OwnerDashboard = () => {
  const [activeTab, setActiveTab] = useState("overview");
  const navigate = useNavigate();
  const { user } = useAuth();
  const greetingName =
    user?.full_name?.trim() || user?.email?.split("@")[0] || "Property Owner";
  const { data: ownerProperties, isLoading: propertiesLoading } = useQuery({
    queryKey: ["owner-properties"],
    queryFn: () => propertyApi.listOwner(),
  });
  // Server-authoritative real-stats aggregation (Phase 15).
  const { data: stats } = useQuery({
    queryKey: ["owner", "portfolio-stats"],
    queryFn: ownerStatsApi.portfolioStats,
  });

  const revByProperty = new Map(
    (stats?.per_property ?? []).map((p) => [p.property_id, p.revenue_generated]),
  );
  const properties = (ownerProperties ?? []).map((p) => ({
    ...toOwnerPropertyCard(p),
    revenueGenerated: revByProperty.get(p.id) ?? "0.00",
  }));

  // Real monthly-revenue series for the chart (real zeros for empty months).
  const revenueSeries = (stats?.monthly_revenue_series ?? []).map((pt) => ({
    month: monthLabel(pt.month),
    revenue: Number(pt.amount),
  }));

  // value === null → honest empty state. Occupancy has NO data source yet (no fake number).
  const ownerStats: {
    title: string;
    value: string | null;
    note?: string;
    icon: typeof Building2;
  }[] = [
    {
      title: "Total Portfolio Value",
      value: stats ? fmtMoney(Number(stats.total_portfolio_value)) : null,
      icon: Building2,
    },
    {
      title: "Total Investors",
      value: stats ? stats.total_investors.toLocaleString() : null,
      icon: Users,
    },
    {
      title: "Monthly Revenue",
      value: stats ? fmtMoney(Number(stats.monthly_revenue_current)) : null,
      icon: DollarSign,
    },
    { title: "Avg. Occupancy", value: null, note: "No occupancy data yet", icon: TrendingUp },
  ];

  return (
    <div className="min-h-screen bg-background">
      <main>
        {/* Dashboard Header */}
        <section className="bg-gradient-to-br from-accent/10 via-background to-primary/5 py-8 border-b border-border">
          <div className="container mx-auto px-4">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <div>
                <Badge className="bg-accent text-accent-foreground mb-2">Property Owner</Badge>
                <h1 className="text-3xl font-bold text-foreground">
                  Welcome back, <span className="text-accent">{greetingName}</span>
                </h1>
                <p className="text-muted-foreground mt-1">
                  Manage your listed properties and track performance
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Notifications"
                  onClick={() => navigate("/notifications")}
                >
                  <Bell className="h-5 w-5" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Settings"
                  onClick={() => navigate("/settings")}
                >
                  <Settings className="h-5 w-5" />
                </Button>
                <Button className="gap-2" onClick={() => setActiveTab("list-property")}>
                  <Plus className="h-4 w-4" />
                  List Property
                </Button>
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
                <TabsTrigger value="properties" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                  <Building2 className="h-4 w-4" />
                  Properties
                </TabsTrigger>
                <TabsTrigger value="financials" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                  <DollarSign className="h-4 w-4" />
                  Financials
                </TabsTrigger>
                <TabsTrigger value="wallet" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                  <Wallet className="h-4 w-4" />
                  Wallet
                </TabsTrigger>
                <TabsTrigger value="documents" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                  <FileText className="h-4 w-4" />
                  Documents
                </TabsTrigger>
                <TabsTrigger value="list-property" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                  <Plus className="h-4 w-4" />
                  List Property
                </TabsTrigger>
                <TabsTrigger value="cards" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                  <CreditCard className="h-4 w-4" />
                  Virtual Cards
                </TabsTrigger>
              </TabsList>

              <TabsContent value="cards" className="space-y-6">
                <VirtualCardRequest role="owner" />
              </TabsContent>

              {/* Overview Tab */}
              <TabsContent value="overview" className="space-y-6">
                {/* Stats */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {ownerStats.map((stat, index) => (
                    <Card key={index} className="bg-card border-border">
                      <CardContent className="p-6">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm text-muted-foreground">{stat.title}</p>
                            {stat.value !== null ? (
                              <p className="text-2xl font-bold text-foreground mt-1">{stat.value}</p>
                            ) : (
                              <p className="text-sm text-muted-foreground mt-2 italic">
                                {stat.note ?? NA}
                              </p>
                            )}
                          </div>
                          <div className="h-12 w-12 rounded-full bg-accent/10 flex items-center justify-center">
                            <stat.icon className="h-6 w-6 text-accent" />
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                {/* Revenue Chart — real distributions generated on the owner's properties,
                    by month (real zeros for months with no distribution). */}
                <Card className="bg-card border-border">
                  <CardHeader>
                    <CardTitle>Monthly Revenue</CardTitle>
                    <CardDescription>
                      Distributions generated on your properties (last 6 months)
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="h-[300px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={revenueSeries}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                          <XAxis dataKey="month" stroke="hsl(var(--muted-foreground))" />
                          <YAxis
                            stroke="hsl(var(--muted-foreground))"
                            tickFormatter={(v) => `$${(v / 1000).toLocaleString()}k`}
                          />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: "hsl(var(--card))",
                              border: "1px solid hsl(var(--border))",
                              borderRadius: "8px",
                            }}
                            formatter={(value: number) => [`$${value.toLocaleString()}`, "Revenue"]}
                          />
                          <defs>
                            <linearGradient id="colorRevenue" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="hsl(var(--accent))" stopOpacity={0.3} />
                              <stop offset="95%" stopColor="hsl(var(--accent))" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <Area
                            type="monotone"
                            dataKey="revenue"
                            stroke="hsl(var(--accent))"
                            strokeWidth={2}
                            fill="url(#colorRevenue)"
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>

                {/* Properties Summary */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {properties.slice(0, 2).map((property) => (
                    <Card key={property.id} className="bg-card border-border overflow-hidden">
                      <div className="flex">
                        <img
                          src={property.image}
                          alt={property.name}
                          className="w-1/3 object-cover"
                        />
                        <div className="flex-1 p-4">
                          <div className="flex items-start justify-between mb-2">
                            <div>
                              <h3 className="font-semibold">{property.name}</h3>
                              <p className="text-sm text-muted-foreground">{property.location}</p>
                            </div>
                            <Badge className={property.status === "active" ? "bg-primary" : "bg-accent"}>
                              {property.status}
                            </Badge>
                          </div>
                          <div className="grid grid-cols-2 gap-2 mt-3">
                            <div>
                              <p className="text-xs text-muted-foreground">Revenue Generated</p>
                              <p className="font-semibold">
                                {fmtMoney(Number(property.revenueGenerated))}
                              </p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground">Occupancy</p>
                              <p className="text-xs text-muted-foreground italic mt-1">
                                No occupancy data yet
                              </p>
                            </div>
                          </div>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              </TabsContent>

              {/* Properties Tab */}
              <TabsContent value="properties" className="space-y-6">
                {propertiesLoading ? (
                  <div className="flex items-center justify-center py-16">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  </div>
                ) : properties.length === 0 ? (
                  <Card className="bg-card border-border">
                    <CardContent className="py-16 text-center text-muted-foreground">
                      You haven't listed any properties yet. Open the “List Property” tab to add one.
                    </CardContent>
                  </Card>
                ) : (
                  properties.map((property) => (
                  <Card key={property.id} className="bg-card border-border overflow-hidden">
                    <div className="flex flex-col md:flex-row">
                      <img
                        src={property.image}
                        alt={property.name}
                        className="w-full md:w-1/4 h-48 md:h-auto object-cover"
                      />
                      <div className="flex-1 p-6">
                        <div className="flex items-start justify-between mb-4">
                          <div>
                            <h3 className="text-xl font-semibold">{property.name}</h3>
                            <div className="flex items-center gap-1 text-muted-foreground mt-1">
                              <MapPin className="h-4 w-4" />
                              {property.location}
                            </div>
                          </div>
                          <Badge className={property.status === "active" ? "bg-primary" : "bg-accent"}>
                            {property.status === "active" ? "Active" : "Funding"}
                          </Badge>
                        </div>

                        {property.status === "funding" && (
                          <div className="mb-4">
                            <div className="flex justify-between mb-1">
                              <span className="text-sm text-muted-foreground">Funding Progress</span>
                              <span className="text-sm font-medium">{property.fundingProgress}%</span>
                            </div>
                            <Progress value={property.fundingProgress} className="h-2" />
                          </div>
                        )}

                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                          <div className="p-3 rounded-lg bg-muted/50">
                            <p className="text-xs text-muted-foreground">Investors</p>
                            <p className="text-lg font-semibold">{property.investors}</p>
                          </div>
                          <div className="p-3 rounded-lg bg-muted/50">
                            <p className="text-xs text-muted-foreground">Revenue Generated</p>
                            <p className="text-lg font-semibold">
                              {fmtMoney(Number(property.revenueGenerated))}
                            </p>
                          </div>
                          <div className="p-3 rounded-lg bg-muted/50">
                            <p className="text-xs text-muted-foreground">Occupancy</p>
                            <p className="text-sm text-muted-foreground italic mt-1">
                              No occupancy data yet
                            </p>
                          </div>
                          <div className="p-3 rounded-lg bg-muted/50">
                            <p className="text-xs text-muted-foreground">Next Payout</p>
                            <p className="text-lg font-semibold">{property.nextPayout}</p>
                          </div>
                        </div>

                        <div className="flex gap-3 mt-4">
                          <Button variant="outline" size="sm" className="gap-2" disabled>
                            <Eye className="h-4 w-4" />
                            View Details
                          </Button>
                          <Button variant="outline" size="sm" className="gap-2" disabled>
                            <BarChart3 className="h-4 w-4" />
                            Analytics
                          </Button>
                        </div>
                      </div>
                    </div>
                  </Card>
                  ))
                )}
              </TabsContent>

              {/* Financials Tab — the real wallet (balance + deposit + Phase-7 withdraw).
                  Owners use the same per-user wallet as everyone else; the prior mock
                  ($125k + fake withdraw) is retired. */}
              <TabsContent value="financials" className="space-y-6">
                <OwnerFinancials onWithdraw={() => setActiveTab("wallet")} />
              </TabsContent>

              {/* Wallet Tab — the real per-user wallet (balance + deposit + Phase-7 withdraw). */}
              <TabsContent value="wallet" className="space-y-6">
                <InvestorWallet />
              </TabsContent>

              {/* Documents Tab — deferred to the documents phase (needs app storage).
                  Honest-disabled (kept, not removed). */}
              <TabsContent value="documents" className="space-y-6">
                <OwnerDocuments />
              </TabsContent>

              {/* List Property Tab — same create→review workflow as the developer
                  surface (D6: one owner role, one POST /properties endpoint). */}
              <TabsContent value="list-property" className="space-y-6">
                <Card className="bg-card border-border">
                  <CardHeader>
                    <CardTitle>List a New Property</CardTitle>
                    <CardDescription>
                      Create your listing and submit it for review. Once an admin approves it, it
                      goes live on the marketplace.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <PropertyCreationForm />
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </div>
        </section>
      </main>
    </div>
  );
};

export default OwnerDashboard;
