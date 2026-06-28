import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { X, RotateCcw, ExternalLink } from "lucide-react";
import type { Filters } from "@/pages/Marketplace";

interface PropertyFiltersProps {
  filters: Filters;
  setFilters: React.Dispatch<React.SetStateAction<Filters>>;
  countries: string[];
  cities: string[];
}

const PropertyFilters = ({
  filters,
  setFilters,
  countries,
  cities,
}: PropertyFiltersProps) => {
  const resetFilters = () => {
    setFilters({
      search: "",
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
  };

  const hasActiveFilters =
    filters.country !== "all" ||
    filters.city !== "all" ||
    filters.propertyType !== "all" ||
    filters.status !== "all" ||
    filters.propertyStatus !== "all" ||
    filters.ownershipModel !== "all" ||
    filters.priceRange[0] > 0 ||
    filters.priceRange[1] < 30000000 ||
    filters.yieldRange[0] > 0 ||
    filters.yieldRange[1] < 15;

  return (
    <div className="bg-card rounded-2xl border border-border p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-foreground">Filters</h3>
        {hasActiveFilters && (
          <Button variant="ghost" size="sm" onClick={resetFilters}>
            <RotateCcw size={14} className="mr-1" />
            Reset
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
        {/* Country */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-2">
            Country
          </label>
          <select
            value={filters.country}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, country: e.target.value, city: "all" }))
            }
            className="w-full px-4 py-2.5 bg-secondary border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="all">All Countries</option>
            {countries.map((country) => (
              <option key={country} value={country}>
                {country}
              </option>
            ))}
          </select>
        </div>

        {/* City */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-2">
            City
          </label>
          <select
            value={filters.city}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, city: e.target.value }))
            }
            className="w-full px-4 py-2.5 bg-secondary border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="all">All Cities</option>
            {cities
              .filter((city) => {
                if (filters.country === "all") return true;
                // Filter cities by selected country
                return true; // In real app, filter by country
              })
              .map((city) => (
                <option key={city} value={city}>
                  {city}
                </option>
              ))}
          </select>
        </div>

        {/* Property Type */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-2">
            Property Type
          </label>
          <select
            value={filters.propertyType}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, propertyType: e.target.value }))
            }
            className="w-full px-4 py-2.5 bg-secondary border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="all">All Types</option>
            <option value="apartment">Apartment</option>
            <option value="villa">Villa</option>
            <option value="commercial">Commercial</option>
            <option value="land">Land</option>
          </select>
        </div>

        {/* Investment Status */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-2">
            Investment Status
          </label>
          <select
            value={filters.status}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, status: e.target.value }))
            }
            className="w-full px-4 py-2.5 bg-secondary border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="all">All Status</option>
            <option value="open">Open for Investment</option>
            <option value="funding">Funding Soon</option>
            <option value="funded">Fully Funded</option>
          </select>
        </div>

        {/* Property Status */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-2">
            Property Status
          </label>
          <select
            value={filters.propertyStatus}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, propertyStatus: e.target.value }))
            }
            className="w-full px-4 py-2.5 bg-secondary border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="all">All</option>
            <option value="ready">Ready Properties</option>
            <option value="construction">Under Construction</option>
          </select>
        </div>

        {/* Ownership Model — categorized (full width) */}
        <div className="col-span-2 md:col-span-3 xl:col-span-5">
          <label className="block text-sm font-medium text-foreground mb-2">
            Ownership Model
          </label>
          <div className="space-y-3">
            <div>
              <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
                Ready Property
              </div>
              <div className="flex flex-wrap gap-2">
                {[
                  { v: "ready-income", l: "Income Generating" },
                  { v: "ready-portfolio", l: "Ready Portfolio" },
                ].map((o) => (
                  <button
                    key={o.v}
                    onClick={() =>
                      setFilters((prev) => ({ ...prev, ownershipModel: o.v, propertyStatus: "ready" }))
                    }
                    className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                      filters.ownershipModel === o.v
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-secondary text-foreground border-border hover:border-primary/40"
                    }`}
                  >
                    {o.l}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
                Under Construction
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() =>
                    setFilters((prev) => ({
                      ...prev,
                      ownershipModel: "all",
                      propertyStatus: "construction",
                    }))
                  }
                  className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                    filters.propertyStatus === "construction" && filters.ownershipModel === "all"
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-secondary text-foreground border-border hover:border-primary/40"
                  }`}
                >
                  All Under Construction
                </button>
                {[
                  { v: "installment", l: "Installment", page: "installment" },
                  { v: "future", l: "Future", page: "future" },
                  { v: "option", l: "Option", page: "option" },
                  { v: "shared-development", l: "Partnership w/ Developer", page: "shared" },
                  { v: "construction-portfolio", l: "Construction Portfolio", page: null },
                ].map((o) => {
                  const active = filters.ownershipModel === o.v;
                  return (
                    <div key={o.v} className="inline-flex items-stretch rounded-full border border-border overflow-hidden">
                      <button
                        onClick={() =>
                          setFilters((prev) => ({
                            ...prev,
                            ownershipModel: o.v,
                            propertyStatus: "construction",
                          }))
                        }
                        className={`px-2.5 py-1 text-xs transition-colors ${
                          active
                            ? "bg-primary text-primary-foreground"
                            : "bg-secondary text-foreground hover:bg-primary/10"
                        }`}
                      >
                        {o.l}
                      </button>
                      {o.page && (
                        <Link
                          to={`/advanced-property/${o.page}`}
                          title={`Open ${o.l} page`}
                          className={`px-2 flex items-center border-l border-border transition-colors ${
                            active
                              ? "bg-primary text-primary-foreground hover:bg-primary/90"
                              : "bg-secondary text-muted-foreground hover:text-primary hover:bg-primary/10"
                          }`}
                        >
                          <ExternalLink className="h-3 w-3" />
                        </Link>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
            {filters.ownershipModel !== "all" && (
              <button
                onClick={() =>
                  setFilters((prev) => ({ ...prev, ownershipModel: "all" }))
                }
                className="text-xs text-muted-foreground hover:text-foreground underline"
              >
                Clear ownership model
              </button>
            )}
          </div>
        </div>
        {/* Price Range */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-2">
            Property Value
          </label>
          <div className="px-2">
            <Slider
              value={filters.priceRange}
              onValueChange={(value) =>
                setFilters((prev) => ({
                  ...prev,
                  priceRange: value as [number, number],
                }))
              }
              min={0}
              max={30000000}
              step={100000}
              className="w-full"
            />
          </div>
          <div className="flex justify-between text-sm text-muted-foreground mt-2">
            <span>${(filters.priceRange[0] / 1000000).toFixed(1)}M</span>
            <span>${(filters.priceRange[1] / 1000000).toFixed(1)}M</span>
          </div>
        </div>

        {/* Yield Range */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-2">
            Expected Yield
          </label>
          <div className="px-2">
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
          <div className="flex justify-between text-sm text-muted-foreground mt-2">
            <span>{filters.yieldRange[0]}%</span>
            <span>{filters.yieldRange[1]}%</span>
          </div>
        </div>
      </div>

      {/* Active Filters */}
      {hasActiveFilters && (
        <div className="mt-6 pt-6 border-t border-border">
          <div className="text-sm font-medium text-foreground mb-3">Active Filters</div>
          <div className="flex flex-wrap gap-2">
            {filters.country !== "all" && (
              <span className="inline-flex items-center gap-1 px-3 py-1 bg-primary/10 text-primary rounded-full text-sm">
                {filters.country}
                <button
                  onClick={() => setFilters((prev) => ({ ...prev, country: "all" }))}
                  className="hover:text-primary/70"
                >
                  <X size={14} />
                </button>
              </span>
            )}
            {filters.city !== "all" && (
              <span className="inline-flex items-center gap-1 px-3 py-1 bg-primary/10 text-primary rounded-full text-sm">
                {filters.city}
                <button
                  onClick={() => setFilters((prev) => ({ ...prev, city: "all" }))}
                  className="hover:text-primary/70"
                >
                  <X size={14} />
                </button>
              </span>
            )}
            {filters.propertyType !== "all" && (
              <span className="inline-flex items-center gap-1 px-3 py-1 bg-primary/10 text-primary rounded-full text-sm">
                {filters.propertyType}
                <button
                  onClick={() => setFilters((prev) => ({ ...prev, propertyType: "all" }))}
                  className="hover:text-primary/70"
                >
                  <X size={14} />
                </button>
              </span>
            )}
            {filters.status !== "all" && (
              <span className="inline-flex items-center gap-1 px-3 py-1 bg-primary/10 text-primary rounded-full text-sm">
                {filters.status}
                <button
                  onClick={() => setFilters((prev) => ({ ...prev, status: "all" }))}
                  className="hover:text-primary/70"
                >
                  <X size={14} />
                </button>
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default PropertyFilters;
