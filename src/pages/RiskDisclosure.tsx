import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import {
  AlertTriangle,
  TrendingDown,
  Clock,
  HardHat,
  Calculator,
  Scale,
  CreditCard,
  AlertCircle,
} from "lucide-react";

const risks = [
  {
    icon: TrendingDown,
    title: "Real Estate Market Fluctuations",
    description: "Property values may decrease due to economic conditions, market cycles, or local factors. The real estate market is subject to periods of growth and decline that can significantly impact investment value.",
    severity: "high",
  },
  {
    icon: Clock,
    title: "Liquidity Risk & Limited Exit Opportunities",
    description: "Real estate investments are inherently illiquid. While we offer a secondary market, there is no guarantee of finding buyers at your desired price or timeline. Exit may take longer than expected.",
    severity: "high",
  },
  {
    icon: HardHat,
    title: "Construction & Development Risks",
    description: "For under-construction properties, risks include construction delays, cost overruns, contractor defaults, permit issues, and potential project cancellation. Completion is not guaranteed.",
    severity: "medium",
  },
  {
    icon: Calculator,
    title: "Valuation & Pricing Risk",
    description: "Property valuations are estimates based on available data and may not reflect actual market value. Actual sale prices may differ significantly from projected valuations.",
    severity: "medium",
  },
  {
    icon: Scale,
    title: "Regulatory & Legal Changes",
    description: "Changes in laws, regulations, tax policies, or government actions may adversely affect investments. This includes changes to property ownership rules, foreign investment restrictions, and tax treatments.",
    severity: "medium",
  },
  {
    icon: CreditCard,
    title: "Payment & Counterparty Risk",
    description: "Risks related to tenant defaults, rental payment delays, property manager performance, and other counterparties failing to meet their obligations.",
    severity: "medium",
  },
];

const RiskDisclosure = () => {
  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "high":
        return "bg-destructive/10 text-destructive border-destructive/20";
      case "medium":
        return "bg-amber-500/10 text-amber-600 border-amber-500/20";
      default:
        return "bg-muted text-muted-foreground";
    }
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      {/* Page Header */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-destructive/10 mb-4">
          <AlertTriangle className="h-8 w-8 text-destructive" />
        </div>
        <h1 className="text-4xl font-bold text-foreground mb-4">Risk Disclosure</h1>
        <p className="text-muted-foreground">
          Last updated: January 2026
        </p>
      </div>

      {/* Main Warning */}
      <Card className="mb-8 border-destructive/30 bg-destructive/5">
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <AlertCircle className="h-6 w-6 text-destructive flex-shrink-0 mt-1" />
            <div>
              <h2 className="text-lg font-semibold text-foreground mb-2">Important Investment Warning</h2>
              <p className="text-foreground leading-relaxed">
                Investing through Capimax PropShare involves risks, including but not limited to the risks 
                described below. You should carefully consider these risks before making any investment decision.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Risk Categories */}
      <div className="space-y-6 mb-10">
        {risks.map((risk, index) => (
          <Card key={index} className="overflow-hidden">
            <CardContent className="p-0">
              <div className="flex flex-col md:flex-row">
                <div className={`p-6 md:w-16 flex items-center justify-center ${getSeverityColor(risk.severity)}`}>
                  <risk.icon className="h-6 w-6" />
                </div>
                <div className="p-6 flex-1">
                  <div className="flex items-start justify-between gap-4 mb-2">
                    <h3 className="text-lg font-semibold text-foreground">{risk.title}</h3>
                    <Badge variant="outline" className={getSeverityColor(risk.severity)}>
                      {risk.severity === "high" ? "High Risk" : "Medium Risk"}
                    </Badge>
                  </div>
                  <p className="text-muted-foreground">{risk.description}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Additional Risks */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold text-foreground mb-6">Additional Considerations</h2>
        <Card>
          <CardContent className="p-6 space-y-4 text-muted-foreground">
            <div>
              <h4 className="font-medium text-foreground mb-2">Currency Risk</h4>
              <p>If you invest in a currency different from your base currency, exchange rate fluctuations may affect your returns.</p>
            </div>
            <Separator />
            <div>
              <h4 className="font-medium text-foreground mb-2">Concentration Risk</h4>
              <p>Investing a significant portion of your portfolio in real estate or specific properties may increase your overall risk exposure.</p>
            </div>
            <Separator />
            <div>
              <h4 className="font-medium text-foreground mb-2">Force Majeure</h4>
              <p>Natural disasters, pandemics, wars, or other unforeseen events may adversely affect property values and returns.</p>
            </div>
            <Separator />
            <div>
              <h4 className="font-medium text-foreground mb-2">Platform Risk</h4>
              <p>While we implement robust security measures, technology platforms face risks including cyber attacks, system failures, and operational disruptions.</p>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* Past Performance Warning */}
      <Card className="mb-10 border-amber-500/30 bg-amber-500/5">
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <TrendingDown className="h-6 w-6 text-amber-500 flex-shrink-0 mt-1" />
            <div>
              <h3 className="text-lg font-semibold text-foreground mb-2">Past Performance Notice</h3>
              <p className="text-foreground font-medium">
                Past performance is not indicative of future results.
              </p>
              <p className="text-muted-foreground mt-2">
                Any historical returns, projected returns, or investment performance shown are for illustrative 
                purposes only and should not be relied upon as indicators of future performance.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Acknowledgment */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold text-foreground mb-6">User Acknowledgment</h2>
        <Card>
          <CardContent className="p-6">
            <p className="text-foreground leading-relaxed mb-4">
              By using Capimax PropShare and making investments through our platform, you acknowledge that:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-muted-foreground">
              <li>You have read and understood all risks described in this disclosure</li>
              <li>You understand that investment outcomes are not guaranteed</li>
              <li>You are investing funds that you can afford to lose</li>
              <li>You have sought independent financial advice if needed</li>
              <li>You accept full responsibility for your investment decisions</li>
            </ul>
          </CardContent>
        </Card>
      </section>

      <Separator className="my-10" />

      {/* Seek Advice */}
      <Card className="bg-muted/30">
        <CardContent className="p-6 text-center">
          <h3 className="font-semibold text-foreground mb-2">Seek Professional Advice</h3>
          <p className="text-sm text-muted-foreground">
            We strongly recommend consulting with qualified financial, legal, and tax advisors before 
            making any investment decisions. This risk disclosure is not exhaustive and does not 
            constitute investment advice.
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default RiskDisclosure;
