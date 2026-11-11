import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { ApiError, liquidityApi, type LpExitRequest, type LpPlanUnits } from "@/lib/api";
import { money, unitPrice } from "@/lib/money";
import PlanPartSchedule from "@/components/marketplace/PlanPartSchedule";

/**
 * Funding an exit request for units of a running installment plan. The provider pays the
 * discounted value of the units less their share of the principal still to pay, and takes that
 * share of the installments over, as a plan of their own (all the plan's units: the plan
 * itself). Every figure is the server's (the request, or a quote for the units chosen), and the
 * funding sends back the cash shown, so a changed amount (the seller paid an installment
 * meanwhile) is never charged unseen.
 */
export default function PlanUnitsFund({ request, onDone }: { request: LpExitRequest; onDone: () => void }) {
  const queryClient = useQueryClient();
  const all = request.units_remaining;
  const [unitsText, setUnitsText] = useState(String(all));
  const [agreed, setAgreed] = useState(false);
  const units = Math.floor(Number(unitsText) || 0);
  const valid = units >= 1 && units <= all;
  const offered = request.position!;
  const partial = valid && units !== all;
  const quote = useQuery({
    queryKey: ["liquidity", "quote", request.request_id, units],
    queryFn: () => liquidityApi.quotePlan(request.request_id, units),
    enabled: partial,
    staleTime: 0,
  });
  const pos: LpPlanUnits | undefined = partial ? quote.data : offered;
  const whole = valid && units === offered.plan_units;
  const toTakeOver = pos ? Number(pos.remaining_principal) + Number(pos.remaining_fees) : 0;

  const fund = useMutation({
    mutationFn: () => liquidityApi.fund(request.request_id, units, crypto.randomUUID(), pos!.cash),
    onSuccess: (position) => {
      toast.success("Liquidity deployed", {
        description: `You acquired ${position.units_acquired} unit(s) on an installment plan for ${money(position.principal)}. The plan and its installments are in your dashboard.`,
      });
      queryClient.invalidateQueries({ queryKey: ["liquidity"] });
      queryClient.invalidateQueries({ queryKey: ["wallet"] });
      queryClient.invalidateQueries({ queryKey: ["installments"] });
      onDone();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "POSITION_CHANGED") {
        setAgreed(false);
        queryClient.invalidateQueries({ queryKey: ["liquidity"] });
      }
      toast.error("Funding failed", {
        description: err instanceof ApiError ? err.message : "Could not fund this request.",
      });
    },
  });

  return (
    <div className="space-y-3 py-2" data-testid="plan-units-fund">
      <p className="text-sm text-muted-foreground">
        These units are on an installment plan. You pay the seller their value at the liquidity price less their
        share of what is still to pay, then you pay that share of the installments on their dates, as a plan in
        your name.
      </p>
      {all > 1 && (
        <div className="space-y-1.5">
          <Label htmlFor="plan-fund-units">Units to fund (1–{all})</Label>
          <Input
            id="plan-fund-units"
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
        </div>
      )}
      {!valid && <p className="text-sm text-destructive">Choose between 1 and {all} units.</p>}
      {partial && quote.isLoading && <p className="text-sm text-muted-foreground">Working out the amounts…</p>}
      {partial && quote.isError && (
        <p className="text-sm text-destructive">
          {quote.error instanceof ApiError ? quote.error.message : "Could not work out the amounts."}
        </p>
      )}
      {valid && pos && (
        <>
          <div className="p-3 rounded-lg bg-muted/40 space-y-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">
                Value at the liquidity price ({pos.units} × {unitPrice(pos.lp_unit_price)})
              </span>
              <span className="font-medium">{money(pos.lp_value)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Still to pay on these units (you take it over)</span>
              <span className="font-medium">−{money(pos.remaining_principal)}</span>
            </div>
            <div className="border-t border-border pt-1.5 flex justify-between font-semibold">
              <span>You pay now</span>
              <span className="text-primary">{money(pos.cash)}</span>
            </div>
            <p className="text-xs text-muted-foreground">
              {pos.vested_units} of the {pos.units} unit(s) are paid for and yours at once; the others become yours as
              you pay.
            </p>
          </div>
          <div>
            <p className="text-sm font-medium mb-2">Installments you take over ({pos.installments_left})</p>
            <PlanPartSchedule schedule={pos.schedule} testId="plan-fund-schedule" />
          </div>
          <label className="flex items-start gap-2 text-sm cursor-pointer">
            <Checkbox
              checked={agreed}
              onCheckedChange={(v) => setAgreed(v === true)}
              className="mt-0.5"
              aria-label="I take over the remaining installments"
            />
            <span>
              I take over the remaining {pos.installments_left} installment(s) of these units, {money(toTakeOver)} in
              all{whole ? " (the whole plan)" : ""}.
            </span>
          </label>
          <Button className="w-full gap-1" disabled={!agreed || fund.isPending} onClick={() => fund.mutate()}>
            {fund.isPending ? "Processing…" : `Pay ${money(pos.cash)} and take over ${pos.units} unit(s)`}
            <ArrowRight className="w-4 h-4" />
          </Button>
        </>
      )}
    </div>
  );
}
