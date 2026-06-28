import { Link } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Scale,
  FileText,
  Shield,
  AlertTriangle,
  BookOpen,
  Gavel,
  ArrowRight,
  CheckCircle,
} from "lucide-react";

const legalDocuments = [
  {
    title: "Terms & Conditions",
    description: "Platform usage terms, user responsibilities, and service agreements",
    icon: FileText,
    url: "/terms",
    required: true,
  },
  {
    title: "Privacy Policy",
    description: "How we collect, use, store, and protect your personal data",
    icon: Shield,
    url: "/privacy",
    required: true,
  },
  {
    title: "Risk Disclosure",
    description: "Investment risks, market fluctuations, and potential loss warnings",
    icon: AlertTriangle,
    url: "/risk-disclosure",
    required: true,
  },
  {
    title: "Disclaimer",
    description: "Platform limitations, advisory disclaimers, and liability notices",
    icon: BookOpen,
    url: "/disclaimer",
    required: true,
  },
  {
    title: "Platform Rules",
    description: "User conduct guidelines, compliance requirements, and trading rules",
    icon: Gavel,
    url: "/platform-rules",
    required: true,
  },
];

const Legal = () => {
  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      {/* Page Header */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
          <Scale className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-4xl font-bold text-foreground mb-4">Legal & Compliance</h1>
        <p className="text-muted-foreground text-lg max-w-3xl mx-auto">
          Capimax PropShare is a digital investment platform providing access to fractional real estate 
          opportunities through structured investment models, including SPVs.
        </p>
      </div>

      {/* Platform Commitment */}
      <Card className="mb-10 border-primary/20 bg-primary/5">
        <CardContent className="p-8">
          <div className="flex flex-col md:flex-row items-start gap-6">
            <div className="w-12 h-12 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0">
              <CheckCircle className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-foreground mb-3">Our Commitment</h2>
              <p className="text-muted-foreground leading-relaxed">
                The platform operates with a strong commitment to <strong className="text-foreground">transparency</strong>, 
                <strong className="text-foreground"> compliance</strong>, <strong className="text-foreground">governance</strong>, 
                and <strong className="text-foreground">risk disclosure</strong>, ensuring users clearly understand their rights, 
                obligations, and associated risks.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Required Notice */}
      <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4 mb-8 flex items-center gap-3">
        <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0" />
        <p className="text-sm text-foreground">
          <strong>Important:</strong> All users are required to review and agree to the following legal documents before using the platform.
        </p>
      </div>

      {/* Legal Documents Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
        {legalDocuments.map((doc) => (
          <Card key={doc.title} className="hover:shadow-lg transition-all group">
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                  <doc.icon className="h-6 w-6 text-primary" />
                </div>
                {doc.required && (
                  <Badge variant="outline" className="text-xs">Required</Badge>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <CardTitle className="text-lg mb-2">{doc.title}</CardTitle>
              <CardDescription className="mb-4">{doc.description}</CardDescription>
              <Button variant="ghost" className="p-0 h-auto text-primary hover:text-primary/80" asChild>
                <Link to={doc.url} className="flex items-center gap-2">
                  Read Full Document
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Contact for Questions */}
      <Card className="bg-muted/30">
        <CardContent className="p-6 text-center">
          <h3 className="font-semibold text-foreground mb-2">Have Questions?</h3>
          <p className="text-sm text-muted-foreground mb-4">
            If you have any questions about our legal documents or compliance policies, please contact our support team.
          </p>
          <Button variant="outline" asChild>
            <Link to="/support">Contact Support</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};

export default Legal;
