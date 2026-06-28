import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ExternalLink, Building2, Shield, ClipboardCheck, Home, Wallet } from "lucide-react";
import { useNavigate } from "react-router-dom";

const partners = [
  {
    category: "Developers",
    items: [
      { name: "Elite Gate Properties", logo: "https://images.unsplash.com/photo-1560179707-f14e90ef3623?w=100&h=100&fit=crop", website: "https://www.elitegateproperties.com" },
      { name: "TDH Development", logo: "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=100&h=100&fit=crop", website: "https://www.tdhdevelopment.com" },
      { name: "Priminn Hotels", logo: "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?w=100&h=100&fit=crop", website: "https://www.priminnhotel.com" },
      { name: "Capimax Development", logo: "https://images.unsplash.com/photo-1497366216548-37526070297c?w=100&h=100&fit=crop", website: "https://www.capimaxgroup.com" },
    ],
    icon: Building2,
  },
  {
    category: "Valuation",
    items: [
      { name: "CIM Financial Group", logo: "https://images.unsplash.com/photo-1551836022-4c4c79ecde51?w=100&h=100&fit=crop", website: "https://www.cimfinancialgroup.com" },
      { name: "Capimax Financial Management", logo: "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=100&h=100&fit=crop", website: "https://www.capimaxgroup.com" },
    ],
    icon: ClipboardCheck,
  },
  {
    category: "Insurance",
    items: [
      { name: "Assurax Insurance", logo: "https://images.unsplash.com/photo-1450101499163-c8848c66ca85?w=100&h=100&fit=crop", website: "https://www.assuraxinsurance.com" },
      { name: "HCC International Insurance", logo: "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?w=100&h=100&fit=crop", website: "https://www.hccinternationalinsurance.com" },
    ],
    icon: Shield,
  },
  {
    category: "Property Management",
    items: [
      { name: "Nova Property Management", logo: "https://images.unsplash.com/photo-1560518883-ce09059eeffa?w=100&h=100&fit=crop", website: "https://novapropertymanagment.com/" },
    ],
    icon: Home,
  },
  {
    category: "Digital Finance",
    items: [
      { name: "Nova Digital Finance", logo: "https://images.unsplash.com/photo-1501167786227-4cba60f6d58f?w=100&h=100&fit=crop", website: "https://www.novadf.com" },
    ],
    icon: Wallet,
  },
];

const Partners = () => {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-background">
      {/* Hero Section */}
      <section className="bg-gradient-to-br from-primary/10 via-background to-accent/5 py-16 border-b border-border">
        <div className="container mx-auto px-4 text-center">
          <Badge className="bg-primary text-primary-foreground mb-4">Our Partners</Badge>
          <h1 className="text-4xl md:text-5xl font-bold text-foreground mb-4">
            Trusted <span className="text-primary">Partners</span>
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            We work with industry-leading companies to ensure the highest standards 
            of quality, security, and service for our investors and property owners.
          </p>
        </div>
      </section>

      {/* Partners Grid */}
      <section className="py-16">
        <div className="container mx-auto px-4 space-y-12">
          {partners.map((category) => (
            <div key={category.category}>
              <div className="flex items-center gap-3 mb-6">
                <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                  <category.icon className="h-5 w-5 text-primary" />
                </div>
                <h2 className="text-2xl font-bold text-foreground">{category.category}</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {category.items.map((partner) => (
                  <Card key={partner.name} className="bg-card border-border hover:shadow-lg transition-shadow">
                    <CardContent className="p-6">
                      <div className="flex items-center gap-4">
                        <img
                          src={partner.logo}
                          alt={partner.name}
                          className="w-16 h-16 rounded-xl object-cover"
                        />
                        <div className="flex-1">
                          <h3 className="font-semibold text-foreground">{partner.name}</h3>
                          <Button
                            variant="link"
                            className="h-auto p-0 text-primary"
                            onClick={() => window.open(partner.website, "_blank")}
                          >
                            Visit Website
                            <ExternalLink className="h-3 w-3 ml-1" />
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Become a Partner CTA */}
      <section className="py-16 bg-gradient-to-r from-primary/10 to-accent/10 border-t border-border">
        <div className="container mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold text-foreground mb-4">Become a Partner</h2>
          <p className="text-muted-foreground mb-6 max-w-xl mx-auto">
            Join our network of trusted partners and help shape the future of 
            fractional real estate investment.
          </p>
          <Button size="lg" onClick={() => navigate("/support")}>Contact Us</Button>
        </div>
      </section>
    </div>
  );
};

export default Partners;
