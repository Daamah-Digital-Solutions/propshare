import { useEffect, useMemo, useState } from "react";
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
import { ApiError } from "@/lib/api";
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

const FEE_RATES: Record<ExitMethod, number> = {
  secondary: 0.025, // 2.5%
  liquidity: 0.035, // 3.5%
};

const SETTLEMENT: Record<ExitMethod, string> = {
  secondary: "T+3 to T+10 days",
  liquidity: "Within 24 hours",
};

export function ExitFlowDialog({ open, onOpenChange, initialPositionId }: Props) {
  const [step, setStep] = useState<Step>("method");
  const [method, setMethod] = useState<ExitMethod | null>(null);
  const [position, setPosition] = useState<OwnedPosition | null>(null);
  const [units, setUnits] = useState(1);
  const positions = useOwnedPositions();
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

  const summary = useMemo(() => {
    if (!position || !method) return null;
    // Liquidity provider exits typically apply a small discount to instant price
    const liquidityDiscount = method === "liquidity" ? 0.97 : 1;
    const pricePerUnit = +(position.unitPrice * liquidityDiscount).toFixed(2);
    const gross = +(units * pricePerUnit).toFixed(2);
    const fee = +(gross * FEE_RATES[method]).toFixed(2);
    const net = +(gross - fee).toFixed(2);
    const remaining = position.units - units;
    return { pricePerUnit, gross, fee, net, remaining };
  }, [position, method, units]);

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
            <Button onClick={handleConfirm} className="gap-1.5">
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
  onSelect,
}: {
  selected: ExitMethod | null;
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
          tag="Lower fees · market price"
          accent="from-primary to-accent"
          bullets={[
            "List your allocation on the secondary market",
            "Wait for a qualified investor to purchase",
            "Lower platform fees (≈ 2.5%)",
            "Market-driven settlement price",
          ]}
          eta="T+3 to T+10 days"
          fee="2.5% fee"
        />
        <MethodCard
          active={selected === "liquidity"}
          onClick={() => onSelect("liquidity")}
          icon={Zap}
          title="Liquidity Provider Exit"
          tag="Instant · backed liquidity"
          accent="from-accent via-primary to-accent"
          bullets={[
            "Instant or fast exit via liquidity providers",
            "Faster settlement to your wallet",
            "Immediate liquidity access",
            "Liquidity-provider backed buy-back",
          ]}
          eta="Within 24 hours"
          fee="3.5% fee"
        />
      </div>

      <div className="text-xs text-muted-foreground p-3 rounded-lg border bg-muted/30 flex gap-2">
        <Shield className="h-4 w-4 text-primary flex-shrink-0 mt-0.5" />
        Both exit channels are processed inside the platform under SPV-backed ownership rules.
        Settlement timelines and pricing are indicative and depend on each opportunity.
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
  onSelectPosition,
  onUnitsChange,
  onContinue,
}: {
  method: ExitMethod;
  positions: OwnedPosition[];
  position: OwnedPosition | null;
  units: number;
  onSelectPosition: (p: OwnedPosition) => void;
  onUnitsChange: (n: number) => void;
  onContinue: () => void;
}) {
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
          You have no sellable units yet. Invest in a property first, or wait for a lock-up to clear.
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
            <Stat label="Current valuation" value={`$${(position.units * position.unitPrice).toLocaleString()}`} />
            <Stat
              label="Estimated exit value"
              value={`$${(units * position.unitPrice * (method === "liquidity" ? 0.97 : 1)).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
              accent
            />
            <Stat label="Settlement" value={SETTLEMENT[method]} />
            <Stat label="Fee" value={`${(FEE_RATES[method] * 100).toFixed(1)}%`} />
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
}: {
  method: ExitMethod;
  position: OwnedPosition;
  units: number;
  summary: { pricePerUnit: number; gross: number; fee: number; net: number; remaining: number };
}) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold">Review your exit request</h3>
        <p className="text-sm text-muted-foreground">
          Please review the details below. Final pricing may vary based on market conditions and provider quotes.
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
        <Row label="Price per unit" value={`$${summary.pricePerUnit.toFixed(2)}`} />
        <Row label="Estimated proceeds" value={`$${summary.gross.toLocaleString()}`} />
        <Row label="Exit fee" value={`-$${summary.fee.toLocaleString()}`} negative />
        <Row label="Net to wallet" value={`$${summary.net.toLocaleString()}`} accent />
        <Row label="Settlement" value={SETTLEMENT[method]} />
        <Row label="Remaining ownership" value={`${summary.remaining} units`} />
        <Row label="Market demand" value={position.demand} />
        <Row label="Liquidity" value={position.liquidity} />
      </div>

      <div className="text-xs text-muted-foreground p-3 rounded-lg border bg-primary/5 flex gap-2">
        <Sparkles className="h-4 w-4 text-primary flex-shrink-0 mt-0.5" />
        Exit conditions: subject to platform rules, qualified-investor matching (secondary) or
        provider availability (liquidity). Settlement times are indicative.
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
