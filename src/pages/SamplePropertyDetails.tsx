import { Link, useParams, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ArrowLeft,
  MapPin,
  Building2,
  TrendingUp,
  Shield,
  FileText,
  Download,
  ChevronRight,
  Clock,
  CheckCircle,
  Wallet,
  AlertTriangle,
  Target,
  CalendarClock,
  Hammer,
  Handshake,
  Layers,
  Banknote,
  ArrowRight,
} from "lucide-react";
import { Loader2 } from "lucide-react";
import { propertyApi } from "@/lib/api";
import { toSampleProperty } from "@/lib/properties";


const toneClass =(tone: "low" | "medium" | "high" | "positive" | "neutral" | "negative") => {
  switch (tone) {
    case "low":
    case "positive":
      return "bg-success/10 text-success border-success/30";
    case "medium":
    case "neutral":
      return "bg-amber-500/10 text-amber-600 border-amber-500/30";
    case "high":
    case "negative":
      return "bg-destructive/10 text-destructive border-destructive/30";
  }
};

const SamplePropertyDetails = () => {
  const { slug } = useParams();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["property", slug],
    queryFn: () => propertyApi.get(slug as string),
    enabled: !!slug,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (isError || !data) return <Navigate to="/marketplace" replace />;

  const sample = toSampleProperty(data);

  return (
    <div className="min-h-screen bg-background">
      <main>
        {/* Breadcrumb */}
        <div className="bg-secondary/30 border-b border-border">
          <div className="container mx-auto px-4 py-4">
            <div className="flex items-center gap-2 text-sm">
              <Link to="/" className="text-muted-foreground hover:text-foreground">Home</Link>
              <ChevronRight size={14} className="text-muted-foreground" />
              <Link to="/marketplace" className="text-muted-foreground hover:text-foreground">Marketplace</Link>
              <ChevronRight size={14} className="text-muted-foreground" />
              <span className="text-foreground font-medium">{sample.title}</span>
            </div>
          </div>
        </div>

        <div className="container mx-auto px-4 py-8 space-y-8">
          <Link to="/marketplace" className="inline-flex items-center gap-2 text-muted-foreground hover:text-foreground">
            <ArrowLeft size={18} /> Back to Properties
          </Link>

          {/* Hero */}
          <div className="grid lg:grid-cols-3 gap-8">
            <div className="lg:col-span-2 space-y-6">
              <div className="rounded-2xl overflow-hidden border border-border">
                <img src={sample.image} alt={sample.title} className="w-full h-80 object-cover" />
              </div>

              <div>
                <div className="flex flex-wrap gap-2 mb-3">
                  <Badge className="bg-primary text-primary-foreground">Demo / Educational</Badge>
                  <Badge variant="outline">{sample.badge}</Badge>
                </div>
                <h1 className="text-3xl md:text-4xl font-bold text-foreground mb-2">{sample.title}</h1>
                <p className="text-lg text-muted-foreground mb-3">{sample.subtitle}</p>
                <div className="flex items-center gap-1 text-muted-foreground text-sm">
                  <MapPin size={14} /> <span>{sample.location}</span>
                </div>
              </div>

              {/* Overview */}
              <Card>
                <CardHeader>
                  <CardTitle>Property Overview</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-muted-foreground leading-relaxed">{sample.description}</p>
                </CardContent>
              </Card>

              {/* Ownership Structure & Investment Structure */}
              <div className="grid md:grid-cols-2 gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2"><Layers size={18} /> Ownership Structure</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {sample.ownershipStructure.map((r) => (
                      <div key={r.label} className="flex justify-between text-sm border-b border-border/50 pb-2 last:border-0">
                        <span className="text-muted-foreground">{r.label}</span>
                        <span className="font-medium text-foreground text-right">{r.value}</span>
                      </div>
                    ))}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2"><Wallet size={18} /> Investment Structure</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {sample.investmentStructure.map((r) => (
                      <div key={r.label} className="flex justify-between text-sm border-b border-border/50 pb-2 last:border-0">
                        <span className="text-muted-foreground">{r.label}</span>
                        <span className="font-medium text-foreground text-right">{r.value}</span>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </div>

              {/* Model-specific deep dive */}
              {sample.optionTerms && (
                <Card className="border-violet-500/30">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2"><Target size={18} /> Option Terms</CardTitle>
                  </CardHeader>
                  <CardContent className="grid sm:grid-cols-2 gap-4">
                    <Stat label="Option Premium" value={sample.optionTerms.optionPremium} />
                    <Stat label="Activation Deadline" value={sample.optionTerms.activationDeadline} />
                    <Stat label="Locked-in Strike" value={sample.optionTerms.lockedPrice} />
                    <Stat label="Future Value (proj.)" value={sample.optionTerms.futureValue} />
                  </CardContent>
                </Card>
              )}
              {sample.futureTerms && (
                <Card className="border-blue-500/30">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2"><CalendarClock size={18} /> Future Agreement</CardTitle>
                  </CardHeader>
                  <CardContent className="grid sm:grid-cols-2 gap-4">
                    <Stat label="Settlement Date" value={sample.futureTerms.settlementDate} />
                    <Stat label="Locked Future Price" value={sample.futureTerms.futurePrice} />
                    <Stat label="Appreciation Projection" value={sample.futureTerms.appreciationProjection} />
                    <Stat label="Construction Milestones" value={sample.futureTerms.constructionMilestoneImpact} />
                  </CardContent>
                </Card>
              )}
              {sample.installmentTerms && (
                <Card className="border-amber-500/30">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2"><Banknote size={18} /> Installment Plan</CardTitle>
                  </CardHeader>
                  <CardContent className="grid sm:grid-cols-2 gap-4">
                    <Stat label="Down Payment" value={sample.installmentTerms.downPayment} />
                    <Stat label="Term" value={`${sample.installmentTerms.months} months`} />
                    <Stat label="Monthly" value={sample.installmentTerms.monthly} />
                    <Stat label="Completion Unlock" value={sample.installmentTerms.completionUnlock} />
                  </CardContent>
                </Card>
              )}
              {sample.sharedTerms && (
                <Card className="border-fuchsia-500/30">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2"><Handshake size={18} /> Shared Development Terms</CardTitle>
                  </CardHeader>
                  <CardContent className="grid sm:grid-cols-2 gap-4">
                    <Stat label="Land Share" value={sample.sharedTerms.landShare} />
                    <Stat label="Construction Share" value={sample.sharedTerms.constructionShare} />
                    <Stat label="Profit Split" value={sample.sharedTerms.profitSplit} />
                    <Stat label="Governance" value={sample.sharedTerms.governance} />
                  </CardContent>
                </Card>
              )}
              {sample.portfolioHoldings && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2"><Building2 size={18} /> Portfolio Holdings</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {sample.portfolioHoldings.map((h) => (
                        <div key={h.name} className="flex items-center justify-between text-sm border-b border-border/50 pb-2 last:border-0">
                          <span className="text-foreground">{h.name}</span>
                          <div className="flex items-center gap-3">
                            <span className="text-muted-foreground">{h.weight}</span>
                            {h.yield && <Badge variant="outline" className="border-success/40 text-success">{h.yield}</Badge>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Timeline & milestones */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><Hammer size={18} /> Timeline & Construction Milestones</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {sample.timeline.map((m, i) => (
                      <div key={m.label} className="grid grid-cols-12 gap-3 items-center">
                        <div className="col-span-3 text-sm">
                          <div className="font-mono text-xs text-muted-foreground">{String(i + 1).padStart(2, "0")}</div>
                          <div className="font-medium text-foreground">{m.label}</div>
                          <div className="text-xs text-muted-foreground">{m.date}</div>
                        </div>
                        <div className="col-span-6">
                          <Progress value={m.progress} className="h-2" />
                        </div>
                        <div className="col-span-3 text-right text-sm">
                          <span className="text-muted-foreground">NAV idx </span>
                          <span className="font-semibold text-foreground">{m.valueIndex}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* ROI / Scenarios */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><TrendingUp size={18} /> ROI & Profit/Loss Scenarios</CardTitle>
                </CardHeader>
                <CardContent className="grid md:grid-cols-3 gap-3">
                  {sample.scenarios.map((s) => (
                    <div key={s.label} className={`rounded-xl border p-4 ${toneClass(s.tone)}`}>
                      <div className="text-xs uppercase tracking-wide opacity-80 mb-1">{s.label}</div>
                      <div className="text-sm font-medium">{s.outcome}</div>
                    </div>
                  ))}
                </CardContent>
              </Card>

              {/* Exit mechanisms */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><ArrowRight size={18} /> Exit Mechanisms</CardTitle>
                </CardHeader>
                <CardContent className="grid md:grid-cols-2 gap-3">
                  {sample.exitMechanisms.map((e) => (
                    <div key={e.name} className="border border-border rounded-xl p-4">
                      <div className="flex items-center justify-between mb-1">
                        <div className="font-semibold text-foreground">{e.name}</div>
                        <Badge variant="outline">{e.eta}</Badge>
                      </div>
                      <div className="text-sm text-muted-foreground">{e.description}</div>
                    </div>
                  ))}
                </CardContent>
              </Card>

              {/* Risks */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><AlertTriangle size={18} /> Risk Indicators</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {sample.risks.map((r) => (
                    <div key={r.label} className="flex items-center justify-between gap-3 border-b border-border/50 pb-2 last:border-0">
                      <div>
                        <div className="font-medium text-foreground">{r.label}</div>
                        <div className="text-sm text-muted-foreground">{r.note}</div>
                      </div>
                      <span className={`text-xs px-2 py-1 rounded-full border ${toneClass(r.level)}`}>
                        {r.level.toUpperCase()}
                      </span>
                    </div>
                  ))}
                </CardContent>
              </Card>

              {/* Documents */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><FileText size={18} /> Documents</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {sample.documents.map((d) => (
                    <div key={d.name} className="flex items-center justify-between border border-border rounded-lg p-3">
                      <div className="flex items-center gap-3">
                        <FileText size={18} className="text-muted-foreground" />
                        <div>
                          <div className="font-medium text-foreground">{d.name}</div>
                          <div className="text-xs text-muted-foreground">{d.type} · {d.size}</div>
                        </div>
                      </div>
                      <Button variant="outline" size="sm" disabled title="Document downloads are not available yet"><Download size={14} className="mr-2" /> Download</Button>
                    </div>
                  ))}
                </CardContent>
              </Card>

              {/* Market analysis */}
              <Card>
                <CardHeader>
                  <CardTitle>Market Analysis</CardTitle>
                </CardHeader>
                <CardContent className="grid sm:grid-cols-3 gap-4">
                  {sample.marketAnalysis.map((m) => (
                    <Stat key={m.label} label={m.label} value={m.value} />
                  ))}
                </CardContent>
              </Card>
            </div>

            {/* Sidebar */}
            <aside className="space-y-6">
              <Card className="sticky top-24">
                <CardHeader>
                  <CardTitle>Investment Snapshot</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <Stat label="Property Value" value={`$${sample.propertyValue.toLocaleString()}`} />
                  <Stat label="Min. Investment" value={`$${sample.minInvestment}`} />
                  {sample.expectedYield !== undefined && sample.expectedYield > 0 && (
                    <Stat label="Expected Yield" value={`${sample.expectedYield}%`} highlight />
                  )}
                  {sample.capitalAppreciation !== undefined && (
                    <Stat label="Capital Appreciation" value={`${sample.capitalAppreciation}%`} />
                  )}
                  {sample.totalReturn !== undefined && (
                    <Stat label="Total Return" value={`${sample.totalReturn}%`} highlight />
                  )}
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-muted-foreground">Funding</span>
                      <span className="font-medium">{sample.fundingProgress}%</span>
                    </div>
                    <Progress value={sample.fundingProgress} className="h-2" />
                  </div>
                  <Button className="w-full" size="lg" asChild>
                    <Link to={`/property/${slug}`}>Invest in this Sample</Link>
                  </Button>
                  <Button variant="outline" asChild className="w-full">
                    <Link to="/property-types">Learn Model</Link>
                  </Button>
                  <div className="flex items-start gap-2 text-xs text-muted-foreground bg-secondary/40 rounded-lg p-3">
                    <Shield size={14} className="mt-0.5 flex-shrink-0" />
                    <span>This is an educational demo opportunity. Numbers shown illustrate how the model works on the platform.</span>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>Developer</CardTitle></CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <div className="font-semibold text-foreground">{sample.developer.name}</div>
                  <div className="flex items-center gap-3 text-muted-foreground">
                    <span>★ {sample.developer.rating}</span>
                    <span>{sample.developer.projectsCompleted} projects</span>
                  </div>
                </CardContent>
              </Card>
            </aside>
          </div>
        </div>
      </main>
    </div>
  );
};

const Stat = ({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) => (
  <div>
    <div className="text-xs text-muted-foreground mb-1">{label}</div>
    <div className={`text-sm font-semibold ${highlight ? "text-success" : "text-foreground"}`}>{value}</div>
  </div>
);

export default SamplePropertyDetails;
