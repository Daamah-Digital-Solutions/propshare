import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, MapPin, TrendingUp, Clock, Building2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { propertyApi } from "@/lib/api";

interface Property {
  id: string;
  title: string;
  location: string;
  image: string;
  price: number;
  minInvestment: number;
  yield: number;
  funded: number;
  type: "ready" | "construction";
  status: "open" | "funding" | "funded";
  developer: string;
}

const READY_MODELS = new Set(["ready-income", "ready-portfolio"]);

const PropertyCard = ({ property }: { property: Property }) => {
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

  return (
    <div className="group bg-card rounded-2xl overflow-hidden border border-border shadow-md hover:shadow-xl transition-all duration-300 hover:-translate-y-1">
      {/* Image */}
      <div className="relative h-48 overflow-hidden">
        <img
          src={property.image}
          alt={property.title}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
        />
        <div className="absolute top-4 left-4 flex gap-2">
          {getStatusBadge()}
          {property.type === "construction" && (
            <Badge variant="outline" className="bg-background/80 backdrop-blur-sm">
              <Clock size={12} className="mr-1" />
              Under Construction
            </Badge>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="p-5">
        <div className="flex items-center gap-1 text-muted-foreground text-sm mb-2">
          <MapPin size={14} />
          <span>{property.location}</span>
        </div>
        
        <h3 className="text-lg font-semibold text-foreground mb-3 group-hover:text-primary transition-colors">
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
            <div className="text-xs text-muted-foreground mb-1">Min. Ownership</div>
            <div className="font-semibold text-primary">
              ${property.minInvestment}
            </div>
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
          <div className="h-2 bg-secondary rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-hero rounded-full transition-all duration-500"
              style={{ width: `${property.funded}%` }}
            />
          </div>
        </div>

        {/* CTA */}
        <Link to={`/property/${property.id}`}>
          <Button variant="default" className="w-full group/btn">
            View Details
            <ArrowRight size={16} className="group-hover/btn:translate-x-1 transition-transform" />
          </Button>
        </Link>
      </div>
    </div>
  );
};

const FeaturedProperties = () => {
  const { data, isLoading } = useQuery({
    queryKey: ["properties", "featured"],
    queryFn: () => propertyApi.list({ sort: "funded", limit: 4 }),
  });

  const properties: Property[] = (data?.items ?? []).map((s) => ({
    id: s.id,
    title: s.title,
    location: s.location,
    image: s.image ?? "",
    price: s.total_value,
    minInvestment: s.minimum_investment,
    yield: s.expected_yield ?? s.target_yield ?? 0,
    funded: Math.round(s.funding_progress),
    type: READY_MODELS.has(s.model) ? "ready" : "construction",
    status: s.status === "funded" ? "funded" : s.funding_progress >= 90 ? "funding" : "open",
    developer: s.developer_name ?? "—",
  }));

  return (
    <section className="py-20 bg-background">
      <div className="container mx-auto px-4">
        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-12">
          <div>
            <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-3">
              Featured Real Estate Opportunities
            </h2>
            <p className="text-muted-foreground max-w-2xl">
              Curated premium properties with high yield potential and strong fundamentals.
              All properties are vetted by our expert team.
            </p>
          </div>
          <Link to="/marketplace">
            <Button variant="outline" size="lg">
              View All Properties
              <ArrowRight size={18} />
            </Button>
          </Link>
        </div>

        {/* Properties Grid */}
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : properties.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            No featured properties yet. Check back soon.
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {properties.map((property, index) => (
              <div
                key={property.id}
                className="animate-fade-up"
                style={{ animationDelay: `${index * 0.1}s` }}
              >
                <PropertyCard property={property} />
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};

export default FeaturedProperties;
