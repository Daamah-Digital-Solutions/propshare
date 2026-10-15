/**
 * Funding progress as people read it (client, 2026-10-15). Rounding the percentage to a
 * whole number showed every opportunity under half a percent as 0%, although investors had
 * bought in, while the admin panel showed 0.03. Small values keep their decimals and round
 * the way the admin panel's figure does; a listing is never shown as 0% once money is in,
 * nor as 100% before it is fully funded.
 */

/** The funding percentage of a listing, from the confirmed money itself (funded amount /
 *  property value), the same rule as the server's ``funding_progress`` but not cut to two
 *  decimals: $100 into a $10M property is 0.001%, which the stored figure holds as 0.00. */
export function fundedPct(p: {
  funded_amount?: number | null;
  total_value?: number | null;
  funding_progress?: number | null;
}): number {
  const value = Number(p.total_value ?? 0);
  const funded = Number(p.funded_amount ?? 0);
  if (value > 0 && Number.isFinite(funded)) return Math.min(100, (funded / value) * 100);
  return Number(p.funding_progress ?? 0);
}

export function fundingText(pct: number | null | undefined): string {
  const p = Number(pct ?? 0);
  if (!Number.isFinite(p) || p <= 0) return "0%";
  if (p >= 100) return "100%";
  const decimals = p < 1 ? 2 : p < 10 ? 1 : 0;
  const factor = 10 ** decimals;
  const shown = Math.round(p * factor) / factor;
  if (shown <= 0) return "<0.01%";
  if (shown >= 100) return "99%"; // not fully funded yet
  const text = shown.toFixed(decimals);
  // trailing zeros of the decimals only ("0.50" -> "0.5", "2.0" -> "2"), never of "70"
  return `${decimals > 0 ? text.replace(/\.?0+$/, "") : text}%`;
}

/** The bar's width: a sliver as soon as anything is funded, so it is seen; the exact
 *  number is the text beside it. */
export function fundingBar(pct: number | null | undefined): number {
  const p = Number(pct ?? 0);
  if (!Number.isFinite(p) || p <= 0) return 0;
  return Math.min(100, Math.max(p, 1));
}
