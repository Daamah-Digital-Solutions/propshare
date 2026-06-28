import { useState, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import PropertyFilters from "@/components/marketplace/PropertyFilters";
import PropertyGrid from "@/components/marketplace/PropertyGrid";
import { Button } from "@/components/ui/button";
import { Search, SlidersHorizontal, Grid3X3, List, Hammer, ArrowRight, Building2, Loader2 } from "lucide-react";
import { Slider } from "@/components/ui/slider";
import { propertyApi } from "@/lib/api";
import { toMarketplaceProperty } from "@/lib/properties";

export type OwnershipModel =
  | "ready-income"
  | "installment"
  | "future"
  | "option"
  | "shared-development"
  | "ready-portfolio"
  | "construction-portfolio";

export interface Property {
  id: string;
  title: string;
  location: string;
  country: string;
  city: string;
  image: string;
  price: number;
  minInvestment: number;
  yield: number;
  funded: number;
  type: "apartment" | "villa" | "commercial" | "land";
  status: "open" | "funding" | "funded";
  propertyStatus: "ready" | "construction";
  ownershipModel?: OwnershipModel;
  investors: number;
  daysLeft: number;
  developer: string;
  propertyManagement: string;
  insurance: string;
  valuation: string;
  isSample?: boolean;
  slug?: string;
}

// Default ownership model derivation (kept for the filter — models always set now).
const deriveOwnershipModel = (p: Property): OwnershipModel => {
  if (p.ownershipModel) return p.ownershipModel;
  return p.propertyStatus === "ready" ? "ready-income" : "installment";
};

export interface Filters {
  search: string;
  country: string;
  city: string;
  propertyType: string;
  status: string;
  propertyStatus: string;
  ownershipModel: string;
  priceRange: [number, number];
  yieldRange: [number, number];
  sortBy: string;
}

const Marketplace = () => {
  const [searchParams] = useSearchParams();
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [showFilters, setShowFilters] = useState(true);
  const [filters, setFilters] = useState<Filters>({
    // Seed from the global header search (?q=) so that header → marketplace search works.
    search: searchParams.get("q") ?? "",
    country: "all",
    city: "all",
    propertyType: "all",
    status: "all",
    propertyStatus: "all",
    ownershipModel: "all",
    priceRange: [0, 30000000],
    yieldRange: [0, 15],
    sortBy: "newest",
  });

  const { data, isLoading } = useQuery({
    queryKey: ["properties", "marketplace"],
    queryFn: () => propertyApi.list({ limit: 200 }),
  });

  const combinedProperties = useMemo<Property[]>(
    () => (data?.items ?? []).map(toMarketplaceProperty),
    [data],
  );

  const filteredProperties = useMemo(() => {
    let result = [...combinedProperties];

    // Search filter
    if (filters.search) {
      const searchLower = filters.search.toLowerCase();
      result = result.filter(
        (p) =>
          p.title.toLowerCase().includes(searchLower) ||
          p.location.toLowerCase().includes(searchLower)
      );
    }

    if (filters.country !== "all") {
      result = result.filter((p) => p.country === filters.country);
    }
    if (filters.city !== "all") {
      result = result.filter((p) => p.city === filters.city);
    }
    if (filters.propertyType !== "all") {
      result = result.filter((p) => p.type === filters.propertyType);
    }
    if (filters.status !== "all") {
      result = result.filter((p) => p.status === filters.status);
    }
    if (filters.propertyStatus !== "all") {
      result = result.filter((p) => p.propertyStatus === filters.propertyStatus);
    }
    if (filters.ownershipModel !== "all") {
      result = result.filter((p) => deriveOwnershipModel(p) === filters.ownershipModel);
    }

    result = result.filter(
      (p) => p.price >= filters.priceRange[0] && p.price <= filters.priceRange[1]
    );
    result = result.filter(
      (p) => p.yield >= filters.yieldRange[0] && p.yield <= filters.yieldRange[1]
    );

    switch (filters.sortBy) {
      case "price-low":
        result.sort((a, b) => a.price - b.price);
        break;
      case "price-high":
        result.sort((a, b) => b.price - a.price);
        break;
      case "yield-high":
        result.sort((a, b) => b.yield - a.yield);
        break;
      case "funded":
        result.sort((a, b) => b.funded - a.funded);
        break;
      case "newest":
      default:
        result.sort((a, b) => a.daysLeft - b.daysLeft);
        break;
    }

    return result;
  }, [filters, combinedProperties]);

  const countries = [...new Set(combinedProperties.map((p) => p.country).filter(Boolean))];
  const cities = [...new Set(combinedProperties.map((p) => p.city).filter(Boolean))];

  return (
    <div className="min-h-screen bg-background">
      <main>
        {/* Page Header */}
        <div className="bg-gradient-hero text-primary-foreground py-16">
          <div className="container mx-auto px-4">
            <h1 className="text-3xl md:text-4xl font-bold mb-4">
              Investment Marketplace
            </h1>
            <p className="text-lg text-primary-foreground/80 max-w-2xl">
              Discover premium real estate investment opportunities across the GCC region.
              Filter by location, property type, and expected returns.
            </p>

            {/* Search Bar */}
            <div className="mt-8 max-w-2xl">
              <div className="relative">
                <Search
                  size={20}
                  className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground"
                />
                <input
                  type="text"
                  placeholder="Search properties by name or location..."
                  value={filters.search}
                  onChange={(e) =>
                    setFilters((prev) => ({ ...prev, search: e.target.value }))
                  }
                  className="w-full pl-12 pr-4 py-4 bg-background text-foreground rounded-xl border-0 focus:outline-none focus:ring-2 focus:ring-primary shadow-lg"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Top Property-Type Navigation */}
        <div className="container mx-auto px-4 pt-8">
          <div className="bg-card border border-border rounded-2xl p-5 md:p-6">
            <div className="mb-4">
              <h2 className="text-lg md:text-xl font-semibold text-foreground">
                Browse by Property Type
              </h2>
              <p className="text-sm text-muted-foreground mt-0.5">
                Pick an ownership structure to explore — completed income assets or
                under-construction opportunities with multiple ownership models.
              </p>
            </div>

            <div className="grid lg:grid-cols-2 gap-4">
              {/* READY */}
              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="h-8 w-8 rounded-lg bg-emerald-500/15 text-emerald-600 flex items-center justify-center">
                      <Building2 className="h-4 w-4" />
                    </div>
                    <div>
                      <div className="font-semibold text-foreground text-sm">Ready Property</div>
                      <div className="text-xs text-muted-foreground">Completed · income generating · rental yield focused</div>
                    </div>
                  </div>
                  <button
                    onClick={() =>
                      setFilters((prev) => ({ ...prev, propertyStatus: "ready", ownershipModel: "all" }))
                    }
                    className="text-xs px-2.5 py-1 rounded-full border border-emerald-500/40 bg-background text-foreground hover:bg-emerald-500/10"
                  >
                    Show ready listings
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() =>
                      setFilters((prev) => ({ ...prev, propertyStatus: "ready", ownershipModel: "ready-income" }))
                    }
                    className="text-left p-2.5 rounded-lg bg-background border border-border hover:border-emerald-500/40"
                  >
                    <div className="text-xs font-semibold text-foreground">Income Generating</div>
                    <div className="text-[11px] text-muted-foreground">Monthly rental yield</div>
                  </button>
                  <button
                    onClick={() =>
                      setFilters((prev) => ({ ...prev, propertyStatus: "ready", ownershipModel: "ready-portfolio" }))
                    }
                    className="text-left p-2.5 rounded-lg bg-background border border-border hover:border-emerald-500/40"
                  >
                    <div className="text-xs font-semibold text-foreground">Ready Portfolio</div>
                    <div className="text-[11px] text-muted-foreground">Diversified income basket</div>
                  </button>
                </div>
              </div>

              {/* UNDER CONSTRUCTION */}
              <div className="rounded-xl border border-primary/30 bg-primary/5 p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="h-8 w-8 rounded-lg bg-primary/15 text-primary flex items-center justify-center">
                      <Hammer className="h-4 w-4" />
                    </div>
                    <div>
                      <div className="font-semibold text-foreground text-sm">Under Construction Property</div>
                      <div className="text-xs text-muted-foreground">Multiple ownership structures · appreciation focused</div>
                    </div>
                  </div>
                  <button
                    onClick={() =>
                      setFilters((prev) => ({ ...prev, propertyStatus: "construction", ownershipModel: "all" }))
                    }
                    className="text-xs px-2.5 py-1 rounded-full border border-primary/40 bg-background text-foreground hover:bg-primary/10"
                  >
                    Show construction
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { key: "installment", label: "Installment-Based", desc: "Pay in monthly installments", model: "installment" },
                    { key: "future", label: "Future Model", desc: "Lock price, settle later", model: "future" },
                    { key: "option", label: "Option Model", desc: "Premium today, decide later", model: "option" },
                    { key: "shared", label: "Shared Development", desc: "Co-invest with developer", model: "shared-development" },
                  ].map((m) => (
                    <div key={m.key} className="p-2.5 rounded-lg bg-background border border-border hover:border-primary/40">
                      <div className="text-xs font-semibold text-foreground">{m.label}</div>
                      <div className="text-[11px] text-muted-foreground mb-1.5">{m.desc}</div>
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() =>
                            setFilters((prev) => ({
                              ...prev,
                              propertyStatus: "construction",
                              ownershipModel: m.model,
                            }))
                          }
                          className="text-[10px] px-2 py-0.5 rounded-full border border-border hover:border-primary/40 text-foreground"
                        >
                          Filter
                        </button>
                        <Link
                          to={`/advanced-property/${m.key}`}
                          className="text-[10px] px-2 py-0.5 rounded-full border border-border hover:border-primary/40 text-foreground inline-flex items-center gap-1"
                        >
                          Open page <ArrowRight className="h-2.5 w-2.5" />
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Filters and Results */}
        <div className="container mx-auto px-4 py-8">
          {/* Mobile Filters */}
          <div className="flex flex-wrap gap-3 mb-6 lg:hidden">
            <select
              value={filters.country}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, country: e.target.value, city: "all" }))
              }
              className="flex-1 min-w-[120px] px-3 py-2.5 bg-secondary border border-border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="all">All Countries</option>
              {countries.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>

            <select
              value={filters.status}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, status: e.target.value }))
              }
              className="flex-1 min-w-[120px] px-3 py-2.5 bg-secondary border border-border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="all">All Status</option>
              <option value="open">Open</option>
              <option value="funding">Funding Soon</option>
              <option value="funded">Fully Funded</option>
            </select>

            <select
              value={filters.propertyStatus}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, propertyStatus: e.target.value }))
              }
              className="flex-1 min-w-[120px] px-3 py-2.5 bg-secondary border border-border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="all">All Properties</option>
              <option value="ready">Rental / Ready</option>
              <option value="construction">Under Construction</option>
            </select>

            <select
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, sortBy: e.target.value }))
              }
              className="flex-1 min-w-[120px] px-3 py-2.5 bg-secondary border border-border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="newest">Ending Soon</option>
              <option value="yield-high">Highest ROI</option>
              <option value="price-low">Price: Low to High</option>
              <option value="price-high">Price: High to Low</option>
              <option value="funded">Most Funded</option>
            </select>
          </div>

          {/* ROI Range - Mobile */}
          <div className="mb-6 lg:hidden">
            <div className="flex items-center justify-between text-sm text-muted-foreground mb-2">
              <span>ROI Range: {filters.yieldRange[0]}% – {filters.yieldRange[1]}%</span>
            </div>
            <div className="px-1">
              <Slider
                value={filters.yieldRange}
                onValueChange={(value) =>
                  setFilters((prev) => ({
                    ...prev,
                    yieldRange: value as [number, number],
                  }))
                }
                min={0}
                max={15}
                step={0.5}
                className="w-full"
              />
            </div>
          </div>

          {/* Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
            <div className="flex items-center gap-4">
              <Button
                variant={showFilters ? "default" : "outline"}
                size="sm"
                onClick={() => setShowFilters(!showFilters)}
                className="hidden lg:flex"
              >
                <SlidersHorizontal size={16} className="mr-2" />
                Filters
              </Button>
              <span className="text-muted-foreground text-sm">
                {filteredProperties.length} properties found
              </span>
            </div>

            <div className="hidden lg:flex items-center gap-4">
              {/* Sort */}
              <select
                value={filters.sortBy}
                onChange={(e) =>
                  setFilters((prev) => ({ ...prev, sortBy: e.target.value }))
                }
                className="px-4 py-2 bg-secondary border border-border rounded-lg text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="newest">Ending Soon</option>
                <option value="price-low">Price: Low to High</option>
                <option value="price-high">Price: High to Low</option>
                <option value="yield-high">Highest ROI</option>
                <option value="funded">Most Funded</option>
              </select>

              {/* View Toggle */}
              <div className="flex items-center bg-secondary rounded-lg p-1">
                <button
                  onClick={() => setViewMode("grid")}
                  className={`p-2 rounded-md transition-colors ${
                    viewMode === "grid"
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Grid3X3 size={18} />
                </button>
                <button
                  onClick={() => setViewMode("list")}
                  className={`p-2 rounded-md transition-colors ${
                    viewMode === "list"
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <List size={18} />
                </button>
              </div>
            </div>
          </div>

          {/* Filters - Top Horizontal */}
          {showFilters && (
            <div className="hidden lg:block mb-6">
              <PropertyFilters
                filters={filters}
                setFilters={setFilters}
                countries={countries}
                cities={cities}
              />
            </div>
          )}

          {/* Property Grid - Full Width */}
          <div className="w-full">
            {isLoading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            ) : (
              <PropertyGrid properties={filteredProperties} viewMode={viewMode} />
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default Marketplace;
