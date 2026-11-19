import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LpDealSummary from "./LpDealSummary";

vi.mock("@/lib/api", () => ({
  liquidityApi: {
    settings: async () => ({ discount_pct: "0", fee_pct: "1.5", fee_share_pct: "0.5", ttl_minutes: 1440, band_pct: "10", passive_enabled: false, tiers: [] }),
  },
}));

describe("LpDealSummary (client, 2026-11-18)", () => {
  it("shows the provider no purchase fee, its share of the seller's fee, and what the seller gets", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <LpDealSummary deal={10_000} />
      </QueryClientProvider>,
    );
    const box = await screen.findByTestId("lp-deal-summary");
    expect(box).toHaveTextContent("Value of the units (you pay)$10,000.00");
    expect(box).toHaveTextContent("Purchase fee$0.00");
    expect(screen.getByTestId("lp-share")).toHaveTextContent("+$50.00");
    expect(box).toHaveTextContent("The seller receives the value less a 1.5% fee$9,850.00");
  });
});
