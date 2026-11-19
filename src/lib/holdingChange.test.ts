import { describe, expect, it } from "vitest";
import { changeLabel, valueChange } from "./holdingChange";

describe("valueChange", () => {
  it("measures the units held against what they cost", () => {
    const c = valueChange([
      { units: 10, unit_price: "115", average_cost: "100" }, // +150 on 1,000
      { units: 5, unit_price: "90", average_cost: "100" }, // −50 on 500
    ]);
    expect(c).toEqual({ amount: 100, pct: 6.67, paid: 1500 });
    expect(changeLabel(c)).toBe("+$100 (+6.67%)");
  });

  it("a fall reads as one, and units with no known cost are left out", () => {
    const c = valueChange([
      { units: 4, unit_price: 95, average_cost: 100 },
      { units: 9, unit_price: 200, average_cost: null },
    ]);
    expect(c).toEqual({ amount: -20, pct: -5, paid: 400 });
    expect(changeLabel(c)).toBe("−$20 (−5%)");
  });

  it("nothing bought: no percentage", () => {
    const c = valueChange([]);
    expect(c.pct).toBeNull();
    expect(changeLabel(c)).toBe("$0");
  });
});
