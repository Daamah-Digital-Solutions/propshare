import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  MapPin,
  Building2,
  DollarSign,
  ArrowRightLeft,
  Tag,
  ExternalLink,
  Layers,
} from "lucide-react";
import { Link } from "react-router-dom";
import { ExitButton } from "@/components/exit/ExitButton";
import { holdingsApi } from "@/lib/api";

const money = (v: number) => `$${v.toLocaleString()}`;

export const ActiveInvestments = () => {
  // Live holdings from the ownership ledger (server-authoritative). No mock portfolio.
  const { data } = useQuery({ queryKey: ["holdings", "mine"], queryFn: holdingsApi.mine });
  const holdings = (data?.items ?? []).filter((h) => h.units > 0);

  const totalValue = holdings.reduce((s, h) => s + h.units * Number(h.unit_price), 0);
  const totalUnits = holdings.reduce((s, h) => s + h.units, 0);

  return (
    <div className="space-y-6">
      {/* Summary Cards — live */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-gradient-to-br from-primary/10 to-primary/5 border-primary/20">
          <CardContent className="p-6">
            <div className="flex items-center gap-3">
              <div className="h-12 w-12 rounded-full bg-primary/20 flex items-center justify-center">
                <Building2 className="h-6 w-6 text-primary" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Total Properties</p>
                <p className="text-2xl font-bold text-foreground">{holdings.length}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-accent/10 to-accent/5 border-accent/20">
          <CardContent className="p-6">
            <div className="flex items-center gap-3">
              <div className="h-12 w-12 rounded-full bg-accent/20 flex items-center justify-center">
                <DollarSign className="h-6 w-6 text-accent" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Current Value</p>
                <p className="text-2xl font-bold text-foreground">{money(totalValue)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-primary/10 to-accent/5 border-primary/20">
          <CardContent className="p-6">
            <div className="flex items-center gap-3">
              <div className="h-12 w-12 rounded-full bg-primary/20 flex items-center justify-center">
                <Layers className="h-6 w-6 text-primary" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Total Units</p>
                <p className="text-2xl font-bold text-foreground">{totalUnits}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Link to="/secondary-market" className="block">
          <Card className="bg-gradient-to-br from-success/10 to-success/5 border-success/20 hover:shadow-md transition-shadow cursor-pointer h-full">
            <CardContent className="p-6">
              <div className="flex items-center gap-3">
                <div className="h-12 w-12 rounded-full bg-success/20 flex items-center justify-center">
                  <ArrowRightLeft className="h-6 w-6 text-success" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Secondary Market</p>
                  <p className="text-sm font-semibold text-success">Buy &amp; Sell Units →</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </Link>
      </div>

      {/* Holdings — live */}
      {holdings.length === 0 ? (
        <Card className="bg-card border-border">
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            You don't own any units yet.{" "}
            <Link to="/marketplace" className="text-primary underline">
              Browse properties
            </Link>{" "}
            to start investing.
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {holdings.map((h) => (
            <Card key={h.property_id} className="bg-card border-border overflow-hidden">
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="font-semibold text-foreground">{h.title ?? "Property"}</h3>
                    {h.location && (
                      <div className="flex items-center gap-1 text-sm text-muted-foreground">
                        <MapPin className="h-3 w-3" />
                        {h.location}
                      </div>
                    )}
                  </div>
                  <Badge className="bg-primary">Owned</Badge>
                </div>

                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="p-2 rounded-lg bg-muted/50">
                    <p className="text-xs text-muted-foreground">Units Owned</p>
                    <p className="text-sm font-semibold">{h.units}</p>
                  </div>
                  <div className="p-2 rounded-lg bg-muted/50">
                    <p className="text-xs text-muted-foreground">Current Value</p>
                    <p className="text-sm font-semibold text-primary">
                      {money(h.units * Number(h.unit_price))}
                    </p>
                  </div>
                  <div className="p-2 rounded-lg bg-muted/50">
                    <p className="text-xs text-muted-foreground">Listed for sale</p>
                    <p className="text-sm font-semibold">{h.listed_units}</p>
                  </div>
                  <div className="p-2 rounded-lg bg-muted/50">
                    <p className="text-xs text-muted-foreground">Sellable</p>
                    <p className="text-sm font-semibold">{h.sellable_units}</p>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 flex-wrap">
                  <Link to="/secondary-market">
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5 text-success border-success/50 hover:bg-success/10"
                    >
                      <Tag className="h-3 w-3" />
                      Sell
                    </Button>
                  </Link>
                  <ExitButton size="sm" label="Exit" />
                  <Link to={`/property/${h.property_id}`}>
                    <Button variant="outline" size="sm" className="gap-2">
                      View
                      <ExternalLink className="h-3 w-3" />
                    </Button>
                  </Link>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
