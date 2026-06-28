import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Shield, Database, Lock, Eye, Users, Trash2 } from "lucide-react";

const Privacy = () => {
  const dataCategories = [
    {
      title: "Personal Data",
      items: ["Full name", "Date of birth", "Nationality", "Government ID details", "Photographs/selfies"],
    },
    {
      title: "Financial Data",
      items: ["Bank account information", "Payment card details", "Investment history", "Transaction records"],
    },
    {
      title: "Technical Data",
      items: ["IP address", "Device information", "Browser type", "Login timestamps", "Usage patterns"],
    },
  ];

  const purposes = [
    { title: "KYC Verification", description: "Identity verification to comply with regulatory requirements" },
    { title: "AML Compliance", description: "Anti-money laundering checks and monitoring" },
    { title: "Platform Operations", description: "Processing transactions and managing investments" },
    { title: "Customer Support", description: "Responding to inquiries and resolving issues" },
    { title: "Legal Obligations", description: "Compliance with applicable laws and regulations" },
  ];

  const userRights = [
    { icon: Eye, title: "Access", description: "Request a copy of your personal data" },
    { icon: Database, title: "Correction", description: "Request correction of inaccurate data" },
    { icon: Trash2, title: "Deletion", description: "Request deletion of your data (subject to legal retention)" },
    { icon: Lock, title: "Restriction", description: "Request restriction of data processing" },
  ];

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      {/* Page Header */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
          <Shield className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-4xl font-bold text-foreground mb-4">Privacy Policy</h1>
        <p className="text-muted-foreground">
          Last updated: January 2026
        </p>
      </div>

      {/* Commitment Statement */}
      <Card className="mb-8 border-primary/20 bg-primary/5">
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <Lock className="h-6 w-6 text-primary flex-shrink-0 mt-1" />
            <p className="text-foreground leading-relaxed">
              Capimax PropShare is committed to protecting user privacy and personal data. 
              All data is handled securely and in accordance with applicable data protection regulations.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Data We Collect */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold text-foreground mb-6 flex items-center gap-3">
          <Database className="h-6 w-6 text-primary" />
          What Data We Collect
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {dataCategories.map((category) => (
            <Card key={category.title}>
              <CardContent className="p-5">
                <h3 className="font-semibold text-foreground mb-3">{category.title}</h3>
                <ul className="space-y-2">
                  {category.items.map((item, index) => (
                    <li key={index} className="text-sm text-muted-foreground flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-primary rounded-full" />
                      {item}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Why We Collect */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold text-foreground mb-6">Why We Collect Your Data</h2>
        <Card>
          <CardContent className="p-6">
            <div className="space-y-4">
              {purposes.map((purpose, index) => (
                <div key={index} className="flex items-start gap-4 p-3 rounded-lg hover:bg-muted/50 transition-colors">
                  <Badge variant="outline" className="mt-0.5">{index + 1}</Badge>
                  <div>
                    <h4 className="font-medium text-foreground">{purpose.title}</h4>
                    <p className="text-sm text-muted-foreground">{purpose.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </section>

      {/* Data Storage & Protection */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold text-foreground mb-6">How Data is Stored & Protected</h2>
        <Card>
          <CardContent className="p-6 space-y-4 text-muted-foreground">
            <p>We implement industry-standard security measures to protect your data:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li>Encryption of data in transit and at rest (AES-256)</li>
              <li>Secure data centers with physical access controls</li>
              <li>Regular security audits and penetration testing</li>
              <li>Access controls and role-based permissions</li>
              <li>Multi-factor authentication for sensitive operations</li>
              <li>Automated threat detection and monitoring</li>
            </ul>
          </CardContent>
        </Card>
      </section>

      {/* Data Sharing */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold text-foreground mb-6 flex items-center gap-3">
          <Users className="h-6 w-6 text-primary" />
          When Data May Be Shared
        </h2>
        <Card>
          <CardContent className="p-6 space-y-4 text-muted-foreground">
            <p>Your data may be shared with:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li><strong className="text-foreground">Compliance Partners:</strong> KYC/AML verification providers</li>
              <li><strong className="text-foreground">Payment Processors:</strong> To facilitate transactions</li>
              <li><strong className="text-foreground">Legal Authorities:</strong> When required by law or court order</li>
              <li><strong className="text-foreground">Regulatory Bodies:</strong> To comply with financial regulations</li>
              <li><strong className="text-foreground">Service Providers:</strong> Cloud hosting, analytics (under strict agreements)</li>
            </ul>
            <p className="pt-4 font-medium text-foreground">
              We never sell your personal data to third parties.
            </p>
          </CardContent>
        </Card>
      </section>

      {/* User Rights */}
      <section className="mb-10">
        <h2 className="text-2xl font-bold text-foreground mb-6">Your Rights</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {userRights.map((right) => (
            <Card key={right.title}>
              <CardContent className="p-5 flex items-start gap-4">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <right.icon className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h4 className="font-semibold text-foreground">{right.title}</h4>
                  <p className="text-sm text-muted-foreground">{right.description}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
        <p className="text-sm text-muted-foreground mt-4">
          To exercise any of these rights, please contact our support team at privacy@capimaxpropshare.com
        </p>
      </section>

      <Separator className="my-10" />

      {/* Contact */}
      <Card className="bg-muted/30">
        <CardContent className="p-6 text-center">
          <h3 className="font-semibold text-foreground mb-2">Questions About Privacy?</h3>
          <p className="text-sm text-muted-foreground">
            For any privacy-related inquiries, contact our Data Protection Officer at{" "}
            <a href="mailto:privacy@capimaxpropshare.com" className="text-primary hover:underline">
              privacy@capimaxpropshare.com
            </a>
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default Privacy;
