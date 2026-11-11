import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Info, Zap } from "lucide-react";
import { toast } from "sonner";
import { ApiError, liquidityApi, type MyPosition } from "@/lib/api";
import { money, unitPrice } from "@/lib/money";
import { cn } from "@/lib/utils";

/** Cents, rounded half up like the server. */
const cents = (n: number) => Math.round(n * 100 + 1e-6) / 100;

/**
 * Offering units of a running installment plan (some, or all) to liquidity providers. A
 * provider pays the discounted value of the units less their share of the principal still to
 * pay, which the provider takes over; the liquidity fee comes off that. The preview uses the
 * server's formula; the request the server returns is what counts. Units of a plan are offered
 * only when no installment is overdue.
 */
export default function PlanLiquidityExit({
  plans,
  discountPct,
  feePct,
  onDone,
}: {
  plans: MyPosition[];
  discountPct: number | null;
  feePct: number | null;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [planId, setPlanId] = useState(plans[0]?.plan_id ?? "");
  const plan = plans.find((p) => p.plan_id === planId) ?? plans[0];
  const free = plan ? (plan.free_units ?? plan.units) : 0;
  const [unitsText, setUnitsText] = useState(String(free));
  const units = Math.floor(Number(unitsText) || 0);
  const valid = !!plan && units >= 1 && units <= free;
  const overdue = plan ? Number(plan.overdue_amount ?? 0) : 0;

  let figures: { lpValue: number; remaining: number; cash: number; fee: number; net: number } | null = null;
  if (plan && valid && discountPct != null && feePct != null) {
    const gross = cents(units * Number(plan.unit_price));
    const lpValue = cents((gross * (100 - discountPct)) / 100);
    const remaining = cents((Number(plan.remaining_principal) * units) / plan.units);
    const cash = cents(lpValue - remaining);
    const fee = cash > 0 ? cents((cash * feePct) / 100) : 0;
    figures = { lpValue, remaining, cash, fee, net: cents(cash - fee) };
  }

  const create = useMutation({
    mutationFn: () => liquidityApi.createExitRequest({ plan_id: plan!.plan_id, units }),
    onSuccess: (req) => {
      toast.success("Instant-exit request listed", {
        description: `${units} unit(s) of ${plan?.property_title ?? "the property"} on your installment plan are now available to liquidity providers. You would receive ${money(req.position?.seller_net ?? req.seller_net)}.`,
      });
      queryClient.invalidateQueries({ queryKey: ["liquidity"] });
      queryClient.invalidateQueries({ queryKey: ["secondary"] });
      onDone();
    },
    onError: (err) => {
      toast.error("Exit request failed", {
        description: err instanceof ApiError ? err.message : "Could not submit your exit request.",
      });
    },
  });

  if (!plan) return null;
  return (
    <div className="mt-3 space-y-3" data-testid="plan-lp-exit">
      {plans.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {plans.map((p) => (
            <button
              key={p.plan_id}
              type="button"
              onClick={() => {
                setPlanId(p.plan_id);
                setUnitsText(String(p.free_units ?? p.units));
              }}
              className={cn(
                "rounded-md border px-2.5 py-1 text-xs",
                p.plan_id === plan.plan_id ? "border-primary bg-primary/10 text-primary" : "border-border",
              )}
            >
              {p.property_title ?? "Property"} · {p.units} units
            </button>
          ))}
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="plan-lp-units">
          Units of the {plan.property_title ?? "property"} plan to offer (1–{free})
        </Label>
        <Input
          id="plan-lp-units"
          type="number"
          min={1}
          max={free}
          step={1}
          value={unitsText}
          onChange={(e) => setUnitsText(e.target.value)}
        />
        {free < plan.units && (
          <p className="text-xs text-muted-foreground">
            {plan.units - free} unit(s) of this plan are already offered (listed, or to a liquidity provider).
          </p>
        )}
      </div>
      {overdue > 0 ? (
        <div className="flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
          <Info className="h-4 w-4 shrink-0 mt-0.5" />
          <span>
            {money(overdue)} of this plan's installments are overdue. Pay them first, then you can offer its units.
          </span>
        </div>
      ) : (
        figures && (
          <div className="rounded-lg bg-secondary/50 p-3 space-y-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">
                Value at the liquidity price ({units} ×{" "}
                {unitPrice(cents((Number(plan.unit_price) * (100 - (discountPct ?? 0))) / 100))})
              </span>
              <span className="font-medium">{money(figures.lpValue)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Still to pay on these units (the provider takes it over)</span>
              <span className="font-medium">−{money(figures.remaining)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Liquidity fee ({feePct}%)</span>
              <span className="font-medium">−{money(figures.fee)}</span>
            </div>
            <div className="border-t border-border pt-1.5 flex justify-between font-semibold">
              <span>You receive</span>
              <span className={figures.net > 0 ? "text-primary" : "text-destructive"}>{money(figures.net)}</span>
            </div>
            <p className="text-xs text-muted-foreground">
              {units === plan.units
                ? "The provider takes over the whole plan and its remaining installments."
                : `Your plan keeps ${plan.units - units} unit(s); each of its remaining installments goes down by the provider's share.`}
            </p>
            {figures.cash <= 0 && (
              <p className="text-xs text-destructive">
                At the liquidity price these units do not cover what is still to pay on them. You can sell them on
                the secondary market instead.
              </p>
            )}
          </div>
        )
      )}
      <Button
        className="w-full gap-1.5"
        disabled={!valid || overdue > 0 || !figures || figures.cash <= 0 || create.isPending}
        onClick={() => create.mutate()}
      >
        <Zap className="h-4 w-4" />
        {create.isPending ? "Submitting…" : `Offer ${valid ? units : ""} unit(s) to liquidity providers`}
      </Button>
    </div>
  );
}
