/**
 * Client feedback #3 — the liquidity provider's dashboard: a real wallet (deposit / withdraw)
 * inside their own dashboard, the whole cycle explained with links, and an exit for every
 * held asset through the secondary market.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { data } = vi.hoisted(() => ({
  data: {
    holdings: [] as unknown[],
  },
}));
vi.mock("@/lib/api", () => ({
  liquidityApi: {
    holdings: async () => ({ items: data.holdings, total: data.holdings.length }),
    positions: async () => ({ items: [], total: 0 }),
    settings: async () => ({ passive_enabled: false, tiers: [] }),
  },
  returnsApi: { getMine: async () => ({ items: [], total_net: "0", count: 0 }) },
  walletApi: { getMe: async () => ({ balance: "2500.00", pending_balance: "0", currency: "USD" }) },
}));
vi.mock("@/components/dashboard/InvestorWallet", () => ({
  InvestorWallet: () => <div data-testid="real-wallet">wallet with deposit and withdraw</div>,
}));
vi.mock("@/components/dashboard/VirtualCardRequest", () => ({
  VirtualCardRequest: () => <div>cards</div>,
}));

import LiquidityDashboard from "./LiquidityDashboard";

function mount(url = "/liquidity-dashboard") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <LiquidityDashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LiquidityDashboard", () => {
  beforeEach(() => {
    data.holdings = [];
  });

  it("opens the real wallet in the LP's own dashboard (no bounce to the investor one)", async () => {
    mount("/liquidity-dashboard?tab=wallet");
    expect(await screen.findByTestId("real-wallet")).toBeInTheDocument();
    expect(screen.queryByText(/shared across roles/i)).toBeNull();
  });

  it("explains the whole cycle, each step linking to where it happens", async () => {
    mount();
    expect(await screen.findByText("$2,500")).toBeInTheDocument(); // wallet balance to fund with
    const cycle = screen.getByTestId("lp-cycle");
    for (const step of ["Fund your wallet", "Choose an exit request", "Buy the units", "Hold them", "Exit on the Secondary Market"]) {
      expect(cycle).toHaveTextContent(step);
    }
    const hrefs = Array.from(cycle.querySelectorAll("a")).map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual(
      expect.arrayContaining([
        "/liquidity-dashboard?tab=wallet",
        "/liquidity-market",
        "/liquidity-dashboard?tab=assets",
        "/secondary-market?tab=sell",
      ]),
    );
  });

  it("gives every held asset a way out through the secondary market", async () => {
    data.holdings = [
      {
        property_id: "prop-9",
        title: "Marina Heights",
        location: "Dubai",
        units: 10,
        listed_units: 4,
        sellable_units: 6,
        unit_price: "100.00",
      },
    ];
    mount("/liquidity-dashboard?tab=assets");
    const sell = await screen.findByRole("link", { name: /Sell on Secondary Market/ });
    expect(sell).toHaveAttribute("href", "/secondary-market?tab=sell&property=prop-9");
    expect(screen.getByText("4 / 6")).toBeInTheDocument();
  });

  it("sends an LP without holdings to the market", async () => {
    mount("/liquidity-dashboard?tab=assets");
    expect(await screen.findByRole("link", { name: "Open the Liquidity Market" })).toHaveAttribute(
      "href",
      "/liquidity-market",
    );
  });
});
