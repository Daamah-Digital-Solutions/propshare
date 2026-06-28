import { Building2, Target, Layers, Users, Shield, Server, Handshake, Eye, UserCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

const AboutCapimaxPropShare = () => {
  return (
    <div className="min-h-screen bg-background">
      {/* Hero Section */}
      <section className="bg-gradient-to-br from-primary/10 via-background to-secondary/10 py-16 md:py-24">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto text-center">
            <h1 className="text-4xl md:text-5xl font-bold text-foreground mb-6">
              About Capimax PropShare
            </h1>
            <p className="text-xl text-muted-foreground">
              Technology-driven digital platform for fractional real estate investment
            </p>
          </div>
        </div>
      </section>

      <div className="container mx-auto px-4 py-12 max-w-5xl">
        {/* Platform Overview */}
        <section className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <Building2 className="h-8 w-8 text-primary" />
            <h2 className="text-3xl font-bold text-foreground">Platform Overview</h2>
          </div>
          <div className="prose prose-lg max-w-none">
            <p className="text-muted-foreground leading-relaxed mb-4">
              Capimax PropShare is a technology-driven digital platform designed to enable fractional real estate investment through structured, transparent, and secure digital solutions. The platform connects investors with carefully selected real estate opportunities while providing property owners and developers with efficient access to capital.
            </p>
            <p className="text-muted-foreground leading-relaxed">
              Capimax PropShare operates as a technology and marketplace platform, offering digital tools, data, and infrastructure to facilitate access to real estate opportunities.
            </p>
          </div>
        </section>

        <Separator className="my-8" />

        {/* Platform Objective */}
        <section className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <Target className="h-8 w-8 text-primary" />
            <h2 className="text-3xl font-bold text-foreground">Platform Objective</h2>
          </div>
          <p className="text-muted-foreground mb-6">The primary objective of Capimax PropShare is to:</p>
          <div className="grid md:grid-cols-2 gap-4">
            {[
              "Democratize access to real estate investment",
              "Lower entry barriers for investors",
              "Enable efficient capital raising for property owners",
              "Enhance transparency, reporting, and investor experience through technology"
            ].map((objective, index) => (
              <Card key={index} className="bg-card/50">
                <CardContent className="p-4 flex items-center gap-3">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold">
                    {index + 1}
                  </div>
                  <p className="text-foreground">{objective}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <Separator className="my-8" />

        {/* Business Model */}
        <section className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <Layers className="h-8 w-8 text-primary" />
            <h2 className="text-3xl font-bold text-foreground">Business Model</h2>
          </div>
          <p className="text-muted-foreground mb-6">
            Capimax PropShare operates on a fractional investment model supported by a structured SPV (Special Purpose Vehicle) framework:
          </p>
          <div className="grid md:grid-cols-2 gap-4">
            {[
              "Each property is structured through a dedicated SPV",
              "Investors participate by acquiring fractional investment units",
              "Returns are generated from rental income, capital appreciation, or project development",
              "The platform provides digital infrastructure, reporting, and management tools"
            ].map((item, index) => (
              <Card key={index} className="bg-card/50 border-l-4 border-l-primary">
                <CardContent className="p-4">
                  <p className="text-foreground">{item}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <Separator className="my-8" />

        {/* Fractional Investment System */}
        <section className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <Users className="h-8 w-8 text-primary" />
            <h2 className="text-3xl font-bold text-foreground">Fractional Investment System</h2>
          </div>
          <p className="text-muted-foreground mb-6">Fractional investment allows investors to:</p>
          <div className="grid md:grid-cols-2 gap-4 mb-8">
            {[
              "Invest in real estate with smaller amounts",
              "Diversify across multiple properties",
              "Access professionally structured opportunities",
              "Monitor performance and returns digitally"
            ].map((item, index) => (
              <div key={index} className="flex items-center gap-3 p-4 bg-secondary/30 rounded-lg">
                <div className="h-2 w-2 rounded-full bg-primary" />
                <p className="text-foreground">{item}</p>
              </div>
            ))}
          </div>
          <p className="text-muted-foreground mb-4">Investment types include:</p>
          <div className="grid md:grid-cols-2 gap-4">
            <Card className="bg-gradient-to-br from-primary/5 to-primary/10">
              <CardContent className="p-6">
                <h4 className="font-semibold text-foreground mb-2">Ready Properties</h4>
                <p className="text-muted-foreground">Income-generating properties with immediate rental returns</p>
              </CardContent>
            </Card>
            <Card className="bg-gradient-to-br from-secondary/5 to-secondary/10">
              <CardContent className="p-6">
                <h4 className="font-semibold text-foreground mb-2">Under-Construction</h4>
                <p className="text-muted-foreground">Properties with installment plans and capital growth potential</p>
              </CardContent>
            </Card>
          </div>
        </section>

        <Separator className="my-8" />

        {/* Benefits */}
        <section className="mb-12">
          <h2 className="text-3xl font-bold text-foreground mb-8 text-center">Benefits</h2>
          <div className="grid md:grid-cols-2 gap-8">
            <Card>
              <CardHeader>
                <CardTitle className="text-primary">For Investors</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-3">
                  {[
                    "Lower minimum investment amounts",
                    "Portfolio diversification",
                    "Transparent reporting and documentation",
                    "Access to secondary market exit mechanisms",
                    "Digital wallet and return distribution tracking"
                  ].map((item, index) => (
                    <li key={index} className="flex items-center gap-3">
                      <div className="h-1.5 w-1.5 rounded-full bg-primary" />
                      <span className="text-muted-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-primary">For Property Owners & Developers</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-3">
                  {[
                    "Structured fundraising model",
                    "Access to a wider investor base",
                    "Clear governance and reporting",
                    "Reduced operational complexity"
                  ].map((item, index) => (
                    <li key={index} className="flex items-center gap-3">
                      <div className="h-1.5 w-1.5 rounded-full bg-primary" />
                      <span className="text-muted-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </div>
        </section>

        <Separator className="my-8" />

        {/* Transparency & Governance */}
        <section className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <Shield className="h-8 w-8 text-primary" />
            <h2 className="text-3xl font-bold text-foreground">Transparency & Governance</h2>
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            {[
              "Clear SPV structures per property",
              "Separate reporting for each investment",
              "Full access to financial, valuation, and performance reports",
              "Defined exit rules and fee structures"
            ].map((item, index) => (
              <Card key={index} className="bg-card/50">
                <CardContent className="p-4 flex items-center gap-3">
                  <Shield className="h-5 w-5 text-primary flex-shrink-0" />
                  <p className="text-foreground">{item}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <Separator className="my-8" />

        {/* Technology & Security */}
        <section className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <Server className="h-8 w-8 text-primary" />
            <h2 className="text-3xl font-bold text-foreground">Technology & Security</h2>
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            {[
              "Advanced digital infrastructure",
              "Secure data handling and encryption",
              "User authentication and compliance checks",
              "Scalable architecture supporting Web App and PWA"
            ].map((item, index) => (
              <Card key={index} className="bg-card/50">
                <CardContent className="p-4 flex items-center gap-3">
                  <Server className="h-5 w-5 text-primary flex-shrink-0" />
                  <p className="text-foreground">{item}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <Separator className="my-8" />

        {/* Partnerships */}
        <section className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <Handshake className="h-8 w-8 text-primary" />
            <h2 className="text-3xl font-bold text-foreground">Partnerships</h2>
          </div>
          <p className="text-muted-foreground mb-6">Capimax PropShare collaborates with:</p>
          <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-4 mb-6">
            {[
              "Real estate developers",
              "Property managers",
              "Valuation and advisory firms",
              "Insurance providers",
              "Technology and compliance partners"
            ].map((partner, index) => (
              <Card key={index} className="bg-gradient-to-br from-primary/5 to-transparent">
                <CardContent className="p-4 text-center">
                  <p className="text-foreground font-medium">{partner}</p>
                </CardContent>
              </Card>
            ))}
          </div>
          <p className="text-muted-foreground text-center italic">
            Each partner contributes to strengthening the investment ecosystem and ensuring professional execution.
          </p>
        </section>

        <Separator className="my-8" />

        {/* Leadership & Experience */}
        <section className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <UserCircle className="h-8 w-8 text-primary" />
            <h2 className="text-3xl font-bold text-foreground">Leadership & Experience</h2>
          </div>
          <p className="text-muted-foreground mb-6">
            Capimax PropShare is founded and led by professionals with experience in real estate, finance, and digital platforms.
          </p>
          <Card className="bg-gradient-to-br from-primary/10 to-secondary/10">
            <CardContent className="p-8 text-center">
              <div className="h-20 w-20 rounded-full bg-primary/20 flex items-center justify-center mx-auto mb-4">
                <UserCircle className="h-12 w-12 text-primary" />
              </div>
              <h3 className="text-xl font-bold text-foreground mb-2">Ibrahim Gad</h3>
              <p className="text-primary font-medium">Founder & Chief Executive Officer</p>
            </CardContent>
          </Card>
        </section>

        <Separator className="my-8" />

        {/* Vision */}
        <section className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <Eye className="h-8 w-8 text-primary" />
            <h2 className="text-3xl font-bold text-foreground">Vision</h2>
          </div>
          <Card className="bg-gradient-to-r from-primary/10 via-background to-secondary/10 border-2 border-primary/20">
            <CardContent className="p-8">
              <p className="text-lg text-foreground text-center italic leading-relaxed">
                "To become a trusted global digital platform for fractional real estate investment, combining technology, transparency, and structured investment models to serve investors and property owners worldwide."
              </p>
            </CardContent>
          </Card>
        </section>
      </div>
    </div>
  );
};

export default AboutCapimaxPropShare;
