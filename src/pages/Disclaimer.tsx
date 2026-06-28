import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { AlertTriangle, Info, ShieldAlert, Scale } from "lucide-react";

const Disclaimer = () => {
  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      {/* Page Header */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-amber-500/10 mb-4">
          <AlertTriangle className="h-8 w-8 text-amber-500" />
        </div>
        <h1 className="text-4xl font-bold text-foreground mb-4">Platform Disclaimer</h1>
        <p className="text-muted-foreground">
          Last updated: January 2026
        </p>
      </div>

      {/* Main Disclaimer Card */}
      <Card className="mb-8 border-amber-500/20 bg-amber-500/5">
        <CardContent className="p-8">
          <div className="flex items-start gap-4">
            <ShieldAlert className="h-6 w-6 text-amber-500 flex-shrink-0 mt-1" />
            <div>
              <h2 className="text-xl font-semibold text-foreground mb-4">Important Notice</h2>
              <p className="text-foreground leading-relaxed">
                Capimax PropShare is a technology-based digital platform that facilitates access to real estate 
                opportunities through structured digital tools and information services only.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Detailed Sections */}
      <div className="space-y-8">
        {/* What We Do NOT Provide */}
        <section>
          <h2 className="text-2xl font-bold text-foreground mb-4 flex items-center gap-3">
            <Info className="h-6 w-6 text-primary" />
            What We Do NOT Provide
          </h2>
          <Card>
            <CardContent className="p-6">
              <p className="text-muted-foreground leading-relaxed mb-4">
                The platform does not provide:
              </p>
              <ul className="space-y-3">
                {[
                  "Investment advice",
                  "Financial services",
                  "Brokerage services",
                  "Asset management",
                  "Fiduciary services",
                ].map((item, index) => (
                  <li key={index} className="flex items-center gap-3 text-foreground">
                    <span className="w-2 h-2 bg-destructive rounded-full flex-shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
              <Separator className="my-6" />
              <p className="text-muted-foreground leading-relaxed">
                Capimax PropShare does not make any investment recommendations, promises, or guarantees of 
                returns, income, or capital preservation.
              </p>
            </CardContent>
          </Card>
        </section>

        {/* User Responsibility */}
        <section>
          <h2 className="text-2xl font-bold text-foreground mb-4 flex items-center gap-3">
            <Scale className="h-6 w-6 text-primary" />
            User Responsibility
          </h2>
          <Card>
            <CardContent className="p-6 space-y-4">
              <p className="text-foreground leading-relaxed font-medium">
                All investment decisions are made solely by users at their own discretion and responsibility.
              </p>
              <p className="text-muted-foreground leading-relaxed">
                Capimax PropShare does not guarantee the accuracy, performance, profitability, liquidity, 
                or future value of any listed opportunity.
              </p>
            </CardContent>
          </Card>
        </section>

        {/* Performance Warning */}
        <section>
          <Card className="border-destructive/20 bg-destructive/5">
            <CardContent className="p-6">
              <div className="flex items-start gap-4">
                <AlertTriangle className="h-6 w-6 text-destructive flex-shrink-0 mt-1" />
                <div>
                  <h3 className="text-lg font-semibold text-foreground mb-2">Performance Warning</h3>
                  <p className="text-foreground leading-relaxed font-medium">
                    Past performance is not indicative of future results.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Due Diligence Advisory */}
        <section>
          <h2 className="text-2xl font-bold text-foreground mb-4">Due Diligence Advisory</h2>
          <Card>
            <CardContent className="p-6">
              <p className="text-muted-foreground leading-relaxed">
                Users are advised to conduct their own due diligence and consult independent legal, 
                financial, and tax advisors before making any investment decisions.
              </p>
              <Separator className="my-6" />
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                  { title: "Legal Advisor", description: "Consult for contractual and regulatory matters" },
                  { title: "Financial Advisor", description: "Evaluate investment suitability for your portfolio" },
                  { title: "Tax Advisor", description: "Understand tax implications in your jurisdiction" },
                ].map((advisor, index) => (
                  <div key={index} className="text-center p-4 bg-muted/50 rounded-lg">
                    <h4 className="font-semibold text-foreground mb-2">{advisor.title}</h4>
                    <p className="text-sm text-muted-foreground">{advisor.description}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Acknowledgment */}
        <section className="pb-8">
          <Card className="bg-muted/30">
            <CardContent className="p-6 text-center">
              <p className="text-sm text-muted-foreground">
                By using Capimax PropShare, you acknowledge that you have read, understood, and agreed 
                to this disclaimer and accept full responsibility for your investment decisions.
              </p>
            </CardContent>
          </Card>
        </section>
      </div>
    </div>
  );
};

export default Disclaimer;
