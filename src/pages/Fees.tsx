import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Building2,
  Users,
  HardHat,
  CreditCard,
  Calendar,
  ArrowLeftRight,
  TrendingUp,
  CheckCircle2,
  Info,
  FileText,
  Calculator,
  Eye,
  Shield,
  BarChart3,
  Wallet,
  Receipt,
  AlertCircle,
  Percent,
} from "lucide-react";

const ownerFeeItems = [
  "Property listing on the platform",
  "Fundraising and subscription management",
  "Digital marketing exposure",
  "Investor onboarding support",
  "SPV setup coordination",
  "Reporting and investor communication tools",
  "Platform administration and operations",
];

const readyPropertyFees = [
  {
    name: "Purchase Fee",
    rate: "3%",
    description: "Paid once at the time of buying investment units",
    icon: CreditCard,
    type: "one-time",
  },
  {
    name: "Annual Management Fee",
    rate: "1%",
    description: "Calculated annually on invested amount",
    icon: Calendar,
    type: "recurring",
  },
  {
    name: "Secondary Market Exit Fee",
    rate: "Variable",
    description: "Applied when selling units on the secondary market. Automatically calculated during exit transaction.",
    icon: ArrowLeftRight,
    type: "exit",
  },
];

const constructionPropertyFees = [
  {
    name: "Down Payment Fee",
    rate: "4%",
    description: "Added to the down payment before payment",
    icon: Wallet,
    type: "one-time",
  },
  {
    name: "Installment Fee",
    rate: "4%",
    description: "Automatically added to every installment amount. Displayed clearly in the installment schedule.",
    icon: Calendar,
    type: "recurring",
  },
  {
    name: "Performance Fee",
    rate: "10%",
    description: "Of annual profit & capital growth margin. Calculated annually based on the official annual valuation report. Applied only on realized growth and profit.",
    icon: TrendingUp,
    type: "performance",
  },
];

const transparencyRules = [
  {
    icon: Receipt,
    title: "Itemized",
    description: "All fees broken down individually",
  },
  {
    icon: Eye,
    title: "Shown Before Payment",
    description: "Clear visibility before committing",
  },
  {
    icon: Calculator,
    title: "Included in Totals",
    description: "Fees reflected in final amounts",
  },
  {
    icon: FileText,
    title: "Saved in Records",
    description: "Stored in investor transaction history",
  },
];

const feeDisplayLocations = [
  "Property details page",
  "Payment summary / checkout",
  "Investor dashboard",
  "Installment schedules",
  "Downloadable reports",
];

const Fees = () => {
  return (
    <div className="min-h-screen bg-background">
      {/* Hero Section */}
      <section className="bg-gradient-to-br from-primary/10 via-background to-accent/5 py-16 border-b border-border">
        <div className="container mx-auto px-4 text-center">
          <Badge className="bg-primary text-primary-foreground mb-4">
            Platform Fees
          </Badge>
          <h1 className="text-4xl md:text-5xl font-bold text-foreground mb-4">
            Fees & <span className="text-primary">Charges</span>
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Complete transparency on all platform fees. Know exactly what you pay 
            before you invest, with no hidden charges.
          </p>
        </div>
      </section>

      {/* Owner Fees Section */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          <div className="grid md:grid-cols-2 gap-12 items-start">
            <div>
              <div className="flex items-center gap-3 mb-6">
                <div className="h-12 w-12 rounded-xl bg-accent/10 flex items-center justify-center">
                  <Building2 className="h-6 w-6 text-accent" />
                </div>
                <div>
                  <Badge variant="outline" className="mb-1">Section 1</Badge>
                  <h2 className="text-2xl font-bold text-foreground">Owner Fees</h2>
                </div>
              </div>
              <p className="text-muted-foreground mb-6">
                These fees are paid by the property owner or developer for listing, 
                fundraising, and platform services.
              </p>
              
              <Card className="border-accent/30 bg-accent/5">
                <CardContent className="p-6">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-lg font-semibold text-foreground">Total Owner Fee</span>
                    <div className="flex items-center gap-2">
                      <Percent className="h-5 w-5 text-accent" />
                      <span className="text-3xl font-bold text-accent">4%</span>
                    </div>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Calculated on the total project value and deducted according to platform rules.
                  </p>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5 text-primary" />
                  Fee Scope Includes
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-3">
                  {ownerFeeItems.map((item, index) => (
                    <li key={index} className="flex items-start gap-3">
                      <div className="h-5 w-5 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                        <div className="h-2 w-2 rounded-full bg-primary" />
                      </div>
                      <span className="text-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <Separator />

      {/* Investor Fees - Ready Properties */}
      <section className="py-16 bg-secondary/30">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <div className="inline-flex items-center gap-2 mb-4">
              <Badge variant="outline">Section 2</Badge>
              <Badge className="bg-success/10 text-success border-success/30">Ready Properties</Badge>
            </div>
            <h2 className="text-3xl font-bold text-foreground mb-4">
              Investor Fees – Ready Properties
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              Fees applicable to ready and income-generating properties with rental yield.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {readyPropertyFees.map((fee, index) => (
              <Card key={index} className="relative overflow-hidden">
                <div className={`absolute top-0 left-0 w-full h-1 ${
                  fee.type === "one-time" ? "bg-primary" : 
                  fee.type === "recurring" ? "bg-accent" : "bg-warning"
                }`} />
                <CardContent className="p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div className={`h-12 w-12 rounded-xl flex items-center justify-center ${
                      fee.type === "one-time" ? "bg-primary/10" : 
                      fee.type === "recurring" ? "bg-accent/10" : "bg-warning/10"
                    }`}>
                      <fee.icon className={`h-6 w-6 ${
                        fee.type === "one-time" ? "text-primary" : 
                        fee.type === "recurring" ? "text-accent" : "text-warning"
                      }`} />
                    </div>
                    <Badge variant="outline" className="text-xs">
                      {fee.type === "one-time" ? "One-time" : 
                       fee.type === "recurring" ? "Annual" : "On Exit"}
                    </Badge>
                  </div>
                  <h3 className="text-xl font-semibold text-foreground mb-2">{fee.name}</h3>
                  <div className="text-3xl font-bold text-primary mb-3">{fee.rate}</div>
                  <p className="text-sm text-muted-foreground">{fee.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="mt-8 max-w-3xl mx-auto">
            <Card className="bg-card border-primary/20">
              <CardContent className="p-6 flex items-start gap-4">
                <Info className="h-5 w-5 text-primary flex-shrink-0 mt-0.5" />
                <p className="text-sm text-muted-foreground">
                  All investor fees are clearly shown before payment and reflected in the checkout summary. 
                  You will always know the exact total before confirming your investment.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Investor Fees - Under Construction */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <div className="inline-flex items-center gap-2 mb-4">
              <Badge variant="outline">Section 3</Badge>
              <Badge className="bg-warning/10 text-warning border-warning/30">Under Construction</Badge>
            </div>
            <h2 className="text-3xl font-bold text-foreground mb-4">
              Investor Fees – Under Construction Properties
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              Fees applicable to under-construction properties with installment payment plans.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-8 max-w-5xl mx-auto">
            {/* One-Time & Installment Fees */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <HardHat className="h-5 w-5 text-warning" />
                  One-Time & Installment-Based Fees
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                {constructionPropertyFees.slice(0, 2).map((fee, index) => (
                  <div key={index} className="flex items-start gap-4">
                    <div className="h-10 w-10 rounded-lg bg-warning/10 flex items-center justify-center flex-shrink-0">
                      <fee.icon className="h-5 w-5 text-warning" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-1">
                        <h4 className="font-semibold text-foreground">{fee.name}</h4>
                        <Badge className="bg-warning/10 text-warning">{fee.rate}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">{fee.description}</p>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* Performance Fee */}
            <Card className="border-primary/30">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5 text-primary" />
                  Performance-Based Fee
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-center py-6">
                  <div className="text-5xl font-bold text-primary mb-2">10%</div>
                  <p className="text-lg font-medium text-foreground mb-4">
                    Of Annual Profit & Capital Growth Margin
                  </p>
                </div>
                <ul className="space-y-3">
                  {[
                    "Calculated annually",
                    "Based on the official annual valuation report",
                    "Applied only on realized growth and profit",
                  ].map((item, index) => (
                    <li key={index} className="flex items-start gap-3">
                      <CheckCircle2 className="h-5 w-5 text-primary flex-shrink-0" />
                      <span className="text-muted-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </div>

          <div className="mt-8 max-w-3xl mx-auto">
            <Card className="bg-warning/5 border-warning/20">
              <CardContent className="p-6 flex items-start gap-4">
                <Calculator className="h-5 w-5 text-warning flex-shrink-0 mt-0.5" />
                <p className="text-sm text-muted-foreground">
                  All fees are calculated automatically by the system and included in the installment 
                  calculator before payment. The installment schedule shows the exact breakdown of 
                  principal and fees for each payment.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <Separator />

      {/* Fee Transparency Section */}
      <section className="py-16 bg-gradient-to-r from-primary/5 to-accent/5">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <Badge variant="outline" className="mb-4">Section 4</Badge>
            <h2 className="text-3xl font-bold text-foreground mb-4">
              Fee Transparency & Display Rules
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              We believe in complete transparency. Every fee is clearly communicated at every step.
            </p>
          </div>

          <div className="grid md:grid-cols-4 gap-6 mb-12">
            {transparencyRules.map((rule, index) => (
              <Card key={index}>
                <CardContent className="p-6 text-center">
                  <div className="h-14 w-14 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
                    <rule.icon className="h-7 w-7 text-primary" />
                  </div>
                  <h3 className="font-semibold text-foreground mb-2">{rule.title}</h3>
                  <p className="text-sm text-muted-foreground">{rule.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card className="max-w-3xl mx-auto">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Eye className="h-5 w-5 text-primary" />
                Fee Breakdown Appears In
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {feeDisplayLocations.map((location, index) => (
                  <div 
                    key={index} 
                    className="flex items-center gap-2 bg-secondary/50 rounded-lg px-4 py-3"
                  >
                    <CheckCircle2 className="h-4 w-4 text-primary flex-shrink-0" />
                    <span className="text-sm text-foreground">{location}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* System Behavior Section */}
      <section className="py-16">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <Badge variant="outline" className="mb-4">Section 5</Badge>
            <h2 className="text-3xl font-bold text-foreground mb-4">
              System Behavior Requirements
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              Our platform ensures consistent and automatic fee calculation across all transactions.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Shield className="h-5 w-5 text-primary" />
                  Fee Calculation Principles
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {[
                  {
                    icon: Calculator,
                    title: "Dynamic Calculation",
                    description: "Fees are calculated in real-time based on investment amount",
                  },
                  {
                    icon: AlertCircle,
                    title: "No Hidden Fees",
                    description: "All fees are disclosed upfront, no surprise charges",
                  },
                  {
                    icon: BarChart3,
                    title: "Consistent Application",
                    description: "Same fee logic across all platform areas",
                  },
                ].map((item, index) => (
                  <div key={index} className="flex items-start gap-3">
                    <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <item.icon className="h-4 w-4 text-primary" />
                    </div>
                    <div>
                      <h4 className="font-medium text-foreground">{item.title}</h4>
                      <p className="text-sm text-muted-foreground">{item.description}</p>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5 text-accent" />
                  Fee Logic Applied Across
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {[
                    {
                      area: "Checkout & Payment",
                      description: "Full fee breakdown before confirming investment",
                      icon: CreditCard,
                    },
                    {
                      area: "Installment Plans",
                      description: "Fees included in each installment calculation",
                      icon: Calendar,
                    },
                    {
                      area: "Secondary Market",
                      description: "Exit fees calculated on trade completion",
                      icon: ArrowLeftRight,
                    },
                    {
                      area: "Reports & Analytics",
                      description: "Fee history visible in all financial reports",
                      icon: FileText,
                    },
                  ].map((item, index) => (
                    <div key={index} className="flex items-center gap-3 p-3 bg-secondary/50 rounded-lg">
                      <item.icon className="h-5 w-5 text-accent flex-shrink-0" />
                      <div>
                        <h4 className="font-medium text-foreground text-sm">{item.area}</h4>
                        <p className="text-xs text-muted-foreground">{item.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Fee Summary Table */}
      <section className="py-16 bg-secondary/30">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-foreground mb-4">
              Fee Summary
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              Quick reference table of all platform fees.
            </p>
          </div>

          <div className="max-w-4xl mx-auto overflow-hidden rounded-xl border border-border">
            <table className="w-full">
              <thead className="bg-card">
                <tr>
                  <th className="text-left px-6 py-4 text-foreground font-semibold">Fee Type</th>
                  <th className="text-left px-6 py-4 text-foreground font-semibold">Applies To</th>
                  <th className="text-center px-6 py-4 text-foreground font-semibold">Rate</th>
                  <th className="text-left px-6 py-4 text-foreground font-semibold">When Applied</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                <tr className="bg-accent/5">
                  <td className="px-6 py-4 font-medium text-foreground">Owner Fee</td>
                  <td className="px-6 py-4 text-muted-foreground">Property Owners</td>
                  <td className="px-6 py-4 text-center">
                    <Badge className="bg-accent/10 text-accent">4%</Badge>
                  </td>
                  <td className="px-6 py-4 text-muted-foreground">On project value</td>
                </tr>
                <tr className="bg-background">
                  <td className="px-6 py-4 font-medium text-foreground">Purchase Fee</td>
                  <td className="px-6 py-4 text-muted-foreground">Ready Properties</td>
                  <td className="px-6 py-4 text-center">
                    <Badge className="bg-primary/10 text-primary">3%</Badge>
                  </td>
                  <td className="px-6 py-4 text-muted-foreground">One-time at purchase</td>
                </tr>
                <tr className="bg-card">
                  <td className="px-6 py-4 font-medium text-foreground">Management Fee</td>
                  <td className="px-6 py-4 text-muted-foreground">Ready Properties</td>
                  <td className="px-6 py-4 text-center">
                    <Badge className="bg-primary/10 text-primary">1%</Badge>
                  </td>
                  <td className="px-6 py-4 text-muted-foreground">Annual</td>
                </tr>
                <tr className="bg-background">
                  <td className="px-6 py-4 font-medium text-foreground">Down Payment Fee</td>
                  <td className="px-6 py-4 text-muted-foreground">Under Construction</td>
                  <td className="px-6 py-4 text-center">
                    <Badge className="bg-warning/10 text-warning">4%</Badge>
                  </td>
                  <td className="px-6 py-4 text-muted-foreground">Added to down payment</td>
                </tr>
                <tr className="bg-card">
                  <td className="px-6 py-4 font-medium text-foreground">Installment Fee</td>
                  <td className="px-6 py-4 text-muted-foreground">Under Construction</td>
                  <td className="px-6 py-4 text-center">
                    <Badge className="bg-warning/10 text-warning">4%</Badge>
                  </td>
                  <td className="px-6 py-4 text-muted-foreground">Per installment</td>
                </tr>
                <tr className="bg-background">
                  <td className="px-6 py-4 font-medium text-foreground">Performance Fee</td>
                  <td className="px-6 py-4 text-muted-foreground">Under Construction</td>
                  <td className="px-6 py-4 text-center">
                    <Badge className="bg-primary/10 text-primary">10%</Badge>
                  </td>
                  <td className="px-6 py-4 text-muted-foreground">On annual profit</td>
                </tr>
                <tr className="bg-card">
                  <td className="px-6 py-4 font-medium text-foreground">Exit Fee</td>
                  <td className="px-6 py-4 text-muted-foreground">Secondary Market</td>
                  <td className="px-6 py-4 text-center">
                    <Badge variant="outline">Variable</Badge>
                  </td>
                  <td className="px-6 py-4 text-muted-foreground">On exit transaction</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Contact Section */}
      <section className="py-16">
        <div className="container mx-auto px-4 text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">
            Questions About Fees?
          </h2>
          <p className="text-muted-foreground mb-6 max-w-xl mx-auto">
            Our team is here to help you understand all aspects of our fee structure. 
            Contact us for any clarifications.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a href="/support">
              <button className="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2">
                Contact Support
              </button>
            </a>
            <a href="/how-it-works">
              <button className="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2">
                Learn How It Works
              </button>
            </a>
          </div>
        </div>
      </section>
    </div>
  );
};

export default Fees;
