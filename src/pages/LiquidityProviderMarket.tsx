import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Droplets,
  TrendingUp,
  Wallet,
  Zap,
  Building2,
  Activity,
  Shield,
  Clock,
  ArrowRight,
  Filter,
  CheckCircle2,
  GraduationCap,
  Sparkles,
  Layers,
  BarChart3,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { ApiError, liquidityApi, type LpExitRequest } from "@/lib/api";

const num = (s: string | null | undefined) => Number(s ?? 0);

function timeLeft(iso: string | null): string {
  if (!iso) return "—";
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "expired";
  const h = Math.floor(ms / 3_600_000);
  if (h >= 1) return `${h}h left`;
  return `${Math.max(1, Math.floor(ms / 60_000))}m left`;
}

export default function LiquidityProviderMarket() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<LpExitRequest | null>(null);
  const [fundUnits, setFundUnits] = useState("");

  const { data: openData } = useQuery({
    queryKey: ["liquidity", "open"],
    queryFn: () => liquidityApi.listOpen(),
  });
  const { data: positionsData } = useQuery({
    queryKey: ["liquidity", "positions"],
    queryFn: () => liquidityApi.positions(),
  });

  const requests = useMemo(() => {
    const rows = openData?.items ?? [];
    if (!search.trim()) return rows;
    const q = search.toLowerCase();
    return rows.filter(
      (r) =>
        (r.property_title ?? "").toLowerCase().includes(q) ||
        (r.property_location ?? "").toLowerCase().includes(q),
    );
  }, [openData, search]);

  const fundMutation = useMutation({
    mutationFn: ({ id, units }: { id: string; units: number }) =>
      liquidityApi.fund(id, units, crypto.randomUUID()),
    onSuccess: (pos) => {
      toast.success("Liquidity deployed", {
        description: `You acquired ${pos.units_acquired} unit(s) for $${num(pos.principal).toLocaleString()}.`,
      });
      setSelected(null);
      setFundUnits("");
      queryClient.invalidateQueries({ queryKey: ["liquidity"] });
      queryClient.invalidateQueries({ queryKey: ["wallet"] });
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? err.message : "Could not fund this request.";
      toast.error("Funding failed", { description: msg });
    },
  });

  const stats = useMemo(() => {
    const rows = openData?.items ?? [];
    const totalLp = rows.reduce((s, r) => s + num(r.lp_price), 0);
    const props = new Set(rows.map((r) => r.property_id)).size;
    const active = (positionsData?.items ?? []).length;
    return [
      { label: "Open Exit Requests", value: String(rows.length), icon: Clock, sub: "Fundable now" },
      { label: "Capital Required", value: `$${totalLp.toLocaleString()}`, icon: Layers, sub: "Across open requests" },
      { label: "Properties", value: String(props), icon: Building2, sub: "Distinct assets" },
      { label: "My Active Positions", value: String(active), icon: Activity, sub: "Acquired via LP" },
    ];
  }, [openData, positionsData]);

  const fundQty = parseInt(fundUnits) || 0;

  return (
    <div className="min-h-screen bg-background">
      {/* Hero */}
      <section className="relative border-b border-border bg-gradient-to-br from-primary/5 via-background to-accent/5">
        <div className="container mx-auto px-4 py-10 md:py-14">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
            <div>
              <Badge variant="outline" className="border-primary/30 text-primary mb-3">
                <Droplets className="w-3 h-3 mr-1" /> Institutional Marketplace
              </Badge>
              <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-2">
                Liquidity Provider Market
              </h1>
              <p className="text-muted-foreground max-w-2xl">
                Fund investor instant-exit requests at a transparent liquidity discount —
                acquire the ownership, earn rental as the new owner, and resell on the secondary market.
              </p>
            </div>
          </div>
        </div>
      </section>

      <div className="container mx-auto px-4 py-8 space-y-8">
        {/* Stats (live) */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {stats.map((s, i) => (
            <Card key={i} className="border-primary/10">
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <s.icon className="w-4 h-4 text-primary" />
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    {s.sub}
                  </span>
                </div>
                <div className="text-xl font-bold">{s.value}</div>
                <div className="text-xs text-muted-foreground">{s.label}</div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Marketplace */}
        <Tabs defaultValue="opportunities" className="space-y-4">
          <TabsList className="flex flex-wrap gap-2 h-auto p-2 bg-muted/50">
            <TabsTrigger value="opportunities" className="gap-2">
              <Zap className="w-4 h-4" /> Instant Exit Opportunities
            </TabsTrigger>
            <TabsTrigger value="positions" className="gap-2">
              <Layers className="w-4 h-4" /> My Positions
            </TabsTrigger>
            <TabsTrigger value="education" className="gap-2">
              <GraduationCap className="w-4 h-4" /> How It Works
            </TabsTrigger>
          </TabsList>

          {/* Opportunities (live order book) */}
          <TabsContent value="opportunities" className="space-y-4">
            <Card>
              <CardContent className="p-4 flex flex-col md:flex-row gap-3">
                <div className="flex-1 relative">
                  <Filter className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search property or location"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="pl-9"
                  />
                </div>
              </CardContent>
            </Card>

            {requests.length === 0 ? (
              <Card>
                <CardContent className="p-10 text-center text-sm text-muted-foreground">
                  No open exit requests right now. Check back soon.
                </CardContent>
              </Card>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {requests.map((req) => {
                  const gross = num(req.gross);
                  const lpPrice = num(req.lp_price);
                  const discount = gross > 0 ? ((gross - lpPrice) / gross) * 100 : 0;
                  return (
                    <Card key={req.request_id} className="border-primary/10 hover:border-primary/30 transition-colors">
                      <CardContent className="p-5 space-y-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center text-primary-foreground flex-shrink-0">
                              <Building2 className="w-5 h-5" />
                            </div>
                            <div className="min-w-0">
                              <div className="font-semibold truncate">{req.property_title ?? "Property"}</div>
                              <div className="text-xs text-muted-foreground truncate">
                                {req.property_location ?? "—"}
                              </div>
                            </div>
                          </div>
                          <Badge variant="outline" className="border-primary/30 text-primary">
                            <Clock className="w-3 h-3 mr-1" /> {timeLeft(req.expires_at)}
                          </Badge>
                        </div>

                        <div className="grid grid-cols-3 gap-3 text-sm">
                          <div>
                            <div className="text-xs text-muted-foreground">You pay</div>
                            <div className="font-semibold">${lpPrice.toLocaleString()}</div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground">Units</div>
                            <div className="font-semibold">{req.units_remaining}</div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground">Reference value</div>
                            <div className="font-semibold">${gross.toLocaleString()}</div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground">Discount</div>
                            <div className="font-semibold text-primary">{discount.toFixed(1)}%</div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground">Unit price</div>
                            <div className="font-semibold">${num(req.unit_price).toLocaleString()}</div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground">Liquidity fee</div>
                            <div className="font-semibold">{num(req.fee_pct)}%</div>
                          </div>
                        </div>

                        <div className="flex items-center justify-end pt-1">
                          <Button size="sm" className="gap-1" onClick={() => setSelected(req)}>
                            Review & Provide <ArrowRight className="w-3 h-3" />
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </TabsContent>

          {/* My Positions (live; acquisition audit) */}
          <TabsContent value="positions" className="space-y-3">
            <Card>
              <CardContent className="p-0 divide-y">
                {(positionsData?.items ?? []).length === 0 ? (
                  <div className="p-10 text-center text-sm text-muted-foreground">
                    No positions yet. Fund an exit request to acquire ownership.
                  </div>
                ) : (
                  (positionsData?.items ?? []).map((pos) => (
                    <div key={pos.position_id} className="flex items-center justify-between gap-3 p-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                          <Building2 className="w-4 h-4 text-primary" />
                        </div>
                        <div>
                          <div className="font-medium text-sm">
                            Acquired {pos.units_acquired} unit(s)
                          </div>
                          <div className="text-xs text-muted-foreground">
                            Principal ${num(pos.principal).toLocaleString()} ·{" "}
                            {pos.created_at ? new Date(pos.created_at).toLocaleDateString() : "—"}
                          </div>
                        </div>
                      </div>
                      <Badge variant="outline" className="border-primary/30 text-primary capitalize">
                        <CheckCircle2 className="w-3 h-3 mr-1" /> {pos.status}
                      </Badge>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
            <p className="text-xs text-muted-foreground px-1">
              This is an acquisition record (audit). Your current holdings and returns are tracked
              from the ownership ledger in your dashboard.
            </p>
          </TabsContent>

          {/* Education */}
          <TabsContent value="education" className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              {
                icon: Droplets,
                title: "What is a Liquidity Provider?",
                desc: "Liquidity providers deploy capital to fund instant exits, acquiring ownership allocations from investors who want to liquidate their property positions immediately.",
              },
              {
                icon: Zap,
                title: "How Instant Exits Work",
                desc: "An investor lists an instant-exit request at a transparent liquidity discount. You fund it, acquire the ownership at that discounted price, and the investor receives funds immediately.",
              },
              {
                icon: TrendingUp,
                title: "How Liquidity Generates Returns",
                desc: "You earn as the new owner: rental distributions on the acquired units, plus the spread when you resell those units on the secondary market.",
              },
              {
                icon: Shield,
                title: "Asset-Backed & Atomic",
                desc: "Ownership transfers atomically on settlement and is recorded on the ownership ledger. Funding is server-priced and the seller's payout is locked at request time.",
              },
              {
                icon: Sparkles,
                title: "Powering the Ecosystem",
                desc: "Liquidity providers keep the platform liquid for everyone — enabling investors to exit at any time and supporting healthy market activity.",
              },
            ].map((b, i) => (
              <Card key={i} className="border-primary/10">
                <CardHeader>
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                      <b.icon className="w-5 h-5 text-primary" />
                    </div>
                    <CardTitle className="text-base">{b.title}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground leading-relaxed">
                  {b.desc}
                </CardContent>
              </Card>
            ))}
          </TabsContent>
        </Tabs>
      </div>

      {/* Review / fund dialog */}
      <Dialog open={!!selected} onOpenChange={(o) => !o && (setSelected(null), setFundUnits(""))}>
        <DialogContent className="max-w-lg">
          {selected && (
            <>
              <DialogHeader>
                <DialogTitle>Provide liquidity — {selected.property_title ?? "Property"}</DialogTitle>
                <DialogDescription>
                  Review the asset-backed exit opportunity before allocating capital. Pricing is
                  server-set; the seller's payout is locked.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-3 py-2">
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="p-3 rounded-lg bg-muted/40">
                    <div className="text-xs text-muted-foreground">You pay / unit (discounted)</div>
                    <div className="font-semibold text-lg">
                      ${(num(selected.lp_price) / selected.units).toFixed(2)}
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/40">
                    <div className="text-xs text-muted-foreground">Reference unit price</div>
                    <div className="font-semibold text-lg">${num(selected.unit_price).toLocaleString()}</div>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>Units to fund (max {selected.units_remaining})</Label>
                  <Input
                    type="number"
                    min={1}
                    max={selected.units_remaining}
                    placeholder="Enter units"
                    value={fundUnits}
                    onChange={(e) => setFundUnits(e.target.value)}
                  />
                </div>
                <div className="text-xs text-muted-foreground p-3 rounded-lg border border-border">
                  <Shield className="w-3 h-3 inline mr-1 text-primary" />
                  Acquired ownership is recorded on the ownership ledger; you earn rental as the new
                  owner and can resell on the secondary market.
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setSelected(null)}>Cancel</Button>
                <Button
                  className="gap-1"
                  disabled={
                    !fundQty || fundQty > selected.units_remaining || fundMutation.isPending
                  }
                  onClick={() => fundMutation.mutate({ id: selected.request_id, units: fundQty })}
                >
                  {fundMutation.isPending ? "Processing…" : "Confirm Allocation"}
                  <ArrowRight className="w-4 h-4" />
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
