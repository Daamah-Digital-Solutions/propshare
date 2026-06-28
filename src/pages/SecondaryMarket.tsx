import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ArrowUpDown,
  TrendingUp,
  TrendingDown,
  Search,
  ShoppingCart,
  Tag,
  Clock,
  CheckCircle2,
  Building2,
  Activity,
  MapPin,
} from "lucide-react";
import { toast } from "sonner";
import SellUnitsForm from "@/components/marketplace/SellUnitsForm";
import { ApiError, secondaryApi, type SecondaryListing } from "@/lib/api";

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const hrs = Math.floor(diff / 3_600_000);
  if (hrs < 1) return "just now";
  if (hrs < 24) return `${hrs} hour${hrs === 1 ? "" : "s"} ago`;
  const days = Math.floor(hrs / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

const SecondaryMarket = () => {
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState("recent");
  const [selectedListing, setSelectedListing] = useState<SecondaryListing | null>(null);
  const [buyUnits, setBuyUnits] = useState("");

  const { data: listingsData } = useQuery({
    queryKey: ["secondary", "listings"],
    queryFn: () => secondaryApi.list(),
  });
  const { data: settings } = useQuery({
    queryKey: ["secondary", "settings"],
    queryFn: () => secondaryApi.settings(),
  });
  const { data: mine } = useQuery({
    queryKey: ["secondary", "mine"],
    queryFn: () => secondaryApi.mine(),
  });

  const feePct = settings ? Number(settings.resale_fee_pct) : 1.0;

  const listings = useMemo(() => {
    let rows = listingsData?.items ?? [];
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      rows = rows.filter(
        (l) =>
          (l.property_title ?? "").toLowerCase().includes(q) ||
          (l.property_location ?? "").toLowerCase().includes(q),
      );
    }
    const sorted = [...rows];
    if (sortBy === "price-low") sorted.sort((a, b) => Number(a.price_per_unit) - Number(b.price_per_unit));
    else if (sortBy === "price-high") sorted.sort((a, b) => Number(b.price_per_unit) - Number(a.price_per_unit));
    return sorted;
  }, [listingsData, searchQuery, sortBy]);

  const buyMutation = useMutation({
    mutationFn: ({ listingId, units }: { listingId: string; units: number }) =>
      secondaryApi.buy(listingId, units, crypto.randomUUID()),
    onSuccess: (trade) => {
      toast.success("Purchase complete", {
        description: `You bought ${trade.units} unit(s) for $${Number(trade.total_charged).toLocaleString()} (incl. fee).`,
      });
      setSelectedListing(null);
      setBuyUnits("");
      queryClient.invalidateQueries({ queryKey: ["secondary"] });
      queryClient.invalidateQueries({ queryKey: ["wallet"] });
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? err.message : "Purchase could not be completed.";
      toast.error("Purchase failed", { description: msg });
    },
  });

  const stats = useMemo(() => {
    const rows = listingsData?.items ?? [];
    const totalUnits = rows.reduce((s, l) => s + l.units_remaining, 0);
    const props = new Set(rows.map((l) => l.property_id)).size;
    const avg =
      rows.length > 0
        ? rows.reduce((s, l) => s + Number(l.price_per_unit), 0) / rows.length
        : 0;
    return [
      { label: "Active Listings", value: String(rows.length) },
      { label: "Units Available", value: totalUnits.toLocaleString() },
      { label: "Avg. Price/Unit", value: avg ? `$${avg.toFixed(0)}` : "—" },
      { label: "Properties", value: String(props) },
    ];
  }, [listingsData]);

  const buyQty = parseInt(buyUnits) || 0;
  const subtotal = selectedListing ? buyQty * Number(selectedListing.price_per_unit) : 0;
  const fee = subtotal * (feePct / 100);

  return (
    <div className="min-h-screen bg-background">
      <main>
        {/* Hero Section */}
        <section className="bg-gradient-to-br from-primary/10 via-background to-accent/5 py-12 border-b border-border">
          <div className="container mx-auto px-4">
            <div className="max-w-3xl">
              <Badge className="bg-accent text-accent-foreground mb-4">Secondary Market</Badge>
              <h1 className="text-4xl md:text-5xl font-bold text-foreground mb-4">
                Trade Property <span className="text-primary">Investment Units</span>
              </h1>
              <p className="text-lg text-muted-foreground">
                Buy and sell fractional property shares from other investors.
                Access liquidity before property exit with our peer-to-peer marketplace.
              </p>
            </div>
          </div>
        </section>

        {/* Market Stats */}
        <section className="py-6 border-b border-border bg-card">
          <div className="container mx-auto px-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {stats.map((stat, index) => (
                <div key={index} className="text-center">
                  <p className="text-sm text-muted-foreground">{stat.label}</p>
                  <p className="text-2xl font-bold text-foreground">{stat.value}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Main Content */}
        <section className="py-8">
          <div className="container mx-auto px-4">
            <Tabs defaultValue="buy" className="space-y-6">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <TabsList className="bg-muted/50">
                  <TabsTrigger value="buy" className="gap-2">
                    <ShoppingCart className="h-4 w-4" />
                    Buy Units
                  </TabsTrigger>
                  <TabsTrigger value="sell" className="gap-2">
                    <Tag className="h-4 w-4" />
                    Sell Units
                  </TabsTrigger>
                  <TabsTrigger value="activity" className="gap-2">
                    <Activity className="h-4 w-4" />
                    My Listings
                  </TabsTrigger>
                </TabsList>

                <div className="flex items-center gap-3">
                  <div className="relative flex-1 md:w-64">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Search properties..."
                      className="pl-10"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                    />
                  </div>
                  <Select value={sortBy} onValueChange={setSortBy}>
                    <SelectTrigger className="w-40">
                      <ArrowUpDown className="h-4 w-4 mr-2" />
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="recent">Most Recent</SelectItem>
                      <SelectItem value="price-low">Price: Low to High</SelectItem>
                      <SelectItem value="price-high">Price: High to Low</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <TabsContent value="buy" className="space-y-4">
                {listings.length === 0 ? (
                  <Card className="bg-card border-border">
                    <CardContent className="py-16 text-center text-muted-foreground">
                      No active listings right now. Check back soon, or list your own units to sell.
                    </CardContent>
                  </Card>
                ) : (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {listings.map((listing) => {
                      const ref = listing.unit_price_ref ? Number(listing.unit_price_ref) : 0;
                      const price = Number(listing.price_per_unit);
                      const change = ref > 0 ? ((price - ref) / ref) * 100 : 0;
                      return (
                        <Card
                          key={listing.listing_id}
                          className="bg-card border-border overflow-hidden hover:shadow-lg transition-shadow"
                        >
                          <div className="flex flex-col md:flex-row">
                            <div className="md:w-1/3 bg-gradient-to-br from-primary/15 to-accent/10 flex items-center justify-center min-h-[12rem]">
                              <Building2 className="h-12 w-12 text-primary/50" />
                            </div>
                            <div className="md:w-2/3 p-5">
                              <div className="flex items-start justify-between mb-3">
                                <div>
                                  <h3 className="font-semibold text-foreground">
                                    {listing.property_title ?? "Property"}
                                  </h3>
                                  <div className="flex items-center gap-1 text-sm text-muted-foreground">
                                    <MapPin className="h-3 w-3" />
                                    {listing.property_location ?? "—"}
                                  </div>
                                </div>
                                <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20">
                                  <CheckCircle2 className="h-3 w-3 mr-1" />
                                  Verified
                                </Badge>
                              </div>

                              <div className="grid grid-cols-2 gap-3 mb-4">
                                <div className="p-2 rounded-lg bg-muted/50">
                                  <p className="text-xs text-muted-foreground">Price/Unit</p>
                                  <div className="flex items-center gap-1">
                                    <p className="text-sm font-semibold">${price.toLocaleString()}</p>
                                    {ref > 0 && (
                                      change >= 0 ? (
                                        <span className="text-xs text-primary flex items-center">
                                          <TrendingUp className="h-3 w-3" />
                                          +{change.toFixed(1)}%
                                        </span>
                                      ) : (
                                        <span className="text-xs text-destructive flex items-center">
                                          <TrendingDown className="h-3 w-3" />
                                          {change.toFixed(1)}%
                                        </span>
                                      )
                                    )}
                                  </div>
                                </div>
                                <div className="p-2 rounded-lg bg-muted/50">
                                  <p className="text-xs text-muted-foreground">Available Units</p>
                                  <p className="text-sm font-semibold">{listing.units_remaining}</p>
                                </div>
                                <div className="p-2 rounded-lg bg-muted/50">
                                  <p className="text-xs text-muted-foreground">Reference Price</p>
                                  <p className="text-sm font-semibold">
                                    {ref > 0 ? `$${ref.toLocaleString()}` : "—"}
                                  </p>
                                </div>
                                <div className="p-2 rounded-lg bg-muted/50">
                                  <p className="text-xs text-muted-foreground">Listing Value</p>
                                  <p className="text-sm font-semibold">
                                    ${(price * listing.units_remaining).toLocaleString()}
                                  </p>
                                </div>
                              </div>

                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                  <Clock className="h-4 w-4" />
                                  {timeAgo(listing.created_at)}
                                </div>
                                <Dialog
                                  open={selectedListing?.listing_id === listing.listing_id}
                                  onOpenChange={(open) => {
                                    setSelectedListing(open ? listing : null);
                                    if (!open) setBuyUnits("");
                                  }}
                                >
                                  <Button onClick={() => setSelectedListing(listing)}>Buy Units</Button>
                                  <DialogContent>
                                    <DialogHeader>
                                      <DialogTitle>
                                        Buy Units - {listing.property_title ?? "Property"}
                                      </DialogTitle>
                                    </DialogHeader>
                                    <div className="space-y-4 py-4">
                                      <div className="p-4 rounded-lg bg-muted/50">
                                        <div className="flex justify-between mb-2">
                                          <span className="text-muted-foreground">Price per Unit</span>
                                          <span className="font-semibold">${price.toLocaleString()}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span className="text-muted-foreground">Available</span>
                                          <span className="font-semibold">{listing.units_remaining} units</span>
                                        </div>
                                      </div>
                                      <div className="space-y-2">
                                        <Label>Number of Units</Label>
                                        <Input
                                          type="number"
                                          placeholder="Enter units to buy"
                                          value={buyUnits}
                                          onChange={(e) => setBuyUnits(e.target.value)}
                                          max={listing.units_remaining}
                                          min={1}
                                        />
                                      </div>

                                      {/* Fee Breakdown for Buyer (backend-driven rate) */}
                                      <div className="p-4 rounded-lg bg-secondary/50 space-y-2 text-sm">
                                        <div className="flex justify-between">
                                          <span className="text-muted-foreground">Subtotal</span>
                                          <span className="font-medium">${subtotal.toLocaleString()}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span className="text-muted-foreground">
                                            Purchase Fee ({feePct}%)
                                          </span>
                                          <span className="font-medium">+${fee.toFixed(2)}</span>
                                        </div>
                                        <div className="border-t border-border pt-2 flex justify-between font-semibold">
                                          <span>Total Cost</span>
                                          <span className="text-primary">
                                            ${(subtotal + fee).toFixed(2)}
                                          </span>
                                        </div>
                                      </div>

                                      <p className="text-xs text-muted-foreground">
                                        The seller receives the full unit price; the purchase fee is
                                        charged on top. Paid instantly from your wallet balance.
                                      </p>

                                      <Button
                                        className="w-full"
                                        disabled={
                                          !buyQty ||
                                          buyQty > listing.units_remaining ||
                                          buyMutation.isPending
                                        }
                                        onClick={() =>
                                          buyMutation.mutate({
                                            listingId: listing.listing_id,
                                            units: buyQty,
                                          })
                                        }
                                      >
                                        {buyMutation.isPending ? "Processing…" : "Confirm Purchase"}
                                      </Button>
                                    </div>
                                  </DialogContent>
                                </Dialog>
                              </div>
                            </div>
                          </div>
                        </Card>
                      );
                    })}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="sell" className="space-y-6">
                <SellUnitsForm />
              </TabsContent>

              <TabsContent value="activity" className="space-y-4">
                <Card className="bg-card border-border">
                  <CardHeader>
                    <CardTitle>Your Listings</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {(mine?.items ?? []).length === 0 ? (
                      <div className="py-10 text-center text-sm text-muted-foreground">
                        You have no listings yet. Use the “Sell Units” tab to list units you own.
                      </div>
                    ) : (
                      <div className="space-y-4">
                        {(mine?.items ?? []).map((l) => (
                          <div
                            key={l.listing_id}
                            className="flex items-center justify-between p-4 rounded-lg bg-muted/30 border border-border/50"
                          >
                            <div className="flex items-center gap-4">
                              <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                                <Tag className="h-5 w-5 text-primary" />
                              </div>
                              <div>
                                <p className="font-medium">{l.property_title ?? "Property"}</p>
                                <p className="text-sm text-muted-foreground">
                                  {l.units_remaining}/{l.units_for_sale} units left • $
                                  {Number(l.price_per_unit).toLocaleString()}/unit
                                </p>
                              </div>
                            </div>
                            <div className="text-right flex items-center gap-3">
                              <Badge variant="outline" className="capitalize">
                                {l.status}
                              </Badge>
                              {l.status === "active" && (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="text-destructive hover:text-destructive"
                                  onClick={async () => {
                                    try {
                                      await secondaryApi.cancel(l.listing_id);
                                      toast.success("Listing cancelled");
                                      queryClient.invalidateQueries({ queryKey: ["secondary"] });
                                    } catch (err) {
                                      const msg =
                                        err instanceof ApiError ? err.message : "Could not cancel.";
                                      toast.error("Cancel failed", { description: msg });
                                    }
                                  }}
                                >
                                  Cancel
                                </Button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </div>
        </section>
      </main>
    </div>
  );
};

export default SecondaryMarket;
