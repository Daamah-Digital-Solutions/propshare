import { describe, expect, it } from "vitest";
import { liquidityFees, secondaryFees } from "./marketFees";

const RATES = { buyerPct: 1.5, sellerPct: 0.5, sharePct: 0.5 };

describe("market fees (client, 2026-11-18)", () => {
  it("an ordinary sale: 0.5% from the seller, 1.5% from the buyer", () => {
    const f = secondaryFees({ gross: 10_000, units: 100, ...RATES });
    expect(f).toMatchObject({ buyerFee: 150, sellerFee: 50, lpFeeShare: 0, totalCharged: 10_150, sellerNet: 9_950 });
  });

  it("a provider resells its LP-market units: no seller fee, 0.5% of the deal from the buyer's fee", () => {
    // the client's example: bought for 10,000, resold for 11,000
    const f = secondaryFees({ gross: 11_000, units: 100, lpUnits: 100, ...RATES });
    expect(f).toMatchObject({ buyerFee: 165, sellerFee: 0, lpFeeShare: 55, totalCharged: 11_165, sellerNet: 11_055 });
  });

  it("a listing partly of LP-market units: each part under its own rule", () => {
    const f = secondaryFees({ gross: 1_000, units: 10, lpUnits: 4, ...RATES });
    expect(f).toMatchObject({ buyerFee: 15, sellerFee: 3, lpFeeShare: 2, sellerNet: 999 });
  });

  it("a provider buys through the LP market: 1.5% from the seller, 0.5% of it to the provider", () => {
    const f = liquidityFees({ deal: 10_000, feePct: 1.5, sharePct: 0.5 });
    expect(f).toEqual({ deal: 10_000, sellerFee: 150, lpFeeShare: 50, sellerNet: 9_850 });
  });

  it("the share is never more than the fee it comes from", () => {
    expect(liquidityFees({ deal: 1_000, feePct: 0.2, sharePct: 0.5 }).lpFeeShare).toBe(2);
  });
});
