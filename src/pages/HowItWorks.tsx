import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import {
  Search,
  UserCheck,
  CreditCard,
  FileText,
  PiggyBank,
  ArrowLeftRight,
  Building2,
  Shield,
  Users,
  TrendingUp,
  CheckCircle2,
  ArrowRight,
} from "lucide-react";

const steps = [
  {
    step: 1,
    title: "Browse Properties",
    description: "Explore our curated selection of premium real estate investments across different asset classes and locations.",
    icon: Search,
  },
  {
    step: 2,
    title: "Complete KYC",
    description: "Verify your identity through our secure KYC process. This ensures compliance and protects all investors.",
    icon: UserCheck,
  },
  {
    step: 3,
    title: "Invest",
    description: "Choose your investment amount and complete the payment using credit card, bank transfer, or cryptocurrency.",
    icon: CreditCard,
  },
  {
    step: 4,
    title: "Receive Certificate",
    description: "Get your digital investment certificate representing your ownership stake in the property SPV.",
    icon: FileText,
  },
  {
    step: 5,
    title: "Earn Returns",
    description: "Receive quarterly rental distributions directly to your wallet. Track your returns in real-time.",
    icon: PiggyBank,
  },
  {
    step: 6,
    title: "Exit Anytime",
    description: "Sell your shares on our secondary market after 6 months, providing liquidity when you need it.",
    icon: ArrowLeftRight,
  },
];

const spvBenefits = [
  {
    title: "Asset Protection",
    description: "Your investment is legally separated from platform operations through the SPV structure.",
    icon: Shield,
  },
  {
    title: "Clear Ownership",
    description: "Digital shares represent direct ownership in the property SPV, recorded on the blockchain.",
    icon: FileText,
  },
  {
    title: "Governance Rights",
    description: "Participate in major decisions affecting the property through shareholder voting.",
    icon: Users,
  },
  {
    title: "Tradeable Shares",
    description: "Sell your shares on the secondary market after 6 months for liquidity.",
    icon: TrendingUp,
  },
];

const HowItWorks = () => {
  return (
    <div className="min-h-screen bg-background">
      {/* Hero Section */}
      <section className="bg-gradient-to-br from-primary/10 via-background to-accent/5 py-16 border-b border-border">
        <div className="container mx-auto px-4 text-center">
          <Badge className="bg-primary text-primary-foreground mb-4">How It Works</Badge>
          <h1 className="text-4xl md:text-5xl font-bold text-foreground mb-4">
            Start Investing in <span className="text-primary">6 Simple Steps</span>
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Our platform makes it easy to invest in premium real estate. 
            From browsing properties to earning returns, we guide you every step of the way.
          </p>
        </div>
      </section>

      {/* Steps Section */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {steps.map((step) => (
              <Card key={step.step} className="bg-card border-border relative overflow-hidden">
                <CardContent className="p-6">
                  <div className="absolute -top-2 -right-2 h-16 w-16 bg-primary/10 rounded-full flex items-center justify-center">
                    <span className="text-2xl font-bold text-primary">{step.step}</span>
                  </div>
                  <div className="h-12 w-12 rounded-xl bg-primary/10 flex items-center justify-center mb-4">
                    <step.icon className="h-6 w-6 text-primary" />
                  </div>
                  <h3 className="text-xl font-semibold text-foreground mb-2">{step.title}</h3>
                  <p className="text-muted-foreground">{step.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* SPV Model Section */}
      <section className="py-16 bg-gradient-to-r from-primary/5 to-accent/5 border-y border-border">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <Badge className="bg-accent text-accent-foreground mb-4">SPV Model</Badge>
            <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
              Secure Investment Structure
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              Each property is held in a Special Purpose Vehicle (SPV), providing legal protection 
              and clear ownership structure for all investors.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {spvBenefits.map((benefit, index) => (
              <Card key={index} className="bg-card border-border">
                <CardContent className="p-6 text-center">
                  <div className="h-14 w-14 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
                    <benefit.icon className="h-7 w-7 text-primary" />
                  </div>
                  <h3 className="font-semibold text-foreground mb-2">{benefit.title}</h3>
                  <p className="text-sm text-muted-foreground">{benefit.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* SPV Diagram */}
          <div className="mt-12 bg-card rounded-2xl border border-border p-8">
            <h3 className="text-xl font-semibold text-foreground text-center mb-8">
              How the SPV Structure Works
            </h3>
            <div className="flex flex-col md:flex-row items-center justify-center gap-4 md:gap-8">
              <div className="text-center p-4">
                <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-2">
                  <Users className="h-8 w-8 text-primary" />
                </div>
                <p className="font-medium">Investors</p>
              </div>
              <ArrowRight className="h-6 w-6 text-muted-foreground rotate-90 md:rotate-0" />
              <div className="text-center p-4">
                <div className="h-16 w-16 rounded-full bg-accent/10 flex items-center justify-center mx-auto mb-2">
                  <Shield className="h-8 w-8 text-accent" />
                </div>
                <p className="font-medium">SPV</p>
              </div>
              <ArrowRight className="h-6 w-6 text-muted-foreground rotate-90 md:rotate-0" />
              <div className="text-center p-4">
                <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-2">
                  <Building2 className="h-8 w-8 text-primary" />
                </div>
                <p className="font-medium">Property</p>
              </div>
              <ArrowRight className="h-6 w-6 text-muted-foreground rotate-90 md:rotate-0" />
              <div className="text-center p-4">
                <div className="h-16 w-16 rounded-full bg-accent/10 flex items-center justify-center mx-auto mb-2">
                  <PiggyBank className="h-8 w-8 text-accent" />
                </div>
                <p className="font-medium">Returns</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-16">
        <div className="container mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold text-foreground mb-4">
            Ready to Start Investing?
          </h2>
          <p className="text-muted-foreground mb-6 max-w-xl mx-auto">
            Join thousands of investors already building wealth through fractional real estate.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/marketplace">
              <Button size="lg" className="gap-2">
                Browse Properties
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link to="/auth">
              <Button size="lg" variant="outline">
                Create Account
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
};

export default HowItWorks;
