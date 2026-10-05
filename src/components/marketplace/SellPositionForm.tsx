import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CalendarClock, CheckCircle, Info } from "lucide-react";
import { toast } from "sonner";
import { ApiError, secondaryApi, type MyPosition } from "@/lib/api";
import { money, shortDate, unitPrice } from "@/lib/money";

/** A position sale prepared elsewhere (the Installments tab, or the assistant):
 * /secondary-market?tab=sell&plan=<plan id>[&price=P] */
export type PositionPrefill = { planId: string; price?: number };

const BLOCKED: Record<string, (p: MyPosition) => string> = {
  pledged: () =>
    "This plan was started with a Nova Sukuk certificate: its units are pledged to Nova Finance until the pledge is released.",
  lockup: (p) => `This position is in a lock-up until ${shortDate(p.lockup_until)}.`,
  listed: () => "This position is already listed for sale. Cancel that listing under My Listings to change its price.",
};

/**
 * Selling a running installment plan as one position. The units of a plan are not listed
 * one by one: the whole plan changes hands. The buyer pays the seller the position's value at
 * the asking price less the principal still to pay (what the seller paid plus the increase on
 * every unit) and takes over the remaining installments. The amounts previewed here are the
 * server's formula; the listing the server returns is what counts.
 */
function PositionRow({
  position,
  feePct,
  prefillPrice,
  prepared,
}: {
  position: MyPosition;
  feePct: number;
  prefillPrice?: number;
  prepared: boolean;
}) {
  const queryClient = useQueryClient();
  const [price, setPrice] = useState(String(prefillPrice ?? Number(position.unit_price)));
  // cents, as the server keeps it: the preview and the listing use the same price
  const asking = Math.round((parseFloat(price) || 0) * 100) / 100;
  const remaining = Number(position.remaining_principal);
  // what the seller has put in: their installments, or what they paid to take the plan over
  // plus their installments since
  const paid = Number(position.cost);
  const value = asking * position.units;
  const youReceive = value - remaining;
  const gain = youReceive - paid;
  const minimum = remaining / position.units;
  const blocked = position.blocked ? BLOCKED[position.blocked]?.(position) : null;

  const create = useMutation({
    mutationFn: () => secondaryApi.create({ plan_id: position.plan_id, price_per_unit: asking }),
    onSuccess: (listing) => {
      toast.success("Position listed", {
        description: `A buyer pays you ${money(listing.position?.cash ?? youReceive)} and takes over the remaining installments.`,
      });
      queryClient.invalidateQueries({ queryKey: ["secondary"] });
      queryClient.invalidateQueries({ queryKey: ["installments"] });
    },
    onError: (err) => {
      toast.error("Listing failed", {
        description: err instanceof ApiError ? err.message : "Could not create the listing.",
      });
    },
  });

  return (
    <div className="rounded-xl border border-border p-4 space-y-4" data-testid="position-row">
      {prepared && !blocked && (
        <div
          data-testid="position-prepared-banner"
          className="rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-sm"
        >
          <div className="font-semibold text-primary">Ready to list</div>
          <div className="text-xs text-muted-foreground">
            Check the price, then press List this position yourself. Nothing is listed before that.
          </div>
        </div>
      )}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-foreground">{position.property_title ?? "Property"}</p>
          <p className="text-xs text-muted-foreground">
            {position.units} units on the plan · {position.vested_units} paid for · {position.installments_left}{" "}
            installment(s) left
            {position.next_due ? `, next ${shortDate(position.next_due)}` : ""}
          </p>
        </div>
        <Badge variant="outline" className="shrink-0">
          Bought at {unitPrice(position.entry_price)} · now {unitPrice(position.unit_price)}
        </Badge>
      </div>

      {blocked ? (
        <div className="flex items-start gap-2 rounded-lg bg-muted/50 p-3 text-sm text-muted-foreground">
          <Info className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{blocked}</span>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor={`price-${position.plan_id}`}>Asking price per unit ($)</Label>
              <Input
                id={`price-${position.plan_id}`}
                type="number"
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Current unit price: {unitPrice(position.unit_price)}. Must be above $
                {minimum.toFixed(2)} to cover what is still to pay.
              </p>
            </div>
            <div className="rounded-lg bg-secondary/50 p-3 space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">
                  Position value ({position.units} × {unitPrice(asking)})
                </span>
                <span className="font-medium">{money(value)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Still to pay (the buyer takes it over)</span>
                <span className="font-medium">−{money(remaining)}</span>
              </div>
              <div className="border-t border-border pt-1.5 flex justify-between font-semibold">
                <span>You receive</span>
                <span className={youReceive > 0 ? "text-primary" : "text-destructive"}>{money(youReceive)}</span>
              </div>
              {youReceive > 0 && (
                <p className="text-xs text-muted-foreground">
                  = {money(paid)} you put in {gain >= 0 ? "+" : "−"} {money(Math.abs(gain))} price{" "}
                  {gain >= 0 ? "increase" : "decrease"} on all {position.units} units. Installment fees
                  you paid are not returned. The buyer pays a {feePct}% fee on top.
                </p>
              )}
            </div>
          </div>
          <Button
            className="w-full gap-2"
            disabled={!(youReceive > 0) || create.isPending}
            onClick={() => create.mutate()}
          >
            <CheckCircle className="h-4 w-4" />
            {create.isPending ? "Listing…" : "List this position"}
            {youReceive > 0 && (
              <Badge variant="secondary" className="ml-2">
                Receive {money(youReceive)}
              </Badge>
            )}
          </Button>
        </>
      )}
    </div>
  );
}

const SellPositionForm = ({ prefill = null }: { prefill?: PositionPrefill | null }) => {
  const { data } = useQuery({ queryKey: ["secondary", "positions"], queryFn: () => secondaryApi.positions() });
  const { data: settings } = useQuery({ queryKey: ["secondary", "settings"], queryFn: () => secondaryApi.settings() });
  const cardRef = useRef<HTMLDivElement>(null);
  const positions = data?.items ?? [];
  useEffect(() => {
    if (prefill && positions.length) cardRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [prefill, positions.length]);
  if (!positions.length) return null;
  const feePct = settings ? Number(settings.resale_fee_pct) : 1.0;
  // the one asked for first
  const ordered = [...positions].sort(
    (a, b) => Number(b.plan_id === prefill?.planId) - Number(a.plan_id === prefill?.planId),
  );
  return (
    <Card ref={cardRef} className="bg-card border-border scroll-mt-24" data-testid="sell-positions">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarClock className="h-5 w-5 text-primary" />
          Sell an Installment Position
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Units you are still paying for are sold with their plan, as one position. The buyer pays you the
          principal you have paid plus the price change on all the units, and takes over the remaining
          installments.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {ordered.map((p) => (
          <PositionRow
            key={p.plan_id}
            position={p}
            feePct={feePct}
            prefillPrice={p.plan_id === prefill?.planId ? prefill.price : undefined}
            prepared={p.plan_id === prefill?.planId}
          />
        ))}
      </CardContent>
    </Card>
  );
};

export default SellPositionForm;
