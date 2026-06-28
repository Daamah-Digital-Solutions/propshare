import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Shield,
  Building2,
  Users,
  TrendingUp,
  FileText,
  Download,
  CheckCircle2,
  ArrowRight,
  Scale,
  PiggyBank,
  Clock,
  ArrowLeftRight,
  Landmark,
  BarChart3,
  Eye,
  Wallet,
  Calendar,
  Lock,
  Globe,
  ChevronRight,
} from "lucide-react";

interface SPVData {
  id: string;
  spvName: string;
  jurisdiction: string;
  propertyTitle: string;
  propertyId: string;
  assetValue: number;
  totalUnits: number;
  unitPrice: number;
  investorParticipation: number;
  projectDuration: string;
  exitRules: string;
  status: string;
}

// Mock SPV data - in production this would come from the database
const mockSPVs: SPVData[] = [
  {
    id: "1",
    spvName: "Capimax Marina SPV Ltd",
    jurisdiction: "British Virgin Islands",
    propertyTitle: "Marina Bay Residences",
    propertyId: "1",
    assetValue: 2500000,
    totalUnits: 100,
    unitPrice: 25000,
    investorParticipation: 75,
    projectDuration: "5 Years",
    exitRules: "Secondary market trading available after 6 months",
    status: "active",
  },
  {
    id: "2",
    spvName: "Capimax Downtown SPV Ltd",
    jurisdiction: "Cayman Islands",
    propertyTitle: "Downtown Commercial Tower",
    propertyId: "2",
    assetValue: 5000000,
    totalUnits: 200,
    unitPrice: 25000,
    investorParticipation: 60,
    projectDuration: "7 Years",
    exitRules: "Exit available after 12-month lock-in period",
    status: "active",
  },
  {
    id: "3",
    spvName: "Capimax Beach SPV Ltd",
    jurisdiction: "Delaware, USA",
    propertyTitle: "Beachfront Villa Collection",
    propertyId: "3",
    assetValue: 3500000,
    totalUnits: 140,
    unitPrice: 25000,
    investorParticipation: 85,
    projectDuration: "4 Years",
    exitRules: "Flexible exit via secondary market",
    status: "funded",
  },
];

const documents = [
  { title: "SPV Incorporation Documents", type: "legal", icon: FileText },
  { title: "Property Ownership Documents", type: "ownership", icon: Building2 },
  { title: "Financial Reports", type: "financial", icon: BarChart3 },
  { title: "Valuation Reports", type: "valuation", icon: TrendingUp },
];

const investorBenefits = [
  {
    title: "Asset Isolation",
    description: "Risk is limited to one property per SPV. Your investment is legally protected from other projects.",
    icon: Shield,
  },
  {
    title: "Clear Ownership Structure",
    description: "Digital shares represent direct ownership in the property SPV, fully transparent and verifiable.",
    icon: FileText,
  },
  {
    title: "Transparent Cash Flow",
    description: "All rental income and returns flow through the SPV with complete visibility in your dashboard.",
    icon: Eye,
  },
  {
    title: "Easier Exit",
    description: "Trade your shares on the secondary market after the lock-in period for liquidity when you need it.",
    icon: ArrowLeftRight,
  },
];

const developerBenefits = [
  {
    title: "Structured Fundraising",
    description: "Access capital from multiple investors through a regulated and organized structure.",
    icon: Landmark,
  },
  {
    title: "Clear Investor Relations",
    description: "Manage investor communications and distributions through a single legal entity.",
    icon: Users,
  },
  {
    title: "Simplified Reporting",
    description: "Consolidated reporting and distribution management for all stakeholders.",
    icon: BarChart3,
  },
];

const SPVModel = () => {
  const { propertyId } = useParams();
  const [selectedSPV, setSelectedSPV] = useState<SPVData | null>(null);

  useEffect(() => {
    if (propertyId) {
      const spv = mockSPVs.find((s) => s.propertyId === propertyId);
      setSelectedSPV(spv || null);
    }
  }, [propertyId]);

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Hero Section */}
      <section className="bg-gradient-to-br from-primary/10 via-background to-accent/5 py-16 border-b border-border">
        <div className="container mx-auto px-4 text-center">
          <Badge className="bg-primary text-primary-foreground mb-4">
            SPV Structure
          </Badge>
          <h1 className="text-4xl md:text-5xl font-bold text-foreground mb-4">
            SPV Structure & <span className="text-primary">Details</span>
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Learn how each property is owned and managed through a Special Purpose Vehicle (SPV) 
            to protect investors, ensure transparency, and separate assets and liabilities.
          </p>
        </div>
      </section>

      {/* What is an SPV */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <div>
              <Badge variant="outline" className="mb-4">
                Understanding SPV
              </Badge>
              <h2 className="text-3xl font-bold text-foreground mb-4">
                What is an SPV?
              </h2>
              <p className="text-muted-foreground mb-6">
                A Special Purpose Vehicle (SPV) is a legally independent company created solely 
                to own and manage a specific property or project. Each property on the Capimax PropShare 
                platform is linked to its own SPV, ensuring complete asset isolation and investor protection.
              </p>
              <ul className="space-y-3">
                {[
                  "Legally separate from the platform",
                  "Single-purpose entity for one property",
                  "Provides liability protection for investors",
                  "Enables fractional ownership structure",
                ].map((item, index) => (
                  <li key={index} className="flex items-start gap-3">
                    <CheckCircle2 className="h-5 w-5 text-primary flex-shrink-0 mt-0.5" />
                    <span className="text-foreground">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="bg-card rounded-2xl border border-border p-8">
              <div className="flex flex-col items-center space-y-4">
                <div className="h-20 w-20 rounded-full bg-primary/10 flex items-center justify-center">
                  <Shield className="h-10 w-10 text-primary" />
                </div>
                <h3 className="text-xl font-semibold text-foreground">
                  Legal Protection
                </h3>
                <p className="text-center text-muted-foreground">
                  Each SPV operates independently, meaning issues with one property 
                  don't affect your other investments.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* SPV Structure */}
      <section className="py-16 bg-secondary/30">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <Badge variant="outline" className="mb-4">
              Structure
            </Badge>
            <h2 className="text-3xl font-bold text-foreground mb-4">
              SPV Structure
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              Understand how the SPV structure creates a clear separation between 
              the platform, the property, and investors.
            </p>
          </div>

          <div className="flex flex-col md:flex-row items-center justify-center gap-4 md:gap-8 max-w-4xl mx-auto">
            <Card className="flex-1 text-center">
              <CardContent className="p-6">
                <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
                  <Users className="h-8 w-8 text-primary" />
                </div>
                <h3 className="font-semibold text-foreground mb-2">Investors</h3>
                <p className="text-sm text-muted-foreground">
                  Own economic interests through investment units
                </p>
              </CardContent>
            </Card>

            <ChevronRight className="h-8 w-8 text-muted-foreground rotate-90 md:rotate-0" />

            <Card className="flex-1 text-center border-primary/50 bg-primary/5">
              <CardContent className="p-6">
                <div className="h-16 w-16 rounded-full bg-primary/20 flex items-center justify-center mx-auto mb-4">
                  <Shield className="h-8 w-8 text-primary" />
                </div>
                <h3 className="font-semibold text-foreground mb-2">SPV Entity</h3>
                <p className="text-sm text-muted-foreground">
                  Legal owner of the property
                </p>
              </CardContent>
            </Card>

            <ChevronRight className="h-8 w-8 text-muted-foreground rotate-90 md:rotate-0" />

            <Card className="flex-1 text-center">
              <CardContent className="p-6">
                <div className="h-16 w-16 rounded-full bg-accent/10 flex items-center justify-center mx-auto mb-4">
                  <Building2 className="h-8 w-8 text-accent" />
                </div>
                <h3 className="font-semibold text-foreground mb-2">Property</h3>
                <p className="text-sm text-muted-foreground">
                  Real estate asset held by the SPV
                </p>
              </CardContent>
            </Card>
          </div>

          <div className="mt-8 text-center">
            <p className="text-sm text-muted-foreground max-w-xl mx-auto">
              <strong>Note:</strong> The platform (Capimax PropShare) acts as a digital marketplace 
              and management layer only. It does not own the properties or the SPVs.
            </p>
          </div>
        </div>
      </section>

      {/* Key SPV Details */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <Badge variant="outline" className="mb-4">
              SPV Directory
            </Badge>
            <h2 className="text-3xl font-bold text-foreground mb-4">
              Key SPV Details
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              View detailed information for each SPV linked to properties on the platform.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {mockSPVs.map((spv) => (
              <Card
                key={spv.id}
                className={`cursor-pointer transition-all hover:shadow-lg ${
                  selectedSPV?.id === spv.id ? "ring-2 ring-primary" : ""
                }`}
                onClick={() => setSelectedSPV(spv)}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <Badge
                      variant={spv.status === "active" ? "default" : "secondary"}
                    >
                      {spv.status}
                    </Badge>
                    <Globe className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <CardTitle className="text-lg">{spv.spvName}</CardTitle>
                  <p className="text-sm text-muted-foreground">
                    {spv.jurisdiction}
                  </p>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Property</span>
                      <Link
                        to={`/property/${spv.propertyId}`}
                        className="text-primary hover:underline font-medium"
                      >
                        {spv.propertyTitle}
                      </Link>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Asset Value</span>
                      <span className="font-medium">
                        {formatCurrency(spv.assetValue)}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Total Units</span>
                      <span className="font-medium">{spv.totalUnits}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Unit Price</span>
                      <span className="font-medium">
                        {formatCurrency(spv.unitPrice)}
                      </span>
                    </div>
                    <Separator />
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">
                        Investor Participation
                      </span>
                      <span className="font-medium text-primary">
                        {spv.investorParticipation}%
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Duration</span>
                      <span className="font-medium">{spv.projectDuration}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* SPV Benefits */}
      <section className="py-16 bg-gradient-to-r from-primary/5 to-accent/5">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <Badge variant="outline" className="mb-4">
              Benefits
            </Badge>
            <h2 className="text-3xl font-bold text-foreground mb-4">
              SPV Benefits
            </h2>
          </div>

          <div className="grid md:grid-cols-2 gap-12">
            {/* Investor Benefits */}
            <div>
              <h3 className="text-xl font-semibold text-foreground mb-6 flex items-center gap-2">
                <Users className="h-5 w-5 text-primary" />
                For Investors
              </h3>
              <div className="space-y-4">
                {investorBenefits.map((benefit, index) => (
                  <Card key={index}>
                    <CardContent className="p-4 flex items-start gap-4">
                      <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                        <benefit.icon className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <h4 className="font-medium text-foreground">
                          {benefit.title}
                        </h4>
                        <p className="text-sm text-muted-foreground">
                          {benefit.description}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>

            {/* Developer Benefits */}
            <div>
              <h3 className="text-xl font-semibold text-foreground mb-6 flex items-center gap-2">
                <Building2 className="h-5 w-5 text-accent" />
                For Property Owners / Developers
              </h3>
              <div className="space-y-4">
                {developerBenefits.map((benefit, index) => (
                  <Card key={index}>
                    <CardContent className="p-4 flex items-start gap-4">
                      <div className="h-10 w-10 rounded-lg bg-accent/10 flex items-center justify-center flex-shrink-0">
                        <benefit.icon className="h-5 w-5 text-accent" />
                      </div>
                      <div>
                        <h4 className="font-medium text-foreground">
                          {benefit.title}
                        </h4>
                        <p className="text-sm text-muted-foreground">
                          {benefit.description}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Governance & Transparency */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <Badge variant="outline" className="mb-4">
              Governance
            </Badge>
            <h2 className="text-3xl font-bold text-foreground mb-4">
              Governance & Transparency
            </h2>
          </div>

          <div className="grid md:grid-cols-4 gap-6">
            {[
              {
                icon: BarChart3,
                title: "Separate Accounting",
                description: "Each SPV maintains its own books and financial records",
              },
              {
                icon: FileText,
                title: "Periodic Reports",
                description: "Quarterly financial reports for all investors",
              },
              {
                icon: TrendingUp,
                title: "Asset Tracking",
                description: "Real-time performance monitoring for each property",
              },
              {
                icon: Eye,
                title: "Full Transparency",
                description: "All documents accessible inside the platform",
              },
            ].map((item, index) => (
              <Card key={index}>
                <CardContent className="p-6 text-center">
                  <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
                    <item.icon className="h-6 w-6 text-primary" />
                  </div>
                  <h3 className="font-semibold text-foreground mb-2">
                    {item.title}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {item.description}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Cash Flow & Returns */}
      <section className="py-16 bg-secondary/30">
        <div className="container mx-auto px-4">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <div>
              <Badge variant="outline" className="mb-4">
                Returns
              </Badge>
              <h2 className="text-3xl font-bold text-foreground mb-4">
                Cash Flow & Returns
              </h2>
              <p className="text-muted-foreground mb-6">
                Understand how returns flow from the property to your wallet through 
                the SPV structure.
              </p>
              <ul className="space-y-4">
                {[
                  {
                    icon: Building2,
                    text: "Rental income or project returns flow into the SPV",
                  },
                  {
                    icon: Scale,
                    text: "Operating expenses and management fees are deducted",
                  },
                  {
                    icon: PiggyBank,
                    text: "Net returns distributed to investors proportionally",
                  },
                  {
                    icon: Wallet,
                    text: "All distributions visible in investor dashboard",
                  },
                ].map((item, index) => (
                  <li key={index} className="flex items-start gap-3">
                    <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <item.icon className="h-4 w-4 text-primary" />
                    </div>
                    <span className="text-foreground mt-1">{item.text}</span>
                  </li>
                ))}
              </ul>
            </div>
            <Card className="bg-card">
              <CardContent className="p-8">
                <h3 className="text-lg font-semibold text-foreground mb-6 text-center">
                  Return Distribution Flow
                </h3>
                <div className="space-y-4">
                  {[
                    { label: "Gross Rental Income", value: "$12,500/month", color: "bg-primary" },
                    { label: "Operating Expenses", value: "-$2,000/month", color: "bg-destructive" },
                    { label: "Management Fee (1%)", value: "-$125/month", color: "bg-muted" },
                    { label: "Platform Fee (2.5%)", value: "-$312/month", color: "bg-muted" },
                  ].map((item, index) => (
                    <div key={index} className="flex justify-between items-center">
                      <span className="text-sm text-muted-foreground">{item.label}</span>
                      <Badge variant="outline" className={item.value.startsWith("-") ? "text-destructive" : ""}>
                        {item.value}
                      </Badge>
                    </div>
                  ))}
                  <Separator />
                  <div className="flex justify-between items-center">
                    <span className="font-semibold text-foreground">Net Distributable</span>
                    <Badge className="bg-primary text-primary-foreground">$10,063/month</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Exit Mechanism */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <Badge variant="outline" className="mb-4">
              Exit Options
            </Badge>
            <h2 className="text-3xl font-bold text-foreground mb-4">
              Exit Mechanism
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              Flexibility to exit your investment through multiple channels.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-6 max-w-4xl mx-auto">
            <Card>
              <CardContent className="p-6 text-center">
                <div className="h-14 w-14 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
                  <ArrowLeftRight className="h-7 w-7 text-primary" />
                </div>
                <h3 className="font-semibold text-foreground mb-2">
                  Secondary Market
                </h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Trade your shares on our secondary market after the lock-in period
                </p>
                <Link to="/secondary-market">
                  <Button variant="outline" size="sm" className="gap-2">
                    View Market
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6 text-center">
                <div className="h-14 w-14 rounded-full bg-accent/10 flex items-center justify-center mx-auto mb-4">
                  <Clock className="h-7 w-7 text-accent" />
                </div>
                <h3 className="font-semibold text-foreground mb-2">
                  Defined Timelines
                </h3>
                <p className="text-sm text-muted-foreground">
                  Exit timelines are clearly defined per SPV. Ready properties: 6 months. 
                  Under-construction: varies by project.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6 text-center">
                <div className="h-14 w-14 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
                  <Lock className="h-7 w-7 text-primary" />
                </div>
                <h3 className="font-semibold text-foreground mb-2">
                  Lock-in Periods
                </h3>
                <p className="text-sm text-muted-foreground">
                  Installment projects allow exit after the defined lock-in period 
                  based on project milestones.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Documents Section */}
      <section className="py-16 bg-secondary/30">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <Badge variant="outline" className="mb-4">
              Documentation
            </Badge>
            <h2 className="text-3xl font-bold text-foreground mb-4">
              SPV Documents
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              Access and download all relevant SPV documents for your investments.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-5xl mx-auto">
            {documents.map((doc, index) => (
              <Card key={index} className="hover:shadow-lg transition-shadow">
                <CardContent className="p-6">
                  <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
                    <doc.icon className="h-6 w-6 text-primary" />
                  </div>
                  <h3 className="font-semibold text-foreground mb-2">
                    {doc.title}
                  </h3>
                  <p className="text-sm text-muted-foreground mb-4">
                    View and download {doc.type} documentation
                  </p>
                  <Button variant="outline" size="sm" className="w-full gap-2">
                    <Download className="h-4 w-4" />
                    Download
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="text-center mt-8">
            <p className="text-sm text-muted-foreground">
              All documents are available for download in PDF format. 
              Property-specific documents can be found on each property details page.
            </p>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-16">
        <div className="container mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold text-foreground mb-4">
            Ready to Invest Securely?
          </h2>
          <p className="text-muted-foreground mb-6 max-w-xl mx-auto">
            Browse our curated properties and start building your real estate portfolio 
            with the protection of the SPV structure.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/marketplace">
              <Button size="lg" className="gap-2">
                Browse Properties
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link to="/how-it-works">
              <Button size="lg" variant="outline">
                Learn More
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
};

export default SPVModel;
