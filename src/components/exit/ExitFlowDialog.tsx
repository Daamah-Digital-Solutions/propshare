import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { cn } from "@/lib/utils";
import {
  ArrowRightLeft,
  Zap,
  ArrowLeft,
  CalendarClock,
  CheckCircle2,
  Clock,
  TrendingUp,
  Building2,
  Sparkles,
  Wallet,
  Shield,
  DollarSign,
  ChevronRight,
} from "lucide-react";
import { toast } from "sonner";
import { ApiError, liquidityApi, secondaryApi, type MyPosition } from "@/lib/api";
import { money } from "@/lib/money";
import {
  useCreateExitRequest,
  useCreateListing,
  useOwnedPositions,
  type ExitMethod,
  type OwnedPosition,
} from "./exitStore";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** Optional: pre-select a position (e.g. when launched from a property page). */
  initialPositionId?: string | number;
}

type Step = "method" | "select" | "summary" | "done";

// The platform's own rates (admin-configurable), never literals: a seller on the secondary
// market is paid in full and the BUYER pays the resale fee on top; a liquidity provider buys
// below the unit price and the liquidity fee is taken from that price.
type Rates = {
  resalePct: number | null;
  lpDiscountPct: number | null;
  lpFeePct: number | null;
  lpMinutes: number | null;
};
// The rates need a session (and a moment to load): a sentence must stand without its number.
const pct = (n: number | null) => (n == null ? "" : `${n}% `);
/** Cents, rounded half up like the server (97.485 is 97.49, which a binary float misses). */
const cents = (n: number) => Math.round(n * 100 + 1e-6) / 100;
const openFor = (minutes: number | null) =>
  minutes == null
    ? "a limited time"
    : minutes >= 120 && minutes % 60 === 0
      ? `${minutes / 60} hours`
      : `${minutes} minutes`;

function useExitRates(enabled: boolean): Rates {
  const { data: sec } = useQuery({
    queryKey: ["secondary", "settings"],
    queryFn: () => secondaryApi.settings(),
    enabled,
  });
  const { data: liq } = useQuery({
    queryKey: ["liquidity", "settings"],
    queryFn: () => liquidityApi.settings(),
    enabled,
  });
  return {
    resalePct: sec ? Number(sec.resale_fee_pct) : null,
    lpDiscountPct: liq ? Number(liq.discount_pct) : null,
    lpFeePct: liq ? Number(liq.fee_pct) : null,
    lpMinutes: liq ? liq.ttl_minutes : null,
  };
}

const SETTLEMENT: Record<ExitMethod, string> = {
  secondary: "When a buyer buys",
  liquidity: "When a provider funds it",
};

type Summary = { pricePerUnit: number; proceeds: number; fee: number; net: number; remaining: number };

/** What an exit of `units` brings, with the server's formulas (the server prices the real one). */
function exitSummary(method: ExitMethod, position: OwnedPosition, units: number, rates: Rates): Summary | null {
  const gross = cents(units * position.unitPrice);
  const remaining = position.units - units;
  if (method === "secondary") {
    return { pricePerUnit: position.unitPrice, proceeds: gross, fee: 0, net: gross, remaining };
  }
  if (rates.lpDiscountPct == null || rates.lpFeePct == null) return null;
  // liquidity_service._price_for: the discounted price, then the fee on it, each to the cent
  const proceeds = cents((gross * (100 - rates.lpDiscountPct)) / 100);
  const fee = cents((proceeds * rates.lpFeePct) / 100);
  return {
    pricePerUnit: cents((position.unitPrice * (100 - rates.lpDiscountPct)) / 100),
    proceeds,
    fee,
    net: cents(proceeds - fee),
    remaining,
  };
}

export function ExitFlowDialog({ open, onOpenChange, initialPositionId }: Props) {
  const [step, setStep] = useState<Step>("method");
  const [method, setMethod] = useState<ExitMethod | null>(null);
  const [position, setPosition] = useState<OwnedPosition | null>(null);
  const [units, setUnits] = useState(1);
  const positions = useOwnedPositions();
  const rates = useExitRates(open);
  // running installment plans: not loose units, each is sold whole as a position
  const { data: planData } = useQuery({
    queryKey: ["secondary", "positions"],
    queryFn: () => secondaryApi.positions(),
    enabled: open,
  });
  const plans = [...(planData?.items ?? [])].sort(
    (a, b) =>
      Number(String(b.property_id) === String(initialPositionId)) -
      Number(String(a.property_id) === String(initialPositionId)),
  );
  const createListing = useCreateListing();
  const createExitRequest = useCreateExitRequest();

  useEffect(() => {
    if (!open) return;
    setStep("method");
    setMethod(null);
    const pre = positions.find((p) => String(p.id) === String(initialPositionId));
    setPosition(pre ?? null);
    setUnits(pre ? Math.max(1, Math.floor(pre.units * 0.25)) : 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialPositionId]);

  const summary = useMemo(
    () => (position && method ? exitSummary(method, position, units, rates) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [position, method, units, rates.lpDiscountPct, rates.lpFeePct],
  );

  const goBack = () => {
    if (step === "select") setStep("method");
    else if (step === "summary") setStep("select");
  };

  const handleConfirm = async () => {
    if (!position || !method || !summary) return;
    try {
      if (method === "liquidity") {
        // Live LP instant-exit: the server prices the discount + fee authoritatively.
        await createExitRequest.mutateAsync({ property_id: String(position.id), units });
        setStep("done");
        toast.success("Instant-exit request listed", {
          description: `${units} unit(s) of ${position.name} are now available to liquidity providers.`,
        });
        return;
      }
      await createListing.mutateAsync({
        property_id: String(position.id),
        units,
        price_per_unit: summary.pricePerUnit,
      });
      setStep("done");
      toast.success("Listed on the secondary market", {
        description: `${units} unit(s) of ${position.name} listed at $${summary.pricePerUnit.toFixed(2)}/unit.`,
      });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Could not submit your exit request.";
      toast.error("Exit request failed", { description: msg });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-3 border-b">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              {step !== "method" && step !== "done" && (
                <Button variant="ghost" size="icon" className="h-8 w-8 -ml-2" onClick={goBack}>
                  <ArrowLeft className="h-4 w-4" />
                </Button>
              )}
              <div>
                <DialogTitle className="flex items-center gap-2">
                  <ArrowRightLeft className="h-5 w-5 text-primary" />
                  Exit Ownership Position
                </DialogTitle>
                <DialogDescription className="mt-1">
                  Institutional-grade exit flow — choose how you want to liquidate your real
                  estate ownership.
                </DialogDescription>
              </div>
            </div>
            <StepDots step={step} />
          </div>
        </DialogHeader>

        <div className="px-6 py-5 max-h-[70vh] overflow-y-auto">
          {step === "method" && (
            <MethodStep
              selected={method}
              rates={rates}
              onSelect={(m) => {
                setMethod(m);
                setStep("select");
              }}
            />
          )}

          {step === "select" && method && (
            <SelectStep
              method={method}
              positions={positions}
              position={position}
              units={units}
              rates={rates}
              plans={plans}
              onLeave={() => onOpenChange(false)}
              onSelectPosition={(p) => {
                setPosition(p);
                setUnits(Math.max(1, Math.floor(p.units * 0.25)));
              }}
              onUnitsChange={setUnits}
              onContinue={() => setStep("summary")}
            />
          )}

          {step === "summary" && method && position && summary && (
            <SummaryStep
              method={method}
              position={position}
              units={units}
              summary={summary}
              rates={rates}
            />
          )}

          {step === "done" && method && position && (
            <DoneStep method={method} propertyName={position.name} />
          )}
        </div>

        {step === "summary" && (
          <DialogFooter className="px-6 py-4 border-t bg-muted/30">
            <Button variant="outline" onClick={goBack} className="gap-1">
              <ArrowLeft className="h-4 w-4" /> Back
            </Button>
            <Button
              onClick={handleConfirm}
              className="gap-1.5"
              disabled={!summary || createListing.isPending || createExitRequest.isPending}
            >
              Confirm Exit Request <ChevronRight className="h-4 w-4" />
            </Button>
          </DialogFooter>
        )}
        {step === "done" && (
          <DialogFooter className="px-6 py-4 border-t bg-muted/30">
            <Button onClick={() => onOpenChange(false)} className="w-full sm:w-auto">
              Done
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}

function StepDots({ step }: { step: Step }) {
  const order: Step[] = ["method", "select", "summary", "done"];
  const idx = order.indexOf(step);
  return (
    <div className="flex items-center gap-1.5">
      {order.map((s, i) => (
        <div
          key={s}
          className={cn(
            "h-1.5 rounded-full transition-all",
            i <= idx ? "w-6 bg-primary" : "w-3 bg-muted"
          )}
        />
      ))}
    </div>
  );
}

/* ----------------------------- Step 1: Method ----------------------------- */

function MethodStep({
  selected,
  rates,
  onSelect,
}: {
  selected: ExitMethod | null;
  rates: Rates;
  onSelect: (m: ExitMethod) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold">How would you like to exit your ownership position?</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Choose the exit channel that best matches your timing and pricing preferences.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <MethodCard
          active={selected === "secondary"}
          onClick={() => onSelect("secondary")}
          icon={ArrowRightLeft}
          title="Secondary Market Exit"
          tag="Your price · no fee for you"
          accent="from-primary to-accent"
          bullets={[
            "List your units on the secondary market",
            "You are paid in full when an investor buys them",
            `No fee for you: the buyer pays the ${pct(rates.resalePct)}resale fee`,
            "You can cancel the listing while it is unsold",
          ]}
          eta={SETTLEMENT.secondary}
          fee="No seller fee"
        />
        <MethodCard
          active={selected === "liquidity"}
          onClick={() => onSelect("liquidity")}
          icon={Zap}
          title="Liquidity Provider Exit"
          tag="Faster · below the unit price"
          accent="from-accent via-primary to-accent"
          bullets={[
            rates.lpDiscountPct == null
              ? "A liquidity provider buys below the unit price"
              : `A liquidity provider buys at the unit price less ${rates.lpDiscountPct}%`,
            `A ${pct(rates.lpFeePct)}liquidity fee is taken from that price`,
            "Paid to your wallet as soon as a provider funds it",
            `The request stays open for ${openFor(rates.lpMinutes)}`,
          ]}
          eta={SETTLEMENT.liquidity}
          fee={
            rates.lpDiscountPct == null || rates.lpFeePct == null
              ? "Below the unit price + a fee"
              : `${rates.lpDiscountPct}% below + ${rates.lpFeePct}% fee`
          }
        />
      </div>

      <div className="text-xs text-muted-foreground p-3 rounded-lg border bg-muted/30 flex gap-2">
        <Shield className="h-4 w-4 text-primary flex-shrink-0 mt-0.5" />
        Both exit channels are processed inside the platform under SPV-backed ownership rules.
        Units are sold at the property's current unit price; the final amounts are computed by the
        platform when the request is made.
      </div>
    </div>
  );
}

function MethodCard({
  active,
  onClick,
  icon: Icon,
  title,
  tag,
  accent,
  bullets,
  eta,
  fee,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof ArrowRightLeft;
  title: string;
  tag: string;
  accent: string;
  bullets: string[];
  eta: string;
  fee: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "text-left rounded-xl border p-4 transition-all hover:shadow-md hover:border-primary/40",
        active ? "border-primary ring-2 ring-primary/20" : "border-border bg-card"
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "w-11 h-11 rounded-xl bg-gradient-to-br flex items-center justify-center text-primary-foreground flex-shrink-0",
            accent
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
        <div className="flex-1">
          <div className="font-semibold">{title}</div>
          <div className="text-xs text-muted-foreground">{tag}</div>
        </div>
      </div>

      <ul className="space-y-1.5 mt-3">
        {bullets.map((b, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <CheckCircle2 className="h-4 w-4 text-primary flex-shrink-0 mt-0.5" />
            <span className="text-muted-foreground">{b}</span>
          </li>
        ))}
      </ul>

      <div className="grid grid-cols-2 gap-2 mt-3 pt-3 border-t">
        <div className="flex items-center gap-1.5 text-xs">
          <Clock className="h-3.5 w-3.5 text-primary" />
          <span className="text-muted-foreground">{eta}</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs justify-end">
          <DollarSign className="h-3.5 w-3.5 text-primary" />
          <span className="text-muted-foreground">{fee}</span>
        </div>
      </div>
    </button>
  );
}

/* ----------------------------- Step 2: Select ----------------------------- */

function SelectStep({
  method,
  positions,
  position,
  units,
  rates,
  plans,
  onLeave,
  onSelectPosition,
  onUnitsChange,
  onContinue,
}: {
  method: ExitMethod;
  positions: OwnedPosition[];
  position: OwnedPosition | null;
  units: number;
  rates: Rates;
  plans: MyPosition[];
  onLeave: () => void;
  onSelectPosition: (p: OwnedPosition) => void;
  onUnitsChange: (n: number) => void;
  onContinue: () => void;
}) {
  const estimate = position ? exitSummary(method, position, units, rates) : null;
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-base font-semibold">Select property & ownership allocation</h3>
          <p className="text-sm text-muted-foreground">
            Choose which position to exit and how many units to liquidate.
          </p>
        </div>
        <Badge variant="outline" className="border-primary/30 text-primary">
          {method === "secondary" ? (
            <><ArrowRightLeft className="h-3 w-3 mr-1" /> Secondary Market</>
          ) : (
            <><Zap className="h-3 w-3 mr-1" /> Liquidity Provider</>
          )}
        </Badge>
      </div>

      {/* Position list */}
      {positions.length === 0 && (
        <div className="text-center py-10 text-sm text-muted-foreground border rounded-lg bg-muted/20">
          {plans.length > 0
            ? "You have no fully paid units to sell here."
            : "You have no sellable units yet. Invest in a property first, or wait for a lock-up to clear."}
        </div>
      )}
      {/* units on a running installment plan are not in the list above: the plan is sold whole */}
      {plans.length > 0 && (
        <div className="rounded-lg border border-primary/30 bg-primary/5 p-3" data-testid="exit-plan-positions">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <CalendarClock className="h-4 w-4 text-primary" /> Units on an installment plan
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Units you are still paying for are sold with their plan, as one position, on the secondary
            market: the buyer pays you the principal you have paid plus the price change on all the units,
            and takes over the remaining installments.
            {method === "liquidity" && " Liquidity providers buy fully paid units only."}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {plans.map((plan) => (
              <Button
                key={plan.plan_id}
                asChild
                size="sm"
                variant="outline"
                className="h-auto gap-1.5 whitespace-normal py-1.5 text-left"
              >
                <Link to={`/secondary-market?tab=sell&plan=${plan.plan_id}`} onClick={onLeave}>
                  Sell the {plan.property_title ?? "property"} position
                  <ChevronRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            ))}
          </div>
        </div>
      )}
      <div className="grid grid-cols-1 gap-2 max-h-[260px] overflow-y-auto pr-1">
        {positions.map((p) => {
          const active = position?.id === p.id;
          return (
            <button
              key={p.id}
              onClick={() => onSelectPosition(p)}
              className={cn(
                "flex items-center gap-3 p-3 rounded-lg border text-left transition-all",
                active ? "border-primary bg-primary/5 ring-1 ring-primary/20" : "border-border hover:border-primary/40"
              )}
            >
              {p.image ? (
                <img src={p.image} alt={p.name} className="w-14 h-14 rounded-md object-cover flex-shrink-0" />
              ) : (
                <div className="w-14 h-14 rounded-md bg-gradient-to-br from-primary/15 to-accent/10 flex items-center justify-center flex-shrink-0">
                  <Building2 className="h-6 w-6 text-primary/50" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-sm truncate">{p.name}</div>
                <div className="text-xs text-muted-foreground truncate">
                  {p.location} · {p.type}
                </div>
                <div className="flex items-center gap-3 mt-1 text-[11px]">
                  <span className="text-muted-foreground">{p.units} units</span>
                  <span className="text-primary font-semibold">${p.unitPrice}/unit</span>
                  <span className="text-muted-foreground">Demand: {p.demand}</span>
                </div>
              </div>
              {active && <CheckCircle2 className="h-5 w-5 text-primary flex-shrink-0" />}
            </button>
          );
        })}
      </div>

      {/* Units selector */}
      {position && (
        <div className="space-y-4 p-4 rounded-xl border bg-muted/20">
          <div className="flex items-center justify-between">
            <Label className="text-sm font-semibold">Units to exit</Label>
            <div className="flex gap-1">
              {[25, 50, 75, 100].map((pct) => (
                <Button
                  key={pct}
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-7 px-2 text-[11px]"
                  onClick={() => onUnitsChange(Math.max(1, Math.floor((position.units * pct) / 100)))}
                >
                  {pct === 100 ? "Full" : `${pct}%`}
                </Button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Slider
              value={[units]}
              min={1}
              max={position.units}
              step={1}
              onValueChange={(v) => onUnitsChange(v[0])}
              className="flex-1"
            />
            <Input
              type="number"
              min={1}
              max={position.units}
              value={units}
              onChange={(e) =>
                onUnitsChange(Math.min(position.units, Math.max(1, parseInt(e.target.value) || 1)))
              }
              className="w-24"
            />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
            <Stat label="Current valuation" value={money(position.units * position.unitPrice)} />
            <Stat
              label="You would receive"
              value={estimate ? money(estimate.net) : "—"}
              accent
            />
            <Stat label="Settlement" value={SETTLEMENT[method]} />
            <Stat
              label="Fee"
              value={
                method === "secondary"
                  ? "None for you"
                  : rates.lpFeePct == null
                    ? "On the price"
                    : `${rates.lpFeePct}% of the price`
              }
            />
          </div>

          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              Remaining ownership after exit:{" "}
              <span className="font-semibold text-foreground">{position.units - units} units</span>
            </span>
            <span>
              Market demand:{" "}
              <span className="font-semibold text-foreground">{position.demand}</span>
            </span>
          </div>
        </div>
      )}

      <div className="flex justify-end">
        <Button onClick={onContinue} disabled={!position} className="gap-1.5">
          Continue <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="p-2 rounded-lg bg-card border">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={cn("text-sm font-semibold", accent && "text-primary")}>{value}</div>
    </div>
  );
}

/* ----------------------------- Step 3: Summary ----------------------------- */

function SummaryStep({
  method,
  position,
  units,
  summary,
  rates,
}: {
  method: ExitMethod;
  position: OwnedPosition;
  units: number;
  summary: Summary;
  rates: Rates;
}) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold">Review your exit request</h3>
        <p className="text-sm text-muted-foreground">
          Please review the details below. The platform computes the final amounts when the request is made.
        </p>
      </div>

      <div className="flex items-center gap-3 p-3 rounded-xl border bg-muted/20">
        {position.image ? (
          <img src={position.image} alt={position.name} className="w-14 h-14 rounded-md object-cover" />
        ) : (
          <div className="w-14 h-14 rounded-md bg-gradient-to-br from-primary/15 to-accent/10 flex items-center justify-center">
            <Building2 className="h-6 w-6 text-primary/50" />
          </div>
        )}
        <div className="flex-1">
          <div className="font-semibold">{position.name}</div>
          <div className="text-xs text-muted-foreground">{position.location} · {position.type}</div>
        </div>
        <Badge variant="outline" className="border-primary/30 text-primary">
          {method === "secondary" ? "Secondary" : "Liquidity"}
        </Badge>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        <Row label="Units to exit" value={`${units}`} />
        <Row label="Price per unit" value={money(summary.pricePerUnit)} />
        <Row label="Estimated proceeds" value={money(summary.proceeds)} />
        {method === "secondary" ? (
          <Row
            label="Exit fee"
            value={rates.resalePct == null ? "None (the buyer pays it)" : `None (the buyer pays ${rates.resalePct}%)`}
          />
        ) : (
          <Row
            label={rates.lpFeePct == null ? "Liquidity fee" : `Liquidity fee (${rates.lpFeePct}%)`}
            value={`-${money(summary.fee)}`}
            negative
          />
        )}
        <Row label="Net to wallet" value={money(summary.net)} accent />
        <Row label="Settlement" value={SETTLEMENT[method]} />
        <Row label="Remaining ownership" value={`${summary.remaining} units`} />
        <Row label="Market demand" value={position.demand} />
        <Row label="Liquidity" value={position.liquidity} />
      </div>

      <div className="text-xs text-muted-foreground p-3 rounded-lg border bg-primary/5 flex gap-2">
        <Sparkles className="h-4 w-4 text-primary flex-shrink-0 mt-0.5" />
        {method === "secondary"
          ? "Your units are listed at the current unit price and stay yours until an investor buys them. To ask a different price, list them from the Secondary Market page."
          : "Your units are held for the request and paid for as soon as a liquidity provider funds it. If the unit price changes meanwhile, the request is closed and you can make a new one."}
      </div>
    </div>
  );
}

function Row({ label, value, accent, negative }: { label: string; value: string; accent?: boolean; negative?: boolean }) {
  return (
    <div className="p-3 rounded-lg border bg-card">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div
        className={cn(
          "text-sm font-semibold",
          accent && "text-primary",
          negative && "text-destructive"
        )}
      >
        {value}
      </div>
    </div>
  );
}

/* ----------------------------- Step 4: Done ----------------------------- */

function DoneStep({ method, propertyName }: { method: ExitMethod; propertyName: string }) {
  return (
    <div className="text-center py-6 space-y-4">
      <div className="w-16 h-16 mx-auto rounded-full bg-primary/10 flex items-center justify-center">
        <CheckCircle2 className="h-8 w-8 text-primary" />
      </div>
      <div>
        <h3 className="text-lg font-bold">Exit request submitted</h3>
        <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
          Your {method === "secondary" ? "secondary market listing" : "liquidity provider request"} for{" "}
          <span className="font-semibold text-foreground">{propertyName}</span> is now active.
          Track progress in the <span className="font-semibold text-foreground">Exit Requests</span> tab.
        </p>
      </div>
      <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground">
        <div className="flex items-center gap-1"><Wallet className="h-3 w-3" /> Net proceeds settle to wallet</div>
        <div className="flex items-center gap-1"><Building2 className="h-3 w-3" /> Ownership updated on settlement</div>
        <div className="flex items-center gap-1"><TrendingUp className="h-3 w-3" /> Tracked in dashboard</div>
      </div>
    </div>
  );
}
