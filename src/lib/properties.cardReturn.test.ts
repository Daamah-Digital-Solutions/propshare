import { describe, it, expect } from "vitest";
import { cardReturn } from "./properties";

const base = { total_return: null, expected_yield: null, capital_appreciation: null, target_yield: null };

describe("cardReturn: the return a property card shows", () => {
  it("is the total expected return, not the rental yield (client, 2026-11-17)", () => {
    // Pacific Mirage: 7% rent + 4.66% appreciation = 11.66% total, as on its page
    expect(cardReturn({ ...base, expected_yield: 7, capital_appreciation: 4.66, total_return: 11.66 })).toBe(11.66);
  });

  it("adds rent and appreciation when the listing has no total", () => {
    expect(cardReturn({ ...base, expected_yield: 7, capital_appreciation: 4.66 })).toBe(11.66);
  });

  it("falls back to the rental yield, then the target yield, then 0", () => {
    expect(cardReturn({ ...base, expected_yield: 8 })).toBe(8);
    expect(cardReturn({ ...base, target_yield: 6.5 })).toBe(6.5);
    expect(cardReturn(base)).toBe(0);
  });
});
