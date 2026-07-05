import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { 
  ArrowLeft, 
  MapPin, 
  Building2, 
  TrendingUp, 
  Calendar,
  Users,
  Shield,
  FileText,
  Download,
  ChevronRight,
  Clock,
  CheckCircle,
  Info,
  Wallet,
  CreditCard,
  Coins,
  ArrowRight,
  Star,
  Bed,
  Bath,
  Maximize,
  Car
} from "lucide-react";
import PropertyGallery from "@/components/property/PropertyGallery";
import InvestmentCalculator from "@/components/property/InvestmentCalculator";
import InstallmentCalculator from "@/components/property/InstallmentCalculator";
import PropertyDocuments from "@/components/property/PropertyDocuments";
import PropertyTimeline from "@/components/property/PropertyTimeline";
import { ExitButton } from "@/components/exit/ExitButton";
import { Loader2 } from "lucide-react";
import { propertyApi, type PropertyDetail } from "@/lib/api";

const READY_MODELS = new Set(["ready-income", "ready-portfolio"]);
const DEFAULT_DEV_LOGO =
  "https://images.unsplash.com/photo-1560179707-f14e90ef3623?w=100&auto=format&fit=crop&q=80";

// Build the view-model the page renders from a live PropertyDetail. Rich fields
// not held as columns live in `content`; everything degrades gracefully when a
// freshly created (owner) listing hasn't supplied them yet.
type Dict = Record<string, unknown>;
const asObj = (v: unknown): Dict => (v && typeof v === "object" ? (v as Dict) : {});
const asNum = (v: unknown): number | null => (typeof v === "number" ? v : null);
const asStr = (v: unknown): string => (typeof v === "string" ? v : "");

const toViewModel = (d: PropertyDetail) => {
  const c = asObj(d.content);
  const details = asObj(c.details);
  const spv = asObj(c.spv);
  const dev = asObj(c.developer);
  const fees = asObj(d.fees);
  const cFees = asObj(c.fees);
  const isReady = READY_MODELS.has(d.model);
  return {
    id: d.id,
    title: d.title,
    subtitle: d.subtitle ?? "",
    location: d.location,
    status: d.status === "funded" ? "funded" : "open",
    type: isReady ? "ready" : "under_construction",
    images: d.images?.length ? d.images : d.image ? [d.image] : [],
    bedrooms: asNum(details.bedrooms),
    bathrooms: asNum(details.bathrooms),
    area: asNum(details.area),
    parking: asNum(details.parking),
    propertyValue: d.total_value,
    minInvestment: d.minimum_investment,
    maxInvestment: asNum(details.maxInvestment) ?? d.total_value,
    expectedYield: d.expected_yield ?? d.target_yield ?? 0,
    capitalAppreciation: d.capital_appreciation ?? 0,
    totalReturn: d.total_return ?? 0,
    fundingProgress: Math.round(d.funding_progress),
    fundingGoal: d.total_value,
    fundedAmount: d.funded_amount,
    investorsCount: d.investors_count,
    daysLeft: 0,
    // Phase 15b — real, computed construction % (falls back to the legacy blob if absent).
    constructionProgress: d.construction_progress ?? asNum(c.constructionProgress) ?? 0,
    milestones: d.milestones ?? [],
    expectedCompletion: d.expected_completion ?? asStr(c.expectedCompletion),
    spv: {
      name: d.spv_name ?? asStr(spv.name),
      jurisdiction: asStr(spv.jurisdiction),
      registrationNumber: d.spv_registration ?? asStr(spv.registrationNumber),
      trustee: asStr(spv.trustee),
      auditor: asStr(spv.auditor),
    },
    developer: {
      name: asStr(dev.name) || d.developer_name || "—",
      logo: asStr(dev.logo) || DEFAULT_DEV_LOGO,
      projectsCompleted: asNum(dev.projectsCompleted) ?? 0,
      rating: asNum(dev.rating) ?? 0,
    },
    description: d.description ?? "",
    amenities: (Array.isArray(details.amenities) ? details.amenities : []) as string[],
    fees: {
      platformFee: asNum(fees.platform_fee) ?? 2.0,
      managementFee: asNum(fees.management_fee) ?? 1.5,
      installmentFee: asNum(fees.installment_fee) ?? 4.0,
      performanceFee: asNum(cFees.performance) ?? 10.0,
      exitFee: asNum(cFees.exit) ?? 1.0,
    },
  };
};

const PropertyDetails = () => {
  const { id } = useParams();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["property", id],
    queryFn: () => propertyApi.get(id as string),
    enabled: !!id,
  });

  const propertyData = data ? toViewModel(data) : null;
  const [investmentAmount, setInvestmentAmount] = useState(0);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (isError || !propertyData) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4 text-center px-4">
        <h1 className="text-2xl font-bold text-foreground">Property not found</h1>
        <p className="text-muted-foreground">
          This listing may have been removed or is not yet live.
        </p>
        <Link to="/marketplace">
          <Button>Back to Marketplace</Button>
        </Link>
      </div>
    );
  }

  const hasFeatures =
    propertyData.bedrooms != null ||
    propertyData.bathrooms != null ||
    propertyData.area != null ||
    propertyData.parking != null;

  const getStatusBadge = () => {
    const status = propertyData.status;
    if (status === "open") {
      return <Badge className="bg-success text-success-foreground">Open for Investment</Badge>;
    } else if (status === "funding") {
      return <Badge className="bg-warning text-warning-foreground">Funding Soon</Badge>;
    } else {
      return <Badge variant="secondary">Fully Funded</Badge>;
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <main>
        {/* Breadcrumb */}
        <div className="bg-secondary/30 border-b border-border">
          <div className="container mx-auto px-4 py-4">
            <div className="flex items-center gap-2 text-sm">
              <Link to="/" className="text-muted-foreground hover:text-foreground transition-colors">
                Home
              </Link>
              <ChevronRight size={14} className="text-muted-foreground" />
              <Link to="/marketplace" className="text-muted-foreground hover:text-foreground transition-colors">
                Marketplace
              </Link>
              <ChevronRight size={14} className="text-muted-foreground" />
              <span className="text-foreground font-medium">{propertyData.title}</span>
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="container mx-auto px-4 py-8">
          {/* Back Button */}
          <Link 
            to="/marketplace" 
            className="inline-flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors mb-6"
          >
            <ArrowLeft size={18} />
            <span>Back to Properties</span>
          </Link>

          <div className="grid lg:grid-cols-3 gap-8">
            {/* Left Column - Property Info */}
            <div className="lg:col-span-2 space-y-8">
              {/* Gallery */}
              <PropertyGallery images={propertyData.images} title={propertyData.title} />

              {/* Property Header */}
              <div>
                <div className="flex flex-wrap items-center gap-3 mb-3">
                  {getStatusBadge()}
                  {propertyData.type === "ready" ? (
                    <Badge variant="outline" className="border-success text-success">
                      <CheckCircle size={12} className="mr-1" />
                      Ready Property
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="border-warning text-warning">
                      <Clock size={12} className="mr-1" />
                      Under Construction
                    </Badge>
                  )}
                </div>
                
                <h1 className="text-3xl md:text-4xl font-bold text-foreground mb-2">
                  {propertyData.title}
                </h1>
                <p className="text-lg text-muted-foreground mb-4">{propertyData.subtitle}</p>
                
                <div className="flex items-center gap-2 text-muted-foreground">
                  <MapPin size={18} />
                  <span>{propertyData.location}</span>
                </div>
              </div>

              {/* Property Features */}
              {hasFeatures && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  {[
                    { icon: Bed, label: "Bedrooms", value: propertyData.bedrooms },
                    { icon: Bath, label: "Bathrooms", value: propertyData.bathrooms },
                    { icon: Maximize, label: "Area", value: propertyData.area ? `${propertyData.area} sq ft` : null },
                    { icon: Car, label: "Parking", value: propertyData.parking },
                  ]
                    .filter((f) => f.value != null)
                    .map((feature, index) => (
                      <div key={index} className="bg-card rounded-xl p-4 border border-border text-center">
                        <feature.icon size={24} className="text-primary mx-auto mb-2" />
                        <div className="text-sm text-muted-foreground">{feature.label}</div>
                        <div className="font-semibold text-foreground">{feature.value}</div>
                      </div>
                    ))}
                </div>
              )}

              {/* Tabs */}
              <Tabs defaultValue="overview" className="w-full">
                <TabsList className="w-full justify-start bg-secondary/50 p-1 rounded-xl">
                  <TabsTrigger value="overview" className="rounded-lg">Overview</TabsTrigger>
                  <TabsTrigger value="financials" className="rounded-lg">Financials</TabsTrigger>
                  <TabsTrigger value="structure" className="rounded-lg">SPV Structure</TabsTrigger>
                  <TabsTrigger value="documents" className="rounded-lg">Documents</TabsTrigger>
                  <TabsTrigger value="timeline" className="rounded-lg">Timeline</TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="mt-6 space-y-6">
                  {/* Description */}
                  <div>
                    <h3 className="text-xl font-semibold text-foreground mb-4">Property Description</h3>
                    <div className="prose prose-sm text-muted-foreground max-w-none whitespace-pre-line">
                      {propertyData.description}
                    </div>
                  </div>

                  {/* Amenities */}
                  {propertyData.amenities.length > 0 && (
                  <div>
                    <h3 className="text-xl font-semibold text-foreground mb-4">Amenities</h3>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      {propertyData.amenities.map((amenity, index) => (
                        <div 
                          key={index} 
                          className="flex items-center gap-2 bg-secondary/50 rounded-lg px-4 py-3"
                        >
                          <CheckCircle size={16} className="text-primary flex-shrink-0" />
                          <span className="text-sm text-foreground">{amenity}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  )}

                  {/* Developer */}
                  <div className="bg-card rounded-2xl p-6 border border-border">
                    <h3 className="text-xl font-semibold text-foreground mb-4">Developer</h3>
                    <div className="flex items-center gap-4">
                      <img 
                        src={propertyData.developer.logo} 
                        alt={propertyData.developer.name}
                        className="w-16 h-16 rounded-xl object-cover"
                      />
                      <div className="flex-1">
                        <h4 className="font-semibold text-foreground">{propertyData.developer.name}</h4>
                        <div className="flex items-center gap-4 mt-1 text-sm text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <Star size={14} className="text-warning fill-warning" />
                            {propertyData.developer.rating}
                          </span>
                          <span>{propertyData.developer.projectsCompleted} projects completed</span>
                        </div>
                      </div>
                      <Button variant="outline" size="sm" disabled title="Developer profiles are not available yet">View Profile</Button>
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="financials" className="mt-6 space-y-6">
                  {/* Key Metrics */}
                  <div className="grid sm:grid-cols-3 gap-4">
                    <div className="bg-gradient-hero rounded-2xl p-6 text-primary-foreground">
                      <TrendingUp size={24} className="mb-3" />
                      <div className="text-3xl font-bold mb-1">{propertyData.expectedYield}%</div>
                      <div className="text-primary-foreground/80">Expected Rental Yield</div>
                    </div>
                    <div className="bg-card rounded-2xl p-6 border border-border">
                      <Building2 size={24} className="text-primary mb-3" />
                      <div className="text-3xl font-bold text-foreground mb-1">{propertyData.capitalAppreciation}%</div>
                      <div className="text-muted-foreground">Est. Capital Appreciation</div>
                    </div>
                    <div className="bg-card rounded-2xl p-6 border border-border">
                      <Wallet size={24} className="text-accent mb-3" />
                      <div className="text-3xl font-bold text-foreground mb-1">{propertyData.totalReturn}%</div>
                      <div className="text-muted-foreground">Total Expected Return</div>
                    </div>
                  </div>

                  {/* Investment Details */}
                  <div className="bg-card rounded-2xl p-6 border border-border">
                    <h3 className="text-xl font-semibold text-foreground mb-4">Investment Details</h3>
                    <div className="grid sm:grid-cols-2 gap-4">
                      {[
                        { label: "Property Value", value: `$${propertyData.propertyValue.toLocaleString()}` },
                        { label: "Minimum Investment", value: `$${propertyData.minInvestment}` },
                        { label: "Maximum Investment", value: `$${propertyData.maxInvestment.toLocaleString()}` },
                        { label: "Distribution Frequency", value: "Quarterly" },
                        { label: "Investment Term", value: "5 Years" },
                        { label: "Exit Options", value: "Secondary Market (after 6 months)" },
                      ].map((item, index) => (
                        <div key={index} className="flex justify-between py-3 border-b border-border last:border-0">
                          <span className="text-muted-foreground">{item.label}</span>
                          <span className="font-medium text-foreground">{item.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Fees */}
                  <div className="bg-card rounded-2xl p-6 border border-border">
                    <div className="flex items-center gap-2 mb-4">
                      <h3 className="text-xl font-semibold text-foreground">Fee Structure</h3>
                      <Info size={16} className="text-muted-foreground" />
                    </div>
                    <div className="space-y-3">
                      {[
                        { label: "Platform Fee", value: `${propertyData.fees.platformFee}%`, note: "One-time" },
                        { label: "Management Fee", value: `${propertyData.fees.managementFee}%`, note: "Annual" },
                        { label: "Performance Fee", value: `${propertyData.fees.performanceFee}%`, note: "On profits above 8%" },
                        { label: "Exit Fee", value: `${propertyData.fees.exitFee}%`, note: "On secondary sales" },
                      ].map((fee, index) => (
                        <div key={index} className="flex items-center justify-between py-2">
                          <div>
                            <span className="text-foreground">{fee.label}</span>
                            <span className="text-sm text-muted-foreground ml-2">({fee.note})</span>
                          </div>
                          <span className="font-semibold text-foreground">{fee.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="structure" className="mt-6 space-y-6">
                  <div className="bg-card rounded-2xl p-6 border border-border">
                    <div className="flex items-center gap-3 mb-6">
                      <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center">
                        <Shield size={24} className="text-primary" />
                      </div>
                      <div>
                        <h3 className="text-xl font-semibold text-foreground">SPV Structure</h3>
                        <p className="text-sm text-muted-foreground">Special Purpose Vehicle protecting your investment</p>
                      </div>
                    </div>

                    <div className="space-y-4">
                      {[
                        { label: "SPV Name", value: propertyData.spv.name },
                        { label: "Jurisdiction", value: propertyData.spv.jurisdiction },
                        { label: "Registration Number", value: propertyData.spv.registrationNumber },
                        { label: "Trustee", value: propertyData.spv.trustee },
                        { label: "Auditor", value: propertyData.spv.auditor },
                      ]
                        .filter((item) => item.value)
                        .map((item, index) => (
                        <div key={index} className="flex justify-between py-3 border-b border-border last:border-0">
                          <span className="text-muted-foreground">{item.label}</span>
                          <span className="font-medium text-foreground">{item.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* SPV Benefits */}
                  <div className="grid sm:grid-cols-2 gap-4">
                    {[
                      {
                        icon: Shield,
                        title: "Asset Protection",
                        description: "Your investment is legally separated from platform operations"
                      },
                      {
                        icon: FileText,
                        title: "Clear Ownership",
                        description: "Digital shares represent direct ownership in the property SPV"
                      },
                      {
                        icon: Users,
                        title: "Governance Rights",
                        description: "Participate in major decisions affecting the property"
                      },
                      {
                        icon: TrendingUp,
                        title: "Tradeable Shares",
                        description: "Sell your shares on the secondary market after 6 months"
                      },
                    ].map((benefit, index) => (
                      <div key={index} className="bg-secondary/50 rounded-xl p-4">
                        <benefit.icon size={20} className="text-primary mb-3" />
                        <h4 className="font-semibold text-foreground mb-1">{benefit.title}</h4>
                        <p className="text-sm text-muted-foreground">{benefit.description}</p>
                      </div>
                    ))}
                  </div>

                  {/* Link to full SPV page */}
                  <div className="text-center pt-4">
                    <Link to={`/spv-model/${id || '1'}`}>
                      <Button variant="outline" className="gap-2">
                        <Info size={16} />
                        View Full SPV Details
                        <ChevronRight size={16} />
                      </Button>
                    </Link>
                  </div>
                </TabsContent>

                <TabsContent value="documents" className="mt-6">
                  <PropertyDocuments propertyId={propertyData.id} />
                </TabsContent>

                <TabsContent value="timeline" className="mt-6">
                  <PropertyTimeline milestones={propertyData.milestones} />
                </TabsContent>
              </Tabs>
            </div>

            {/* Right Column - Investment Card */}
            <div className="lg:col-span-1">
              <div className="sticky top-24 space-y-4">
                {propertyData.type === "under_construction" ? (
                  <InstallmentCalculator
                    propertyId={propertyData.id}
                    propertyData={propertyData}
                    investmentAmount={investmentAmount || propertyData.minInvestment}
                    setInvestmentAmount={setInvestmentAmount}
                    propertyTitle={propertyData.title}
                  />
                ) : (
                  <InvestmentCalculator
                    propertyId={propertyData.id}
                    propertyData={propertyData}
                    investmentAmount={investmentAmount || propertyData.minInvestment}
                    setInvestmentAmount={setInvestmentAmount}
                  />
                )}

                <div className="rounded-xl border bg-card p-4">
                  <div className="text-sm font-semibold mb-1">Already own units in this property?</div>
                  <p className="text-xs text-muted-foreground mb-3">
                    Exit via the secondary market or through a liquidity provider — fully tracked in your dashboard.
                  </p>
                  <ExitButton
                    variant="outline"
                    className="w-full"
                    label="Exit Ownership Position"
                    initialPositionId={propertyData.id}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default PropertyDetails;
