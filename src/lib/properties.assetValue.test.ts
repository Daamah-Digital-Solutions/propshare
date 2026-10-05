/**
 * A property's value on every page is all its units at today's unit price. The offering's own
 * total (`total_value`) blends what was paid for the units already sold with today's price
 * for the rest, so after a price change it is neither the launch value nor today's.
 * `launch_price` (set by the server at the first price change) says the price has moved.
 */
import { describe, expect, it } from "vitest";
import type { PropertySummary } from "@/lib/api";
import { shortDate } from "@/lib/money";
import { assetValue, toMarketplaceProperty } from "./properties";

describe("assetValue", () => {
  it("is the stored total until the unit price moves", () => {
    expect(assetValue({ total_units: 10_000, unit_price: 100, total_value: 1_000_000, launch_price: null })).toBe(
      1_000_000,
    );
  });

  it("is every unit at today's price once it has moved, not the blended total", () => {
    // 4,000 of the 10,000 units were sold at $100, then the price went to $110
    expect(assetValue({ total_units: 10_000, unit_price: 110, total_value: 1_060_000, launch_price: 100 })).toBe(
      1_100_000,
    );
  });

  it("leaves a listing whose stored total was entered differently alone", () => {
    // an old listing where units x price is not the total, and whose price never changed
    expect(assetValue({ total_units: 9_000, unit_price: 100, total_value: 1_000_000 })).toBe(1_000_000);
    expect(assetValue({ total_units: 0, unit_price: 0, total_value: 750_000, launch_price: null })).toBe(750_000);
  });

  it("is what the marketplace card shows", () => {
    const summary = {
      id: "p1",
      slug: "p1",
      title: "Creek Tower",
      subtitle: null,
      location: "Dubai",
      country: "UAE",
      city: "Dubai",
      model: "installment",
      property_type: "apartment",
      status: "active",
      image: null,
      total_value: 1_060_000,
      minimum_investment: 110,
      unit_price: 110,
      launch_price: 100,
      target_yield: null,
      expected_yield: null,
      capital_appreciation: null,
      total_return: null,
      funded_amount: 400_000,
      funding_progress: 37.7,
      total_units: 10_000,
      available_units: 6_000,
      investors_count: 12,
      developer_name: null,
    } as PropertySummary;
    expect(toMarketplaceProperty(summary).price).toBe(1_100_000);
  });
});

describe("shortDate", () => {
  it("shows a calendar date as that day and a timestamp as the viewer's day", () => {
    expect(shortDate("2026-11-01")).toBe("Nov 1, 2026"); // a due date: the same day everywhere
    // an instant: whatever day it is where the viewer is (never the UTC day by force)
    const instant = "2026-12-15T23:30:00Z";
    expect(shortDate(instant)).toBe(
      new Date(instant).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }),
    );
    expect(shortDate(null)).toBe("—");
  });
});
