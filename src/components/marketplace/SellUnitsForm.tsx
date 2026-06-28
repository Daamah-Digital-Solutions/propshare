import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertCircle,
  Calculator,
  Tag,
  TrendingUp,
  Info,
  CheckCircle,
  FileText,
} from "lucide-react";
import { toast } from "sonner";
import { ApiError, holdingsApi, secondaryApi } from "@/lib/api";

const SellUnitsForm = () => {
  const queryClient = useQueryClient();
  const [selectedProperty, setSelectedProperty] = useState("");
  const [unitsToSell, setUnitsToSell] = useState("");
  const [pricePerUnit, setPricePerUnit] = useState("");

  const { data: holdings } = useQuery({
    queryKey: ["secondary", "holdings"],
    queryFn: () => holdingsApi.mine(),
  });
  const { data: settings } = useQuery({
    queryKey: ["secondary", "settings"],
    queryFn: () => secondaryApi.settings(),
  });

  const ownedProperties = holdings?.items ?? [];
  const selected = ownedProperties.find((p) => p.property_id === selectedProperty);
  const refPrice = selected ? Number(selected.unit_price) : 0;
  const feePct = settings ? Number(settings.resale_fee_pct) : 1.0;

  const calc = useMemo(() => {
    const units = parseInt(unitsToSell) || 0;
    const price = parseFloat(pricePerUnit) || 0;
    const gross = units * price;
    return { units, price, gross, buyerFee: gross * (feePct / 100) };
  }, [unitsToSell, pricePerUnit, feePct]);

  const createMutation = useMutation({
    mutationFn: () =>
      secondaryApi.create({
        property_id: selectedProperty,
        units: parseInt(unitsToSell),
        price_per_unit: parseFloat(pricePerUnit),
      }),
    onSuccess: () => {
      toast.success("Listing created", {
        description: `${unitsToSell} units of ${selected?.title} listed at $${pricePerUnit}/unit`,
      });
      setSelectedProperty("");
      setUnitsToSell("");
      setPricePerUnit("");
      queryClient.invalidateQueries({ queryKey: ["secondary"] });
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? err.message : "Could not create the listing.";
      toast.error("Listing failed", { description: msg });
    },
  });

  const handleCreateListing = () => {
    if (!selectedProperty || !unitsToSell || !pricePerUnit) {
      toast.error("Please fill in all required fields");
      return;
    }
    if (selected && calc.units > selected.sellable_units) {
      toast.error(`You only have ${selected.sellable_units} sellable units available`);
      return;
    }
    createMutation.mutate();
  };

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Tag className="h-5 w-5 text-primary" />
          List Your Units for Sale
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Form Fields */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Select Property</Label>
            <Select value={selectedProperty} onValueChange={setSelectedProperty}>
              <SelectTrigger>
                <SelectValue placeholder="Choose a property" />
              </SelectTrigger>
              <SelectContent>
                {ownedProperties.length === 0 ? (
                  <div className="px-3 py-2 text-sm text-muted-foreground">
                    You don’t own any units yet.
                  </div>
                ) : (
                  ownedProperties.map((p) => (
                    <SelectItem key={p.property_id} value={p.property_id}>
                      {p.title} ({p.sellable_units} units)
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Units to Sell</Label>
            <Input
              type="number"
              placeholder="Enter number of units"
              value={unitsToSell}
              onChange={(e) => setUnitsToSell(e.target.value)}
              max={selected?.sellable_units}
            />
            {selected && (
              <p className="text-xs text-muted-foreground">
                Sellable: {selected.sellable_units} units
                {selected.listed_units > 0 && ` (${selected.listed_units} already listed)`}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label>Price per Unit ($)</Label>
            <Input
              type="number"
              placeholder="Set your asking price"
              value={pricePerUnit}
              onChange={(e) => setPricePerUnit(e.target.value)}
            />
            {selected && (
              <p className="text-xs text-muted-foreground">
                Reference price: ${refPrice.toLocaleString()}
              </p>
            )}
          </div>
        </div>

        {/* Market Insights */}
        {selected && refPrice > 0 && (
          <div className="p-4 rounded-lg bg-muted/50">
            <p className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-primary" />
              Market Insights
            </p>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <p className="text-lg font-semibold">${refPrice.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Reference Price</p>
              </div>
              <div>
                <p className="text-lg font-semibold">{selected.units}</p>
                <p className="text-xs text-muted-foreground">Units Held</p>
              </div>
              <div>
                <p className="text-lg font-semibold">{selected.sellable_units}</p>
                <p className="text-xs text-muted-foreground">Sellable</p>
              </div>
            </div>
          </div>
        )}

        <Separator />

        {/* Fee Breakdown & Calculation */}
        <div className="space-y-4">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <Calculator className="h-4 w-4 text-primary" />
            Sale Calculation
          </h4>

          <div className="bg-secondary/50 rounded-xl p-4 space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Units to Sell</span>
              <span className="font-medium">{unitsToSell || "0"} units</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Price per Unit</span>
              <span className="font-medium">${pricePerUnit || "0"}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Gross Sale Value</span>
              <span className="font-medium">${calc.gross.toLocaleString()}</span>
            </div>

            <Separator />

            <div className="flex justify-between font-semibold">
              <span className="text-foreground">Net Proceeds (You Receive)</span>
              <span className="text-primary">${calc.gross.toFixed(2)}</span>
            </div>

            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground flex items-center gap-1">
                Buyer pays resale fee ({feePct}%)
                <Info className="h-3 w-3" />
              </span>
              <span className="font-medium">+${calc.buyerFee.toFixed(2)}</span>
            </div>
          </div>

          {/* Fee Info */}
          <div className="flex items-start gap-3 p-4 bg-warning/10 rounded-xl border border-warning/20">
            <AlertCircle className="h-5 w-5 text-warning flex-shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-medium text-foreground">Fee Information</p>
              <p className="text-muted-foreground">
                You receive the full gross sale value. The {feePct}% resale fee is charged to the
                buyer on top of your asking price.
              </p>
            </div>
          </div>

          {/* Fee Summary Link */}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <FileText className="h-4 w-4" />
            <span>View complete fee structure on the </span>
            <a href="/fees" className="text-primary hover:underline">Fees page</a>
          </div>
        </div>

        {/* Submit Button */}
        <Button
          className="w-full gap-2"
          size="lg"
          onClick={handleCreateListing}
          disabled={!selectedProperty || !unitsToSell || !pricePerUnit || createMutation.isPending}
        >
          <CheckCircle className="h-4 w-4" />
          {createMutation.isPending ? "Creating…" : "Create Listing"}
          {calc.gross > 0 && (
            <Badge variant="secondary" className="ml-2">
              Receive ${calc.gross.toFixed(2)}
            </Badge>
          )}
        </Button>

        {/* Trust Indicators */}
        <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            <CheckCircle className="h-3 w-3 text-success" />
            <span>Secure Transaction</span>
          </div>
          <div className="flex items-center gap-1">
            <CheckCircle className="h-3 w-3 text-success" />
            <span>Instant Settlement</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default SellUnitsForm;
