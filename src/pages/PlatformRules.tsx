import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import {
  Gavel,
  CheckCircle,
  Shield,
  Scale,
  UserCheck,
  Ban,
  AlertTriangle,
  ArrowRightLeft,
} from "lucide-react";

const rules = [
  {
    icon: UserCheck,
    title: "Provide Accurate & Truthful Information",
    description: "All information provided during registration, KYC, and transactions must be accurate, complete, and up-to-date. Misrepresentation may result in account termination.",
  },
  {
    icon: Shield,
    title: "Complete KYC/AML Requirements",
    description: "All users must complete identity verification (KYC) and comply with anti-money laundering (AML) requirements before making investments or withdrawals.",
  },
  {
    icon: Scale,
    title: "Use Platform for Lawful Purposes Only",
    description: "The platform must only be used for legitimate investment purposes. Any illegal activities, money laundering, or fraud are strictly prohibited.",
  },
  {
    icon: CheckCircle,
    title: "Respect Investment Limits & Exit Rules",
    description: "Users must adhere to minimum/maximum investment limits, lock-up periods, and exit procedures as specified for each investment opportunity.",
  },
  {
    icon: Ban,
    title: "Avoid Manipulation, Abuse, or Misuse",
    description: "Any attempt to manipulate prices, exploit system vulnerabilities, or abuse platform features will result in immediate suspension and potential legal action.",
  },
  {
    icon: ArrowRightLeft,
    title: "Comply with Secondary Market Trading Rules",
    description: "When using the secondary market, users must follow all trading rules, including pricing guidelines, settlement procedures, and fee obligations.",
  },
];

const violations = [
  { action: "Account suspension", description: "Temporary or permanent access restriction" },
  { action: "Transaction reversal", description: "Cancellation of unauthorized or fraudulent transactions" },
  { action: "Fund freeze", description: "Holding of funds pending investigation" },
  { action: "Legal action", description: "Civil or criminal proceedings as appropriate" },
  { action: "Regulatory reporting", description: "Reporting to relevant authorities when required" },
];

const PlatformRules = () => {
  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      {/* Page Header */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
          <Gavel className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-4xl font-bold text-foreground mb-4">Platform Rules</h1>
        <p className="text-muted-foreground">
          Last updated: January 2026
        </p>
      </div>

      {/* Introduction */}
      <Card className="mb-8 border-primary/20 bg-primary/5">
        <CardContent className="p-6">
          <p className="text-foreground leading-relaxed">
            To ensure fair, secure, and compliant use of the platform, all users must adhere to the following rules. 
            These rules are designed to protect all platform participants and maintain the integrity of our marketplace.
          </p>
        </CardContent>
      </Card>

      {/* Platform Rules */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold text-foreground mb-6">User Obligations</h2>
        <div className="space-y-4">
          {rules.map((rule, index) => (
            <Card key={index}>
              <CardContent className="p-5">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                    <rule.icon className="h-5 w-5 text-primary" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <Badge variant="outline" className="text-xs">Rule {index + 1}</Badge>
                      <h3 className="font-semibold text-foreground">{rule.title}</h3>
                    </div>
                    <p className="text-muted-foreground text-sm">{rule.description}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Prohibited Activities */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold text-foreground mb-6">Prohibited Activities</h2>
        <Card>
          <CardContent className="p-6">
            <p className="text-muted-foreground mb-4">The following activities are strictly prohibited:</p>
            <ul className="space-y-3">
              {[
                "Creating multiple accounts or impersonating others",
                "Providing false or misleading information",
                "Using automated systems to access the platform without authorization",
                "Attempting to bypass security measures or access controls",
                "Market manipulation or price collusion",
                "Money laundering or terrorist financing activities",
                "Harassing or threatening other users or staff",
                "Unauthorized data collection or scraping",
                "Violating intellectual property rights",
                "Any activity that violates applicable laws or regulations",
              ].map((item, index) => (
                <li key={index} className="flex items-start gap-3">
                  <Ban className="h-4 w-4 text-destructive flex-shrink-0 mt-1" />
                  <span className="text-foreground text-sm">{item}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </section>

      {/* Secondary Market Rules */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold text-foreground mb-6">Secondary Market Trading Rules</h2>
        <Card>
          <CardContent className="p-6 space-y-4 text-muted-foreground">
            <p>When trading on the secondary market, users must:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li>List units at fair market prices (no price manipulation)</li>
              <li>Honor all accepted offers within the specified timeframe</li>
              <li>Pay all applicable fees (2% exit fee for sellers, 3% purchase fee for buyers)</li>
              <li>Maintain sufficient balance for transaction completion</li>
              <li>Not engage in wash trading or artificial volume creation</li>
            </ul>
          </CardContent>
        </Card>
      </section>

      {/* Consequences */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold text-foreground mb-6 flex items-center gap-3">
          <AlertTriangle className="h-6 w-6 text-destructive" />
          Consequences of Violations
        </h2>
        <Card className="border-destructive/20">
          <CardContent className="p-6">
            <p className="text-foreground mb-4">
              Violation of platform rules may result in one or more of the following actions:
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {violations.map((violation, index) => (
                <div key={index} className="p-4 bg-destructive/5 rounded-lg border border-destructive/10">
                  <h4 className="font-semibold text-foreground mb-1">{violation.action}</h4>
                  <p className="text-sm text-muted-foreground">{violation.description}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </section>

      {/* Reporting */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold text-foreground mb-6">Reporting Violations</h2>
        <Card>
          <CardContent className="p-6 text-muted-foreground">
            <p>
              If you witness or suspect any rule violations, please report them immediately to our compliance team at{" "}
              <a href="mailto:compliance@capimaxpropshare.com" className="text-primary hover:underline">
                compliance@capimaxpropshare.com
              </a>
              . All reports will be treated confidentially.
            </p>
          </CardContent>
        </Card>
      </section>

      <Separator className="my-10" />

      {/* Acknowledgment */}
      <Card className="bg-muted/30">
        <CardContent className="p-6 text-center">
          <h3 className="font-semibold text-foreground mb-2">User Agreement</h3>
          <p className="text-sm text-muted-foreground">
            By using Capimax PropShare, you acknowledge that you have read, understood, and agreed to 
            these Platform Rules. We reserve the right to update these rules at any time with notice to users.
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default PlatformRules;
