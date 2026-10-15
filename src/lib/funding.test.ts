/**
 * Funding progress keeps its decimals (client, 2026-10-15): 0.03% funded was shown as 0%,
 * so an opportunity people had bought into looked untouched.
 */
import { describe, expect, it } from "vitest";
import { fundedPct, fundingBar, fundingText } from "./funding";

describe("fundingText", () => {
  it("shows a small funding with its decimals, never 0%", () => {
    expect(fundingText(0.03)).toBe("0.03%");
    expect(fundingText(0.2)).toBe("0.2%");
    expect(fundingText(0.5)).toBe("0.5%");
    expect(fundingText(0.004)).toBe("<0.01%");
  });

  it("keeps one decimal under 10% and whole numbers above, rounded like the admin panel", () => {
    expect(fundingText(2)).toBe("2%");
    expect(fundingText(2.47)).toBe("2.5%");
    expect(fundingText(45.9)).toBe("46%");
    expect(fundingText(70)).toBe("70%");
    expect(fundingText(10)).toBe("10%");
    expect(fundingText(5.0)).toBe("5%");
    expect(fundingText(99.99)).toBe("99%"); // never 100% before it is
    expect(fundingText(100)).toBe("100%");
  });

  it("says 0% when nothing is funded or the value is missing", () => {
    expect(fundingText(0)).toBe("0%");
    expect(fundingText(null)).toBe("0%");
    expect(fundingText(undefined)).toBe("0%");
  });
});

describe("fundingBar", () => {
  it("shows a sliver as soon as anything is funded", () => {
    expect(fundingBar(0)).toBe(0);
    expect(fundingBar(0.03)).toBe(1);
    expect(fundingBar(12.5)).toBe(12.5);
    expect(fundingBar(140)).toBe(100);
  });
});

describe("fundedPct", () => {
  it("is the confirmed money over the property value, not cut to two decimals", () => {
    expect(fundedPct({ funded_amount: 100, total_value: 10_000_000, funding_progress: 0 })).toBeCloseTo(0.001);
    expect(fundingText(fundedPct({ funded_amount: 100, total_value: 10_000_000, funding_progress: 0 }))).toBe("<0.01%");
    expect(fundingText(fundedPct({ funded_amount: 141, total_value: 470_100, funding_progress: 0.03 }))).toBe("0.03%"); // the admin panel says 0.03
    expect(fundedPct({ funded_amount: 6_000_000, total_value: 5_000_000 })).toBe(100);
  });

  it("falls back to the stored figure when the value is unknown", () => {
    expect(fundedPct({ funding_progress: 12.5 })).toBe(12.5);
    expect(fundedPct({ funded_amount: 50, total_value: 0, funding_progress: 0 })).toBe(0);
  });
});
