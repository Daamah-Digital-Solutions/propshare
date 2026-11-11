import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Building2, CalendarClock, Clock, MapPin, TrendingDown, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { ApiError, secondaryApi, type ListingPosition, type SecondaryListing } from "@/lib/api";
import { money, shortDate, unitPrice } from "@/lib/money";
import PlanPartSchedule from "@/components/marketplace/PlanPartSchedule";

/**
 * A listing that offers an installment plan POSITION (not loose units): the units of the plan,
 * paid for or not, with their installments. The listing can offer the whole plan or some of its
 * units, and a buyer can take all the units listed or only some: those become a plan of the
 * buyer's own, with the same dates and that share of every payment. The buyer pays the seller
 * now what has been paid on those units plus the price change since (`cash`), then pays their
 * installments on their dates. What the seller paid someone else for the position, if they
 * bought it, is not shown to buyers. Nothing here computes money: every figure comes from the
 * server (the listing, or a quote for the units chosen), and the purchase sends back the amount
 * shown so a changed position is never charged unseen.
 */
export default function PositionListingCard({
  listing,
  feePct,
  listedAgo,
}: {
  listing: SecondaryListing;
  feePct: number;
  listedAgo: string;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const all = listing.units_remaining;
  const [unitsText, setUnitsText] = useState(String(all));
  const units = Math.floor(Number(unitsText) || 0);
  const validUnits = units >= 1 && units <= all;
  const listed = listing.position!;
  const planUnits = listed.plan_units ?? listed.units;
  const price = Number(listing.price_per_unit);
  const ref = listing.unit_price_ref ? Number(listing.unit_price_ref) : 0;
  const change = ref > 0 ? ((price - ref) / ref) * 100 : 0;

  // every unit listed: the listing's own figures; fewer: the server's quote for that part
  const partial = validUnits && units !== all;
  const quote = useQuery({
    queryKey: ["secondary", "quote", listing.listing_id, units],
    queryFn: () => secondaryApi.quote(listing.listing_id, units),
    enabled: open && partial,
    staleTime: 0,
  });
  const pos: ListingPosition | undefined = partial ? quote.data : listed;
  const whole = validUnits && units === planUnits;
  const toTakeOver = pos ? Number(pos.remaining_principal) + Number(pos.remaining_fees) : 0;

  const buy = useMutation({
    mutationFn: () => secondaryApi.buy(listing.listing_id, units, crypto.randomUUID(), pos!.cash, pos!.resale_fee),
    onSuccess: (trade) => {
      toast.success("Position bought", {
        description: whole
          ? `You paid ${money(trade.total_charged)} (incl. fee) and took over the plan. Its installments are in your dashboard.`
          : `You paid ${money(trade.total_charged)} (incl. fee) for ${trade.units} unit(s). Your new plan and its installments are in your dashboard.`,
      });
      setOpen(false);
      setAgreed(false);
      queryClient.invalidateQueries({ queryKey: ["secondary"] });
      queryClient.invalidateQueries({ queryKey: ["wallet"] });
      queryClient.invalidateQueries({ queryKey: ["installments"] });
      queryClient.invalidateQueries({ queryKey: ["holdings"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "POSITION_CHANGED") {
        // the seller paid an installment meanwhile: show the new figures, ask again
        setAgreed(false);
        queryClient.invalidateQueries({ queryKey: ["secondary"] });
        toast.error("The amounts changed", {
          description: "The amounts of this position changed since you opened it. Check the new ones and confirm again.",
        });
        return;
      }
      toast.error("Purchase failed", {
        description: err instanceof ApiError ? err.message : "Purchase could not be completed.",
      });
    },
  });

  return (
    <Card
      className="bg-card border-border overflow-hidden hover:shadow-lg transition-shadow"
      data-testid="position-listing"
    >
      <div className="flex flex-col md:flex-row">
        <div className="md:w-1/3 bg-gradient-to-br from-primary/15 to-accent/10 flex items-center justify-center min-h-[12rem]">
          <Building2 className="h-12 w-12 text-primary/50" />
        </div>
        <div className="md:w-2/3 p-5">
          <div className="flex items-start justify-between mb-3 gap-2">
            <div>
              <h3 className="font-semibold text-foreground">{listing.property_title ?? "Property"}</h3>
              <div className="flex items-center gap-1 text-sm text-muted-foreground">
                <MapPin className="h-3 w-3" />
                {listing.property_location ?? "—"}
              </div>
            </div>
            <Badge variant="outline" className="bg-accent/10 text-foreground border-accent/30 shrink-0">
              <CalendarClock className="h-3 w-3 mr-1 text-accent" />
              Installment position
            </Badge>
          </div>

          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="p-2 rounded-lg bg-muted/50">
              <p className="text-xs text-muted-foreground">Price/Unit</p>
              <div className="flex items-center gap-1">
                <p className="text-sm font-semibold">{unitPrice(price)}</p>
                {ref > 0 &&
                  (change >= 0 ? (
                    <span className="text-xs text-primary flex items-center">
                      <TrendingUp className="h-3 w-3" />+{change.toFixed(1)}%
                    </span>
                  ) : (
                    <span className="text-xs text-destructive flex items-center">
                      <TrendingDown className="h-3 w-3" />
                      {change.toFixed(1)}%
                    </span>
                  ))}
              </div>
            </div>
            <div className="p-2 rounded-lg bg-muted/50">
              <p className="text-xs text-muted-foreground">Units for sale</p>
              <p className="text-sm font-semibold">
                {all} <span className="font-normal text-muted-foreground">of {planUnits} on the plan</span>
              </p>
              {all > 1 && <p className="text-[11px] text-muted-foreground">You can buy some of them</p>}
            </div>
            <div className="p-2 rounded-lg bg-primary/10">
              <p className="text-xs text-muted-foreground">You pay the seller now</p>
              <p className="text-sm font-semibold text-primary">{money(listed.cash)}</p>
            </div>
            <div className="p-2 rounded-lg bg-muted/50">
              <p className="text-xs text-muted-foreground">Then {listed.installments_left} installment(s)</p>
              <p className="text-sm font-semibold">
                {money(Number(listed.remaining_principal) + Number(listed.remaining_fees))}
              </p>
              <p className="text-[11px] text-muted-foreground">next {shortDate(listed.next_due)}</p>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="h-4 w-4" />
              {listedAgo}
            </div>
            <Dialog
              open={open}
              onOpenChange={(next) => {
                setOpen(next);
                if (!next) {
                  setAgreed(false);
                  setUnitsText(String(all));
                }
              }}
            >
              <Button onClick={() => setOpen(true)}>View &amp; Buy</Button>
              <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
                <DialogHeader>
                  <DialogTitle>Installment position — {listing.property_title ?? "Property"}</DialogTitle>
                  <DialogDescription>
                    You pay the seller what has been paid on these units plus the change in their price since
                    the plan started, and you carry on with their installments. The units already paid for are
                    yours at once; the others become yours as you pay.
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-2" data-testid="position-buy">
                  {all > 1 && (
                    <div className="space-y-1.5">
                      <Label htmlFor={`units-${listing.listing_id}`}>How many units (1–{all})</Label>
                      <Input
                        id={`units-${listing.listing_id}`}
                        data-testid="position-units"
                        type="number"
                        min={1}
                        max={all}
                        step={1}
                        value={unitsText}
                        onChange={(e) => {
                          setUnitsText(e.target.value);
                          setAgreed(false);
                        }}
                      />
                      <p className="text-xs text-muted-foreground">
                        {whole
                          ? "All the plan's units: the plan itself becomes yours."
                          : `Part of the plan: these units become an installment plan in your name, with the same dates and their share of every payment. The seller keeps the rest.`}
                      </p>
                    </div>
                  )}
                  {!validUnits && <p className="text-sm text-destructive">Choose between 1 and {all} units.</p>}
                  {partial && quote.isLoading && <p className="text-sm text-muted-foreground">Working out the amounts…</p>}
                  {partial && quote.isError && (
                    <p className="text-sm text-destructive">
                      {quote.error instanceof ApiError ? quote.error.message : "Could not work out the amounts."}
                    </p>
                  )}
                  {validUnits && pos && (
                    <>
                      <div className="p-4 rounded-lg bg-muted/50 space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">
                            Value ({pos.units} × {unitPrice(price)})
                          </span>
                          <span className="font-medium">{money(pos.value)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Still to pay on these units (you take it over)</span>
                          <span className="font-medium">−{money(pos.remaining_principal)}</span>
                        </div>
                        <div className="border-t border-border pt-2 flex justify-between font-semibold">
                          <span>You pay the seller now</span>
                          <span>{money(pos.cash)}</span>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          = {money(pos.paid_principal)} paid on these units
                          {Number(pos.gain) !== 0 &&
                            ` ${Number(pos.gain) > 0 ? "+" : "−"} ${money(Math.abs(Number(pos.gain)))} price ${
                              Number(pos.gain) > 0 ? "increase" : "decrease"
                            } on ${pos.units} units since the plan started`}
                        </p>
                      </div>

                      <div className="p-4 rounded-lg bg-secondary/50 space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Paid to the seller</span>
                          <span className="font-medium">{money(pos.cash)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Purchase Fee ({feePct}%)</span>
                          <span className="font-medium">+{money(pos.resale_fee)}</span>
                        </div>
                        <div className="border-t border-border pt-2 flex justify-between font-semibold">
                          <span>Charged from your wallet now</span>
                          <span className="text-primary">{money(pos.total_now)}</span>
                        </div>
                      </div>

                      <div>
                        <p className="text-sm font-medium mb-2">
                          Installments you take over ({pos.installments_left})
                          {pos.overdue > 0 && (
                            <span className="ml-2 text-xs font-normal text-destructive">
                              {pos.overdue} already due: charged at the next automatic charge
                            </span>
                          )}
                        </p>
                        <PlanPartSchedule schedule={pos.schedule} />
                        <p className="mt-2 text-xs text-muted-foreground">
                          Each installment is charged from your wallet automatically on its date (you can also pay
                          early). There is no late fee; a missed payment is retried once your wallet is funded.
                        </p>
                      </div>

                      <label className="flex items-start gap-2 text-sm cursor-pointer">
                        <Checkbox
                          checked={agreed}
                          onCheckedChange={(v) => setAgreed(v === true)}
                          className="mt-0.5"
                          aria-label="I take over the remaining installments"
                        />
                        <span>
                          I am buying {pos.units} unit(s) and I take over their remaining {pos.installments_left}{" "}
                          installment(s), {money(toTakeOver)} in all.
                        </span>
                      </label>

                      <Button className="w-full" disabled={!agreed || buy.isPending} onClick={() => buy.mutate()}>
                        {buy.isPending
                          ? "Processing…"
                          : whole
                            ? `Pay ${money(pos.total_now)} and take over the plan`
                            : `Pay ${money(pos.total_now)} for ${pos.units} unit(s)`}
                      </Button>
                    </>
                  )}
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>
    </Card>
  );
}
