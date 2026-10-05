import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Building2, CalendarClock, Clock, MapPin, TrendingDown, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { ApiError, secondaryApi, type SecondaryListing } from "@/lib/api";
import { money, shortDate, unitPrice } from "@/lib/money";

const installmentLabel = (kind: string, seq: number) =>
  kind === "final" ? `Final (month ${seq})` : `Month ${seq}`;

/**
 * A listing that offers a whole installment plan POSITION (not loose units): every unit of
 * the plan, paid for or not, sold together. The buyer pays the seller now what has been paid
 * on the plan plus the price change on all its units since it started (`cash`), and then
 * pays the remaining installments on their dates. What the seller paid someone else for the
 * position, if they bought it, is not shown to buyers. Nothing here computes money: every figure comes from the server, and the
 * purchase sends back the amount shown so a changed position is never charged unseen.
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
  const pos = listing.position!;
  const price = Number(listing.price_per_unit);
  const ref = listing.unit_price_ref ? Number(listing.unit_price_ref) : 0;
  const change = ref > 0 ? ((price - ref) / ref) * 100 : 0;
  const toTakeOver = Number(pos.remaining_principal) + Number(pos.remaining_fees);

  const buy = useMutation({
    mutationFn: () =>
      secondaryApi.buy(
        listing.listing_id,
        listing.units_remaining,
        crypto.randomUUID(),
        pos.cash,
        pos.resale_fee,
      ),
    onSuccess: (trade) => {
      toast.success("Position bought", {
        description: `You paid ${money(trade.total_charged)} (incl. fee) and took over the plan. Its installments are in your dashboard.`,
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
              <p className="text-xs text-muted-foreground">Units (sold together)</p>
              <p className="text-sm font-semibold">
                {pos.units} <span className="font-normal text-muted-foreground">· {pos.vested_units} paid for</span>
              </p>
            </div>
            <div className="p-2 rounded-lg bg-primary/10">
              <p className="text-xs text-muted-foreground">You pay the seller now</p>
              <p className="text-sm font-semibold text-primary">{money(pos.cash)}</p>
            </div>
            <div className="p-2 rounded-lg bg-muted/50">
              <p className="text-xs text-muted-foreground">Then {pos.installments_left} installment(s)</p>
              <p className="text-sm font-semibold">{money(toTakeOver)}</p>
              <p className="text-[11px] text-muted-foreground">next {shortDate(pos.next_due)}</p>
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
                if (!next) setAgreed(false);
              }}
            >
              <Button onClick={() => setOpen(true)}>View &amp; Buy</Button>
              <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
                <DialogHeader>
                  <DialogTitle>Installment position — {listing.property_title ?? "Property"}</DialogTitle>
                  <DialogDescription>
                    You buy the whole position: {pos.units} units at {unitPrice(price)} each. You pay the seller
                    what has been paid on the plan plus the change in the price since it started, and you carry
                    on with the remaining installments. The {pos.vested_units} unit(s) already paid for are
                    yours at once; the others become yours as you pay.
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-2" data-testid="position-buy">
                  <div className="p-4 rounded-lg bg-muted/50 space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">
                        Position value ({pos.units} × {unitPrice(price)})
                      </span>
                      <span className="font-medium">{money(pos.value)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Still to pay on the plan (you take it over)</span>
                      <span className="font-medium">−{money(pos.remaining_principal)}</span>
                    </div>
                    <div className="border-t border-border pt-2 flex justify-between font-semibold">
                      <span>You pay the seller now</span>
                      <span>{money(pos.cash)}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      = {money(pos.paid_principal)} paid on the plan
                      {Number(pos.gain) !== 0 &&
                        ` ${Number(pos.gain) > 0 ? "+" : "−"} ${money(Math.abs(Number(pos.gain)))} price ${
                          Number(pos.gain) > 0 ? "increase" : "decrease"
                        } on all ${pos.units} units since it started`}
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
                    <div className="rounded-lg border border-border overflow-hidden">
                      <table className="w-full text-xs">
                        <thead className="bg-muted/50 text-muted-foreground">
                          <tr>
                            <th className="text-left font-medium p-2">Payment</th>
                            <th className="text-left font-medium p-2">Due</th>
                            <th className="text-right font-medium p-2">Amount (incl. fee)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {pos.schedule.map((row) => (
                            <tr key={row.seq} className="border-t border-border/60">
                              <td className="p-2">{installmentLabel(row.kind, row.seq)}</td>
                              <td className="p-2">{shortDate(row.due_date)}</td>
                              <td className="p-2 text-right font-medium">{money(row.total_amount)}</td>
                            </tr>
                          ))}
                          <tr className="border-t border-border bg-muted/30 font-semibold">
                            <td className="p-2" colSpan={2}>
                              Total still to pay
                            </td>
                            <td className="p-2 text-right">{money(toTakeOver)}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
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
                      I am buying the whole position and I take over the remaining {pos.installments_left}{" "}
                      installment(s), {money(toTakeOver)} in all.
                    </span>
                  </label>

                  <Button className="w-full" disabled={!agreed || buy.isPending} onClick={() => buy.mutate()}>
                    {buy.isPending ? "Processing…" : `Pay ${money(pos.total_now)} and take over the plan`}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>
    </Card>
  );
}
