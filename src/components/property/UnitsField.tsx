import { Minus, Plus } from "lucide-react";
import { useNumberDraft } from "@/hooks/useNumberDraft";

interface UnitsFieldProps {
  /** The price of one unit (> 0). */
  unitPrice: number;
  /** The whole units the current amount buys. */
  units: number;
  /** The amount bounds of the listing: the units field allows the whole units inside them. */
  minAmount: number;
  maxAmount: number;
  /** Sets the amount to this many units. */
  onUnits: (units: number) => void;
  testId?: string;
}

/**
 * How many units to buy, typed directly (client letter, 2026-11-18: "a clear field to write the
 * number of units when buying"). It drives the same amount as the amount field: units × unit
 * price. The range is the whole units inside the listing's minimum and maximum amounts.
 */
export default function UnitsField(props: UnitsFieldProps) {
  const { unitPrice, units, minAmount, maxAmount, onUnits } = props;
  const testId = props.testId ?? "units-field";
  const minUnits = Math.max(1, Math.ceil(minAmount / unitPrice - 1e-9));
  const maxUnits = Math.max(minUnits, Math.floor(maxAmount / unitPrice + 1e-9));
  const field = useNumberDraft({ value: units, onValueChange: onUnits, min: minUnits, max: maxUnits, integer: true });
  const step = (by: number) => onUnits(Math.min(Math.max(units + by, minUnits), maxUnits));

  return (
    <div data-testid={testId}>
      <label htmlFor={`${testId}-input`} className="block text-sm font-medium text-foreground mb-2">
        Number of Units
      </label>
      <div className="flex items-stretch gap-2">
        <button
          type="button"
          onClick={() => step(-1)}
          disabled={units <= minUnits}
          aria-label="One unit less"
          className="flex w-12 items-center justify-center rounded-xl border border-border bg-secondary text-foreground transition hover:bg-secondary/80 disabled:opacity-40"
        >
          <Minus className="h-4 w-4" />
        </button>
        <input
          id={`${testId}-input`}
          type="number"
          {...field.inputProps}
          min={minUnits}
          max={maxUnits}
          step={1}
          className={`min-w-0 flex-1 rounded-xl border bg-secondary px-4 py-3 text-center text-lg font-semibold text-foreground focus:outline-none focus:ring-2 ${
            field.invalid ? "border-destructive focus:ring-destructive" : "border-border focus:ring-primary"
          }`}
        />
        <button
          type="button"
          onClick={() => step(1)}
          disabled={units >= maxUnits}
          aria-label="One unit more"
          className="flex w-12 items-center justify-center rounded-xl border border-border bg-secondary text-foreground transition hover:bg-secondary/80 disabled:opacity-40"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {`From ${minUnits.toLocaleString("en-US")} to ${maxUnits.toLocaleString("en-US")} units`}
      </p>
    </div>
  );
}
