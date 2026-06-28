import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { FileText, CheckCircle, AlertCircle } from "lucide-react";

const Terms = () => {
  const keyPoints = [
    "Capimax PropShare acts as a technology and marketplace platform, not a bank or investment advisor.",
    "All investments carry risk, including potential loss of capital.",
    "Users are responsible for ensuring they are legally eligible to invest.",
    "The platform may suspend or terminate accounts for compliance or regulatory reasons.",
    "All transactions are subject to platform rules, fees, and applicable laws.",
    "Continued use of the platform constitutes full acceptance of these terms.",
  ];

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      {/* Page Header */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
          <FileText className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-4xl font-bold text-foreground mb-4">Terms & Conditions</h1>
        <p className="text-muted-foreground">
          Last updated: January 2026
        </p>
      </div>

      {/* Agreement Notice */}
      <Card className="mb-8 border-primary/20 bg-primary/5">
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <AlertCircle className="h-6 w-6 text-primary flex-shrink-0 mt-1" />
            <p className="text-foreground leading-relaxed">
              By accessing or using Capimax PropShare, you agree to be bound by these Terms & Conditions. 
              Please read them carefully before using our platform.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Key Points */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold text-foreground mb-6">Key Points</h2>
        <Card>
          <CardContent className="p-6">
            <ul className="space-y-4">
              {keyPoints.map((point, index) => (
                <li key={index} className="flex items-start gap-3">
                  <CheckCircle className="h-5 w-5 text-primary flex-shrink-0 mt-0.5" />
                  <span className="text-foreground">{point}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </section>

      {/* Detailed Sections */}
      <div className="space-y-8">
        <section>
          <h2 className="text-xl font-bold text-foreground mb-4">1. Platform Services</h2>
          <Card>
            <CardContent className="p-6 space-y-4 text-muted-foreground">
              <p>
                Capimax PropShare provides a digital marketplace for fractional real estate investment opportunities. 
                The platform facilitates access to property investments through structured vehicles such as Special Purpose Vehicles (SPVs).
              </p>
              <p>
                We are a technology platform and do not provide banking, investment advisory, or asset management services. 
                All investment decisions are made solely by users.
              </p>
            </CardContent>
          </Card>
        </section>

        <section>
          <h2 className="text-xl font-bold text-foreground mb-4">2. User Eligibility</h2>
          <Card>
            <CardContent className="p-6 space-y-4 text-muted-foreground">
              <p>To use our platform, you must:</p>
              <ul className="list-disc pl-6 space-y-2">
                <li>Be at least 18 years of age</li>
                <li>Have legal capacity to enter into binding agreements</li>
                <li>Complete identity verification (KYC) requirements</li>
                <li>Not be a resident of a prohibited jurisdiction</li>
                <li>Have a valid bank account or payment method</li>
              </ul>
            </CardContent>
          </Card>
        </section>

        <section>
          <h2 className="text-xl font-bold text-foreground mb-4">3. Investment Risks</h2>
          <Card>
            <CardContent className="p-6 space-y-4 text-muted-foreground">
              <p>
                All investments made through the platform carry inherent risks, including but not limited to:
              </p>
              <ul className="list-disc pl-6 space-y-2">
                <li>Loss of invested capital</li>
                <li>Illiquidity of investments</li>
                <li>Market value fluctuations</li>
                <li>Delays in expected returns</li>
                <li>Regulatory changes affecting investments</li>
              </ul>
              <p className="font-medium text-foreground">
                Past performance is not indicative of future results.
              </p>
            </CardContent>
          </Card>
        </section>

        <section>
          <h2 className="text-xl font-bold text-foreground mb-4">4. Account Responsibilities</h2>
          <Card>
            <CardContent className="p-6 space-y-4 text-muted-foreground">
              <p>Users are responsible for:</p>
              <ul className="list-disc pl-6 space-y-2">
                <li>Maintaining accurate and up-to-date account information</li>
                <li>Securing login credentials and preventing unauthorized access</li>
                <li>Reporting suspicious activity immediately</li>
                <li>Complying with all applicable laws and regulations</li>
              </ul>
            </CardContent>
          </Card>
        </section>

        <section>
          <h2 className="text-xl font-bold text-foreground mb-4">5. Platform Fees</h2>
          <Card>
            <CardContent className="p-6 space-y-4 text-muted-foreground">
              <p>
                All transactions are subject to platform fees as disclosed on our Fees page. 
                These may include purchase fees, management fees, performance fees, and exit fees.
              </p>
              <p>
                Fee structures may be updated from time to time, and users will be notified of any changes.
              </p>
            </CardContent>
          </Card>
        </section>

        <section>
          <h2 className="text-xl font-bold text-foreground mb-4">6. Account Suspension & Termination</h2>
          <Card>
            <CardContent className="p-6 space-y-4 text-muted-foreground">
              <p>
                The platform reserves the right to suspend or terminate user accounts for:
              </p>
              <ul className="list-disc pl-6 space-y-2">
                <li>Violation of Terms & Conditions</li>
                <li>Fraudulent or suspicious activity</li>
                <li>Failure to complete KYC/AML requirements</li>
                <li>Regulatory or legal compliance requirements</li>
                <li>Platform rule violations</li>
              </ul>
            </CardContent>
          </Card>
        </section>

        <section>
          <h2 className="text-xl font-bold text-foreground mb-4">7. Governing Law</h2>
          <Card>
            <CardContent className="p-6 text-muted-foreground">
              <p>
                These Terms & Conditions are governed by and construed in accordance with the laws of the 
                United Arab Emirates. Any disputes arising from the use of this platform shall be subject 
                to the exclusive jurisdiction of the courts of Dubai.
              </p>
            </CardContent>
          </Card>
        </section>
      </div>

      <Separator className="my-10" />

      {/* Acceptance Notice */}
      <Card className="bg-muted/30">
        <CardContent className="p-6 text-center">
          <p className="text-sm text-muted-foreground">
            By continuing to use Capimax PropShare, you confirm that you have read, understood, and agreed 
            to these Terms & Conditions. If you do not agree, please discontinue use of the platform.
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default Terms;
