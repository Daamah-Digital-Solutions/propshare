/**
 * How much the units held have changed in value since they were bought (client letter,
 * 2026-11-18: the dashboard shows the change in an investment's value, as an amount and a
 * percentage, against its value at purchase). Purchase value = units × average cost (the
 * ledger-weighted price paid); value now = units × the current unit price.
 */
export interface PricedHolding {
  units: number;
  unit_price: string | number;
  average_cost?: string | number | null;
}

export interface ValueChange {
  /** value now − value at purchase, in dollars (2 dp) */
  amount: number;
  /** that change as a percentage of the value at purchase (2 dp); null when nothing was paid */
  pct: number | null;
  /** the value at purchase the change is measured against */
  paid: number;
}

const round2 = (n: number) => Math.round(n * 100) / 100;

/** The change across these holdings; only units with a known purchase price count. */
export function valueChange(holdings: PricedHolding[]): ValueChange {
  let paid = 0;
  let now = 0;
  for (const h of holdings) {
    if (h.average_cost == null || h.units <= 0) continue;
    paid += h.units * Number(h.average_cost);
    now += h.units * Number(h.unit_price);
  }
  const amount = round2(now - paid);
  return { amount, pct: paid > 0 ? round2((amount / paid) * 100) : null, paid: round2(paid) };
}

/** "+$1,250 (+4.17%)" / "−$80 (−0.53%)" / "$0 (0%)". */
export function changeLabel(c: ValueChange): string {
  const sign = c.amount > 0 ? "+" : c.amount < 0 ? "−" : "";
  const money = `${sign}$${Math.abs(c.amount).toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
  if (c.pct === null) return money;
  const pct = `${sign}${Math.abs(c.pct).toLocaleString("en-US", { maximumFractionDigits: 2 })}%`;
  return `${money} (${pct})`;
}
