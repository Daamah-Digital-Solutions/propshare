// Display helpers for amounts the server computed. Nothing here does money math.

/** "$1,234.50": an amount, always with its cents. */
export const money = (value: string | number) =>
  `$${Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** "$100", "$12.50": a unit price keeps its cents only when it has any. */
export const unitPrice = (value: string | number) => {
  const n = Number(value);
  const digits = Math.round(n * 100) % 100 === 0 ? 0 : 2;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
};

/** "+5%", "-1.5%", "0%" */
export const signedPct = (value: string | number) => {
  const n = Math.round(Number(value) * 100) / 100;
  return `${n > 0 ? "+" : ""}${n}%`;
};

/** "Oct 5, 2026". A calendar date ("2026-10-05", a due date) is that day in every time
 * zone; a timestamp (an instant, with its time) is shown as the viewer's local day. */
export const shortDate = (iso: string | null) => {
  if (!iso) return "—";
  const when = iso.length > 10 ? new Date(iso) : new Date(`${iso}T00:00:00`);
  return when.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
};
