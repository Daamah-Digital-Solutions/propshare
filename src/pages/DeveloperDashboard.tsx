import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  Building2,
  TrendingUp,
  DollarSign,
  Users,
  Wallet,
  Bell,
  Settings,
  Upload,
  Eye,
  Download,
  Calendar,
  Clock,
  AlertCircle,
  ArrowUpRight,
  BarChart3,
  HardHat,
  MapPin,
  Hammer,
  Target,
  CreditCard,
} from "lucide-react";
import { VirtualCardRequest } from "@/components/dashboard/VirtualCardRequest";
import { PropertyCreationForm } from "@/components/developer/PropertyCreationForm";
import { MilestonesManager } from "@/components/developer/MilestonesManager";
import { InvestorCommunications } from "@/components/developer/InvestorCommunications";
import { useQuery } from "@tanstack/react-query";
import { ownerStatsApi, propertyApi, type PropertyDetail } from "@/lib/api";
import { Loader2 } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const READY_MODELS = new Set(["ready-income", "ready-portfolio"]);

const MONTH_ABBR = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];
const monthLabel = (ym: string) => MONTH_ABBR[Number(ym.slice(5, 7)) - 1] ?? ym;

type ProjectCard = {
  id: string;
  name: string;
  location: string;
  image: string;
  status: "construction" | "funding" | "planning";
  constructionProgress: number;
  fundingProgress: number;
  investors: number;
  totalRaised: number;
  targetAmount: number;
  expectedCompletion: string;
  phase: string;
};

const PHASE_LABEL: Record<ProjectCard["status"], string> = {
  construction: "Under Construction",
  funding: "Funding",
  planning: "In Review",
};

const toProjectCard = (p: PropertyDetail): ProjectCard => {
  const content = (p.content ?? {}) as Record<string, unknown>;
  const status: ProjectCard["status"] =
    p.status === "draft" || p.status === "under_review" || p.status === "closed"
      ? "planning"
      : !READY_MODELS.has(p.model)
        ? "construction"
        : "funding";
  return {
    id: p.id,
    name: p.title,
    location: p.location,
    image: p.image ?? p.images?.[0] ?? "",
    status,
    // Phase 15b — real construction % computed from milestones (legacy blob fallback).
    constructionProgress: p.construction_progress ?? Number(content.constructionProgress ?? 0),
    fundingProgress: Math.round(p.funding_progress),
    investors: p.investors_count,
    totalRaised: p.funded_amount,
    targetAmount: p.total_value,
    expectedCompletion: p.expected_completion ?? "TBD",
    phase: PHASE_LABEL[status],
  };
};

// Server-authoritative money formatting; never fabricates a value.
const fmtMoney = (n: number) =>
  n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M` : `$${Math.round(n).toLocaleString()}`;

// "Not available yet" — no backend source for this metric (do NOT fake a number).
const NA = "Not available yet";

const VALID_TABS = ["overview", "projects", "funding", "milestones", "investors", "cards"];

const DeveloperDashboard = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState(() =>
    VALID_TABS.includes(tabFromUrl || "") ? tabFromUrl! : "overview",
  );
  useEffect(() => {
    if (tabFromUrl && VALID_TABS.includes(tabFromUrl) && tabFromUrl !== activeTab) {
      setActiveTab(tabFromUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tabFromUrl]);
  const handleTabChange = (value: string) => {
    setActiveTab(value);
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        p.set("tab", value);
        return p;
      },
      { replace: true },
    );
  };
  const navigate = useNavigate();
  const { user } = useAuth();
  const greetingName =
    user?.full_name?.trim() || user?.email?.split("@")[0] || "Developer";
  const { data: ownerProperties, isLoading: projectsLoading } = useQuery({
    queryKey: ["owner-properties"],
    queryFn: () => propertyApi.listOwner(),
  });
  const projects = (ownerProperties ?? []).map(toProjectCard);

  // Server-authoritative funding aggregation (Phase 15): monthly series, this-month, repeat investors.
  const { data: funding } = useQuery({
    queryKey: ["owner", "funding-stats"],
    queryFn: ownerStatsApi.fundingStats,
  });
  const fundingSeries = (funding?.monthly_funding_series ?? []).map((pt) => ({
    month: monthLabel(pt.month),
    amount: Number(pt.amount),
  }));

  // Real, derivable stats (Σ / avg over the developer's own projects).
  const totalRaised = projects.reduce((s, p) => s + (p.totalRaised ?? 0), 0);
  const totalTarget = projects.reduce((s, p) => s + (p.targetAmount ?? 0), 0);
  const totalInvestors = projects.reduce((s, p) => s + (p.investors ?? 0), 0);
  const avgFunding = projects.length
    ? Math.round(projects.reduce((s, p) => s + p.fundingProgress, 0) / projects.length)
    : 0;
  const avgInvestment = totalInvestors > 0 ? totalRaised / totalInvestors : null;
  const fundingProjects = projects.filter((p) => p.status === "funding");
  const activeFundingGoals = fundingProjects.reduce((s, p) => s + (p.targetAmount ?? 0), 0);

  // value === null → honest-disabled card (no real data source). Never a fake number.
  const developerStats: {
    title: string;
    value: string | null;
    icon: typeof Building2;
  }[] = [
    { title: "Active Projects", value: projects.length.toLocaleString(), icon: Building2 },
    { title: "Total Raised", value: fmtMoney(totalRaised), icon: DollarSign },
    { title: "Total Investors", value: totalInvestors.toLocaleString(), icon: Users },
    { title: "Avg. Funding Rate", value: `${avgFunding}%`, icon: Target },
  ];

  return (
    <div className="min-h-screen bg-background">
      <main>
        {/* Dashboard Header */}
        <section className="bg-gradient-to-br from-primary/10 via-background to-accent/5 py-8 border-b border-border">
          <div className="container mx-auto px-4">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <div>
                <Badge className="bg-primary text-primary-foreground mb-2">Developer</Badge>
                <h1 className="text-3xl font-bold text-foreground">
                  Welcome back, <span className="text-primary">{greetingName}</span>
                </h1>
                <p className="text-muted-foreground mt-1">
                  Manage your development projects and investor relations
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
                <PropertyCreationForm />
              </div>
            </div>
          </div>
        </section>

        {/* Dashboard Content */}
        <section className="py-8">
          <div className="container mx-auto px-4">
            <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-8">
              <TabsList className="w-full flex flex-wrap justify-start gap-2 h-auto p-2 bg-muted/50">
                <TabsTrigger value="overview" className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
                  <BarChart3 className="h-4 w-4" />
                  Overview
                </TabsTrigger>
                <TabsTrigger value="projects" className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
                  <HardHat className="h-4 w-4" />
                  Projects
                </TabsTrigger>
                <TabsTrigger value="funding" className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
                  <DollarSign className="h-4 w-4" />
                  Funding
                </TabsTrigger>
                <TabsTrigger value="milestones" className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
                  <Target className="h-4 w-4" />
                  Milestones
                </TabsTrigger>
                <TabsTrigger value="investors" className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
                  <Users className="h-4 w-4" />
                  Investors
                </TabsTrigger>
                <TabsTrigger value="cards" className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
                  <CreditCard className="h-4 w-4" />
                  Virtual Cards
                </TabsTrigger>
              </TabsList>

              <TabsContent value="cards" className="space-y-6">
                <VirtualCardRequest role="developer" />
              </TabsContent>

              {/* Overview Tab */}
              <TabsContent value="overview" className="space-y-6">
                {/* Stats */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {developerStats.map((stat, index) => (
                    <Card key={index} className="bg-card border-border">
                      <CardContent className="p-6">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm text-muted-foreground">{stat.title}</p>
                            {stat.value !== null ? (
                              <p className="text-2xl font-bold text-foreground mt-1">{stat.value}</p>
                            ) : (
                              <p className="text-sm text-muted-foreground mt-2 italic">{NA}</p>
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

                {/* Funding Chart — real confirmed investments on the developer's projects,
                    by month (real zeros for months with no funding). */}
                <Card className="bg-card border-border">
                  <CardHeader>
                    <CardTitle>Monthly Funding Raised</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="h-[300px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={fundingSeries}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                          <XAxis dataKey="month" stroke="hsl(var(--muted-foreground))" />
                          <YAxis
                            stroke="hsl(var(--muted-foreground))"
                            tickFormatter={(v) => `$${(v / 1_000_000).toLocaleString()}M`}
                          />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: "hsl(var(--card))",
                              border: "1px solid hsl(var(--border))",
                              borderRadius: "8px",
                            }}
                            formatter={(value: number) => [`$${value.toLocaleString()}`, "Raised"]}
                          />
                          <Bar dataKey="amount" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>

                {/* Active Projects Summary */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {projects.filter(p => p.status === "construction").slice(0, 2).map((project) => (
                    <Card key={project.id} className="bg-card border-border overflow-hidden">
                      <div className="flex">
                        <img
                          src={project.image}
                          alt={project.name}
                          className="w-1/3 object-cover"
                        />
                        <div className="flex-1 p-4">
                          <div className="flex items-start justify-between mb-2">
                            <div>
                              <h3 className="font-semibold">{project.name}</h3>
                              <p className="text-sm text-muted-foreground">{project.location}</p>
                            </div>
                            <Badge className="bg-accent text-accent-foreground">
                              <Hammer className="h-3 w-3 mr-1" />
                              {project.phase}
                            </Badge>
                          </div>
                          <div className="space-y-2 mt-3">
                            <div>
                              <div className="flex justify-between text-sm mb-1">
                                <span className="text-muted-foreground">Construction</span>
                                <span className="font-medium">{project.constructionProgress}%</span>
                              </div>
                              <Progress value={project.constructionProgress} className="h-2" />
                            </div>
                          </div>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              </TabsContent>

              {/* Projects Tab */}
              <TabsContent value="projects" className="space-y-6">
                {projectsLoading ? (
                  <div className="flex items-center justify-center py-16">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  </div>
                ) : projects.length === 0 ? (
                  <Card className="bg-card border-border">
                    <CardContent className="py-16 text-center text-muted-foreground">
                      You haven't created any projects yet. Use “New Project” to list your first
                      property.
                    </CardContent>
                  </Card>
                ) : (
                  projects.map((project) => (
                  <Card key={project.id} className="bg-card border-border overflow-hidden">
                    <div className="flex flex-col md:flex-row">
                      <img
                        src={project.image}
                        alt={project.name}
                        className="w-full md:w-1/4 h-48 md:h-auto object-cover"
                      />
                      <div className="flex-1 p-6">
                        <div className="flex items-start justify-between mb-4">
                          <div>
                            <h3 className="text-xl font-semibold">{project.name}</h3>
                            <div className="flex items-center gap-1 text-muted-foreground mt-1">
                              <MapPin className="h-4 w-4" />
                              {project.location}
                            </div>
                          </div>
                          <Badge className={
                            project.status === "construction" ? "bg-accent" :
                            project.status === "funding" ? "bg-primary" :
                            "bg-muted"
                          }>
                            {project.status === "construction" ? (
                              <><Hammer className="h-3 w-3 mr-1" />Under Construction</>
                            ) : project.status === "funding" ? (
                              <><DollarSign className="h-3 w-3 mr-1" />Funding</>
                            ) : (
                              <><Clock className="h-3 w-3 mr-1" />Planning</>
                            )}
                          </Badge>
                        </div>

                        <div className="space-y-3 mb-4">
                          {project.status !== "planning" && (
                            <>
                              <div>
                                <div className="flex justify-between text-sm mb-1">
                                  <span className="text-muted-foreground">Funding Progress</span>
                                  <span className="font-medium">{project.fundingProgress}%</span>
                                </div>
                                <Progress value={project.fundingProgress} className="h-2" />
                              </div>
                              {project.status === "construction" && (
                                <div>
                                  <div className="flex justify-between text-sm mb-1">
                                    <span className="text-muted-foreground">Construction Progress</span>
                                    <span className="font-medium">{project.constructionProgress}%</span>
                                  </div>
                                  <Progress value={project.constructionProgress} className="h-2 [&>div]:bg-accent" />
                                </div>
                              )}
                            </>
                          )}
                        </div>

                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                          <div className="p-3 rounded-lg bg-muted/50">
                            <p className="text-xs text-muted-foreground">Total Raised</p>
                            <p className="text-lg font-semibold">${(project.totalRaised/1000000).toFixed(1)}M</p>
                          </div>
                          <div className="p-3 rounded-lg bg-muted/50">
                            <p className="text-xs text-muted-foreground">Target</p>
                            <p className="text-lg font-semibold">${(project.targetAmount/1000000).toFixed(1)}M</p>
                          </div>
                          <div className="p-3 rounded-lg bg-muted/50">
                            <p className="text-xs text-muted-foreground">Investors</p>
                            <p className="text-lg font-semibold">{project.investors}</p>
                          </div>
                          <div className="p-3 rounded-lg bg-muted/50">
                            <p className="text-xs text-muted-foreground">Completion</p>
                            <p className="text-lg font-semibold">{project.expectedCompletion}</p>
                          </div>
                        </div>

                        <div className="flex gap-3 mt-4">
                          <Button variant="outline" size="sm" className="gap-2" disabled>
                            <Eye className="h-4 w-4" />
                            View Details
                          </Button>
                          <Button variant="outline" size="sm" className="gap-2" disabled>
                            <Upload className="h-4 w-4" />
                            Update Progress
                          </Button>
                          <Button variant="outline" size="sm" className="gap-2" disabled>
                            <Users className="h-4 w-4" />
                            Investor Report
                          </Button>
                        </div>
                      </div>
                    </div>
                  </Card>
                  ))
                )}
              </TabsContent>

              {/* Funding Tab */}
              <TabsContent value="funding" className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Card className="bg-gradient-to-br from-primary to-primary/80 text-primary-foreground">
                    <CardContent className="p-6">
                      <DollarSign className="h-8 w-8 mb-3" />
                      <p className="text-sm opacity-90">Total Raised (All Time)</p>
                      <p className="text-3xl font-bold mt-1">{fmtMoney(totalRaised)}</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-card border-border">
                    <CardContent className="p-6">
                      <TrendingUp className="h-8 w-8 text-primary mb-3" />
                      <p className="text-sm text-muted-foreground">This Month</p>
                      <p className="text-3xl font-bold mt-1">
                        {fmtMoney(Number(funding?.funding_this_month ?? 0))}
                      </p>
                    </CardContent>
                  </Card>
                  <Card className="bg-card border-border">
                    <CardContent className="p-6">
                      <Target className="h-8 w-8 text-accent mb-3" />
                      <p className="text-sm text-muted-foreground">Active Funding Goals</p>
                      <p className="text-3xl font-bold mt-1">{fmtMoney(activeFundingGoals)}</p>
                    </CardContent>
                  </Card>
                </div>

                <Card className="bg-card border-border">
                  <CardHeader>
                    <CardTitle>Projects Currently Funding</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {projects.filter(p => p.status === "funding").map((project) => (
                      <div key={project.id} className="p-4 rounded-lg bg-muted/30 mb-4 last:mb-0">
                        <div className="flex items-center justify-between mb-3">
                          <div>
                            <h4 className="font-semibold">{project.name}</h4>
                            <p className="text-sm text-muted-foreground">{project.location}</p>
                          </div>
                          <Badge className="bg-primary">{project.fundingProgress}% Funded</Badge>
                        </div>
                        <Progress value={project.fundingProgress} className="h-3 mb-2" />
                        <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">
                            ${(project.totalRaised/1000000).toFixed(1)}M raised
                          </span>
                          <span className="font-medium">
                            ${(project.targetAmount/1000000).toFixed(1)}M target
                          </span>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </TabsContent>

              {/* Milestones Tab (Phase 15b) — real per-property milestones CRUD backed by
                  property_milestones. Developers add/edit/reorder; investors read them on the
                  property page. The construction % is computed from these milestones. */}
              <TabsContent value="milestones" className="space-y-6">
                <MilestonesManager
                  projects={projects.map((p) => ({ id: p.id, name: p.name }))}
                />
              </TabsContent>

              {/* Investors Tab — Total Investors + Avg. Investment are derived from real
                  project data; Repeat Investors has no backend (honest-disabled). */}
              <TabsContent value="investors" className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Card className="bg-card border-border">
                    <CardContent className="p-6 text-center">
                      <Users className="h-8 w-8 text-primary mx-auto mb-3" />
                      <p className="text-3xl font-bold">{totalInvestors.toLocaleString()}</p>
                      <p className="text-sm text-muted-foreground">Total Investors</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-card border-border">
                    <CardContent className="p-6 text-center">
                      <DollarSign className="h-8 w-8 text-accent mx-auto mb-3" />
                      <p className="text-3xl font-bold">
                        {avgInvestment !== null ? fmtMoney(avgInvestment) : "—"}
                      </p>
                      <p className="text-sm text-muted-foreground">Avg. Investment</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-card border-border">
                    <CardContent className="p-6 text-center">
                      <TrendingUp className="h-8 w-8 text-primary mx-auto mb-3" />
                      <p className="text-3xl font-bold">
                        {funding ? `${funding.repeat_investors.pct}%` : "—"}
                      </p>
                      <p className="text-sm text-muted-foreground">Repeat Investors</p>
                    </CardContent>
                  </Card>
                </div>

                {/* Investor Communications (Phase 15c) — real per-property updates that fan
                    out to net-holders via the Phase-12 notify()/email seam. Counts are real
                    (recipients + in-app reads); no open/click tracking. */}
                <InvestorCommunications
                  projects={projects.map((p) => ({ id: p.id, name: p.name }))}
                />
              </TabsContent>
            </Tabs>
          </div>
        </section>
      </main>
    </div>
  );
};

export default DeveloperDashboard;
