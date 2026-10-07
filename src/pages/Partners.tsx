import {
  Building2,
  ConciergeBell,
  CreditCard,
  ExternalLink,
  Globe,
  Landmark,
  Scale,
  ShieldCheck,
  Umbrella,
  type LucideIcon,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PARTNER_SECTIONS, type Partner, type PartnerSectionKey } from "@/lib/partners";
import { displayUrl } from "@/lib/verificationPartners";

/**
 * The Partners page: the client's partner register (src/lib/partners.ts), one section per kind
 * of partner. Each partner is a card with its logo, what it does for the platform, where it
 * operates and a link to its own site.
 */

const ICONS: Record<PartnerSectionKey, LucideIcon> = {
  payments: CreditCard,
  identity: ShieldCheck,
  banking: Landmark,
  advisory: Scale,
  insurance: Umbrella,
  developers: Building2,
  operations: ConciergeBell,
};

function PartnerCard({ partner }: { partner: Partner }) {
  return (
    <Card className="flex h-full flex-col overflow-hidden border-border bg-card transition-shadow hover:shadow-lg">
      {/* the logos are drawn for a white ground: the tile stays white in the dark theme too */}
      <div className="flex h-32 items-center justify-center border-b border-border bg-white p-6">
        <img
          src={partner.logo}
          alt={`${partner.name} logo`}
          loading="lazy"
          className="max-h-20 max-w-[220px] object-contain"
        />
      </div>
      <CardContent className="flex flex-1 flex-col p-5">
        <h3 className="text-lg font-semibold leading-snug text-foreground">{partner.name}</h3>
        {partner.role && <p className="mt-0.5 text-sm font-medium text-primary">{partner.role}</p>}
        <p className="mt-3 flex-1 text-sm leading-relaxed text-muted-foreground">
          {partner.description}
        </p>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t border-border pt-3 text-sm">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <Globe className="h-4 w-4 shrink-0" aria-hidden="true" />
            {partner.market}
          </span>
          {partner.url && (
            <a
              href={partner.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium text-primary underline-offset-4 hover:underline"
            >
              <span className="sr-only">{partner.name} website: </span>
              {displayUrl(partner.url)}
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            </a>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

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

      {/* The register, section by section */}
      <div className="py-16">
        <div className="container mx-auto px-4 space-y-14">
          {PARTNER_SECTIONS.map((section) => {
            const Icon = ICONS[section.key];
            const headingId = `partners-${section.key}`;
            return (
              <section key={section.key} aria-labelledby={headingId} data-testid={headingId}>
                <div className="flex items-center gap-3 mb-6">
                  <div className="h-10 w-10 shrink-0 rounded-lg bg-primary/10 flex items-center justify-center">
                    <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
                  </div>
                  <h2 id={headingId} className="text-2xl font-bold text-foreground">
                    {section.title}
                  </h2>
                </div>
                <ul className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {section.partners.map((partner) => (
                    <li key={partner.key} data-testid={`partner-${partner.key}`}>
                      <PartnerCard partner={partner} />
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      </div>

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
