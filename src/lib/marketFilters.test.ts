import { describe, it, expect } from "vitest";
import { inRange, PRICE_MAX, topLabel, YIELD_MAX } from "./marketFilters";

describe("marketplace range filters", () => {
  it("never hides a listing above the top of an untouched range (client, 2026-11-17)", () => {
    // the Greek off-plan listings: 16% and 22% rent, 32% and 44% in total; and anything higher
    for (const r of [16, 22, 32, 44, 60, 120]) expect(inRange(r, [0, YIELD_MAX], YIELD_MAX)).toBe(true);
    expect(inRange(45_000_000, [0, PRICE_MAX], PRICE_MAX)).toBe(true);
  });

  it("applies a top the visitor lowered", () => {
    expect(inRange(22, [0, 15], YIELD_MAX)).toBe(false);
    expect(inRange(12, [0, 15], YIELD_MAX)).toBe(true);
    expect(inRange(4, [5, YIELD_MAX], YIELD_MAX)).toBe(false);
  });

  it("labels an open top with a plus", () => {
    expect(topLabel(YIELD_MAX, YIELD_MAX, (n) => `${n}%`)).toBe("50%+");
    expect(topLabel(15, YIELD_MAX, (n) => `${n}%`)).toBe("15%");
  });
});
