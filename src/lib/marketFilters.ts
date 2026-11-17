/**
 * The marketplace's range filters (property value and return).
 *
 * A slider pushed all the way up means "no upper limit": the top of the range is open, so a
 * listing above it is never hidden by a filter nobody touched. (Client, 2026-11-17: two Greek
 * off-plan listings returning 16% and 22% disappeared from the marketplace while the old
 * default stopped at 15%; they were still on the home page and in the admin panel.)
 */
export const YIELD_MAX = 50; // % — the return slider's top step
export const PRICE_MAX = 30_000_000; // $ — the value slider's top step

/** Is `value` inside [lo, hi]? A `hi` at the slider's top (`max`) has no upper limit. */
export const inRange = (value: number, [lo, hi]: [number, number], max: number): boolean =>
  value >= lo && (hi >= max || value <= hi);

/** The label of a range's top: "50%+" / "$30.0M+" when it is open. */
export const topLabel = (hi: number, max: number, format: (n: number) => string): string =>
  hi >= max ? `${format(hi)}+` : format(hi);
