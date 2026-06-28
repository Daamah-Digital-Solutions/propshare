import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  MapPin,
  TrendingUp,
  Users,
  Clock,
  ArrowRight,
  CheckCircle,
  Building2,
} from "lucide-react";
import type { Property } from "@/pages/Marketplace";

interface PropertyGridProps {
  properties: Property[];
  viewMode: "grid" | "list";
}

const ownershipLabel = (m?: Property["ownershipModel"]) => {
  switch (m) {
    case "ready-income": return { label: "INCOME GENERATING", tone: "bg-success/10 text-success border-success/30" };
    case "installment": return { label: "INSTALLMENT", tone: "bg-amber-500/10 text-amber-600 border-amber-500/30" };
    case "future": return { label: "FUTURE", tone: "bg-blue-500/10 text-blue-500 border-blue-500/30" };
    case "option": return { label: "OPTION", tone: "bg-violet-500/10 text-violet-500 border-violet-500/30" };
    case "shared-development": return { label: "SHARED DEVELOPMENT", tone: "bg-fuchsia-500/10 text-fuchsia-500 border-fuchsia-500/30" };
    case "ready-portfolio": return { label: "READY PORTFOLIO", tone: "bg-teal-500/10 text-teal-600 border-teal-500/30" };
    case "construction-portfolio": return { label: "CONSTRUCTION PORTFOLIO", tone: "bg-orange-500/10 text-orange-600 border-orange-500/30" };
    default: return null;
  }
};

const PropertyCard = ({ property, viewMode }: { property: Property; viewMode: "grid" | "list" }) => {
  const getStatusBadge = () => {
    switch (property.status) {
      case "open":
        return <Badge className="bg-success text-success-foreground">Open</Badge>;
      case "funding":
        return <Badge className="bg-warning text-warning-foreground">Funding Soon</Badge>;
      case "funded":
        return <Badge variant="secondary">Fully Funded</Badge>;
    }
  };

  const ownership = ownershipLabel(property.ownershipModel);
  const advancedSlug =
    property.ownershipModel === "option"
      ? "option"
      : property.ownershipModel === "future"
      ? "future"
      : property.ownershipModel === "installment"
      ? "installment"
      : property.ownershipModel === "shared-development"
      ? "shared"
      : null;
  const detailsHref = advancedSlug
    ? `/advanced-property/${advancedSlug}`
    : property.isSample && property.slug
    ? `/property-sample/${property.slug}`
    : `/property/${property.id}`;

  const getTypeBadge = () => {
    const typeLabels = {
      apartment: "Apartment",
      villa: "Villa",
      commercial: "Commercial",
      land: "Land",
    };
    return typeLabels[property.type];
  };

  if (viewMode === "list") {
    return (
      <Link to={detailsHref}>
        <div className="group bg-card rounded-2xl overflow-hidden border border-border shadow-md hover:shadow-xl transition-all duration-300 flex">
          {/* Image */}
          <div className="relative w-64 flex-shrink-0">
            <img
              src={property.image}
              alt={property.title}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            />
            <div className="absolute top-4 left-4 flex gap-2">
              {getStatusBadge()}
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 p-6 flex flex-col justify-between">
            <div>
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                <Badge variant="outline">{getTypeBadge()}</Badge>
                {ownership && (
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${ownership.tone}`}>
                    {ownership.label}
                  </span>
                )}
                {property.propertyStatus === "construction" && (
                  <Badge variant="outline" className="border-warning text-warning font-semibold">
                    <Clock size={12} className="mr-1" />
                    UNDER CONSTRUCTION
                  </Badge>
                )}
              </div>
              
              <h3 className="text-xl font-semibold text-foreground mb-1 group-hover:text-primary transition-colors">
                {property.title}
              </h3>
              
              <div className="flex items-center gap-1 text-muted-foreground text-sm mb-4">
                <MapPin size={14} />
                <span>{property.location}</span>
              </div>

              <div className="flex items-center gap-6 flex-wrap">
                <div>
                  <div className="text-sm text-muted-foreground">Property Value</div>
                  <div className="font-semibold text-foreground">
                    ${property.price.toLocaleString()}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Min. Investment</div>
                  <div className="font-semibold text-primary">
                    ${property.minInvestment}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Expected Yield</div>
                  <div className="font-semibold text-success flex items-center gap-1">
                    <TrendingUp size={14} />
                    {property.yield}%
                  </div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Developer</div>
                  <div className="font-semibold text-foreground flex items-center gap-1">
                    <Building2 size={14} />
                    {property.developer}
                  </div>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
              <div className="flex items-center gap-4 text-sm text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Users size={14} />
                  {property.investors} investors
                </span>
                {property.daysLeft > 0 && (
                  <span className="flex items-center gap-1">
                    <Clock size={14} />
                    {property.daysLeft} days left
                  </span>
                )}
              </div>
              <div className="flex items-center gap-4">
                <div className="w-32">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-muted-foreground">Funded</span>
                    <span className="font-medium text-foreground">{property.funded}%</span>
                  </div>
                  <Progress value={property.funded} className="h-1.5" />
                </div>
                <Button variant="default" size="sm">
                  View Details
                  <ArrowRight size={14} />
                </Button>
              </div>
            </div>
          </div>
        </div>
      </Link>
    );
  }

  return (
    <Link to={detailsHref}>
      <div className="group bg-card rounded-2xl overflow-hidden border border-border shadow-md hover:shadow-xl transition-all duration-300 hover:-translate-y-1">
        {/* Image */}
        <div className="relative h-48 overflow-hidden">
          <img
            src={property.image}
            alt={property.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
          />
          <div className="absolute top-4 left-4 flex gap-2 flex-wrap">
            {getStatusBadge()}
          </div>
          <div className="absolute top-4 right-4 flex flex-col items-end gap-1">
            <Badge variant="outline" className="bg-background/80 backdrop-blur-sm">
              {getTypeBadge()}
            </Badge>
            {ownership && (
              <span className={`text-[10px] font-semibold tracking-wide px-2 py-0.5 rounded-full border bg-background/80 backdrop-blur-sm ${ownership.tone}`}>
                {ownership.label}
              </span>
            )}
          </div>
          {property.propertyStatus === "construction" && (
            <div className="absolute bottom-4 left-4">
              <Badge variant="outline" className="bg-background/80 backdrop-blur-sm border-warning text-warning font-semibold">
                <Clock size={12} className="mr-1" />
                UNDER CONSTRUCTION
              </Badge>
            </div>
          )}
        </div>

        {/* Content */}
        <div className="p-5">
          <div className="flex items-center gap-1 text-muted-foreground text-sm mb-2">
            <MapPin size={14} />
            <span>{property.location}</span>
          </div>

          <h3 className="text-lg font-semibold text-foreground mb-3 group-hover:text-primary transition-colors line-clamp-1">
            {property.title}
          </h3>

          {/* Stats */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="bg-secondary/50 rounded-lg p-3">
              <div className="text-xs text-muted-foreground mb-1">Property Value</div>
              <div className="font-semibold text-foreground">
                ${property.price.toLocaleString()}
              </div>
            </div>
            <div className="bg-secondary/50 rounded-lg p-3">
              <div className="text-xs text-muted-foreground mb-1">Min. Investment</div>
              <div className="font-semibold text-primary">${property.minInvestment}</div>
            </div>
          </div>

          {/* Yield & Developer */}
          <div className="flex flex-col gap-2 mb-4">
            <div className="flex items-center gap-2 text-success">
              <TrendingUp size={16} />
              <span className="font-semibold">{property.yield}% Expected Yield</span>
            </div>
            <div className="flex items-center gap-2 text-muted-foreground text-sm">
              <Building2 size={14} />
              <span>{property.developer}</span>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="mb-4">
            <div className="flex justify-between text-sm mb-2">
              <span className="text-muted-foreground">Funding Progress</span>
              <span className="font-medium text-foreground">{property.funded}%</span>
            </div>
            <Progress value={property.funded} className="h-2" />
          </div>

          {/* Footer Stats */}
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-4">
            <span className="flex items-center gap-1">
              <Users size={12} />
              {property.investors} investors
            </span>
            {property.daysLeft > 0 ? (
              <span className="flex items-center gap-1">
                <Clock size={12} />
                {property.daysLeft} days left
              </span>
            ) : (
              <span className="flex items-center gap-1 text-success">
                <CheckCircle size={12} />
                Completed
              </span>
            )}
          </div>

          {/* CTA */}
          <Button variant="default" className="w-full group/btn">
            View Details
            <ArrowRight size={16} className="group-hover/btn:translate-x-1 transition-transform" />
          </Button>
        </div>
      </div>
    </Link>
  );
};

const PropertyGrid = ({ properties, viewMode }: PropertyGridProps) => {
  if (properties.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <Building2 size={64} className="text-muted-foreground/30 mb-4" />
        <h3 className="text-xl font-semibold text-foreground mb-2">No properties found</h3>
        <p className="text-muted-foreground max-w-md">
          Try adjusting your filters or search criteria to find more investment opportunities.
        </p>
      </div>
    );
  }

  return (
    <div
      className={
        viewMode === "grid"
          ? "grid sm:grid-cols-2 xl:grid-cols-3 gap-6"
          : "space-y-4"
      }
    >
      {properties.map((property) => (
        <PropertyCard key={property.id} property={property} viewMode={viewMode} />
      ))}
    </div>
  );
};

export default PropertyGrid;
