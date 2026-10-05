/**
 * The exit dialog must show the platform's own rates (it used to print literals that matched
 * nothing: a 2.5% seller fee on the secondary market, 3.5% and a 3% discount for a liquidity
 * exit) and must not tell an investor who pays by installments that there is nothing to sell:
 * a running plan is sold whole, as a position.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { holdings, positions, createListing, createExit, rates } = vi.hoisted(() => ({
  holdings: vi.fn(),
  positions: vi.fn(),
  createListing: vi.fn(),
  createExit: vi.fn(),
  rates: { signedIn: true },
}));
vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    holdingsApi: { mine: () => holdings() },
    secondaryApi: {
      settings: async () => {
        if (!rates.signedIn) throw new Error("401");
        return { resale_fee_pct: "1.0", lockup_days: 0, price_min_pct: null, price_max_pct: null };
      },
      positions: () => positions(),
      create: (...a: unknown[]) => createListing(...a),
      mine: async () => ({ items: [], total: 0 }),
    },
    liquidityApi: {
      settings: async () => {
        if (!rates.signedIn) throw new Error("401");
        return {
          discount_pct: "5.0",
          fee_pct: "2.0",
          ttl_minutes: 1440,
          band_pct: "10",
          passive_enabled: false,
          tiers: [],
        };
      },
      createExitRequest: (...a: unknown[]) => createExit(...a),
      myRequests: async () => ({ items: [], total: 0 }),
    },
  };
});
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { ExitFlowDialog } from "./ExitFlowDialog";

const HOLDING = {
  property_id: "prop-1",
  title: "Creek Tower",
  location: "Dubai",
  units: 100,
  listed_units: 0,
  sellable_units: 100,
  unit_price: "110.00",
};

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ExitFlowDialog open onOpenChange={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ExitFlowDialog", () => {
  beforeEach(() => {
    holdings.mockReset();
    positions.mockReset();
    createListing.mockReset();
    createExit.mockReset();
    rates.signedIn = true;
    holdings.mockResolvedValue({ items: [HOLDING], total: 1 });
    positions.mockResolvedValue({ items: [], total: 0 });
  });

  it("states the platform's real rates for each way out", async () => {
    mount();
    expect(await screen.findByText("No fee for you: the buyer pays the 1% resale fee")).toBeInTheDocument();
    expect(screen.getByText("A liquidity provider buys at the unit price less 5%")).toBeInTheDocument();
    expect(screen.getByText("A 2% liquidity fee is taken from that price")).toBeInTheDocument();
    expect(screen.getByText("The request stays open for 24 hours")).toBeInTheDocument();
    // none of the literals the dialog used to print
    expect(document.body.textContent).not.toMatch(/2\.5%|3\.5%|T\+3/);
  });

  it("a secondary sale pays the seller in full: the fee is the buyer's", async () => {
    createListing.mockResolvedValue({ listing_id: "lst-1" });
    mount();
    fireEvent.click(await screen.findByText("Secondary Market Exit"));
    fireEvent.click(await screen.findByText("Creek Tower"));
    // 25 of the 100 units at $110
    expect(await screen.findByText("You would receive")).toBeInTheDocument();
    expect(screen.getByText("$2,750.00")).toBeInTheDocument();
    expect(screen.getByText("None for you")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(await screen.findByText("None (the buyer pays 1%)")).toBeInTheDocument();
    const net = screen.getByText("Net to wallet").parentElement!;
    expect(net).toHaveTextContent("$2,750.00");
    fireEvent.click(screen.getByRole("button", { name: /confirm exit request/i }));
    await vi.waitFor(() =>
      expect(createListing).toHaveBeenCalledWith({ property_id: "prop-1", units: 25, price_per_unit: 110 }),
    );
  });

  it("a liquidity exit shows the provider's price and the fee taken from it", async () => {
    mount();
    fireEvent.click(await screen.findByText("Liquidity Provider Exit"));
    fireEvent.click(await screen.findByText("Creek Tower"));
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    // 25 × 110 = 2,750; less 5% = 2,612.50; the 2% fee on that = 52.25; net 2,560.25
    expect((await screen.findByText("Price per unit")).parentElement).toHaveTextContent("$104.50");
    expect(screen.getByText("Estimated proceeds").parentElement).toHaveTextContent("$2,612.50");
    expect(screen.getByText("Liquidity fee (2%)").parentElement).toHaveTextContent("-$52.25");
    expect(screen.getByText("Net to wallet").parentElement).toHaveTextContent("$2,560.25");
  });

  it("rounds each step to the cent the way the server does", async () => {
    // 1 unit at $100.50: 5% off is 95.475, which the server rounds UP to 95.48 (a binary
    // float would give 95.47); the 2% fee on that is 1.91; the seller nets 93.57
    holdings.mockResolvedValue({
      items: [{ ...HOLDING, units: 4, sellable_units: 4, unit_price: "100.50" }],
      total: 1,
    });
    mount();
    fireEvent.click(await screen.findByText("Liquidity Provider Exit"));
    fireEvent.click(await screen.findByText("Creek Tower"));
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect((await screen.findByText("Estimated proceeds")).parentElement).toHaveTextContent("$95.48");
    expect(screen.getByText("Liquidity fee (2%)").parentElement).toHaveTextContent("-$1.91");
    expect(screen.getByText("Net to wallet").parentElement).toHaveTextContent("$93.57");
  });

  it("still reads as sentences when the rates cannot be loaded (a visitor)", async () => {
    rates.signedIn = false;
    mount();
    expect(await screen.findByText("No fee for you: the buyer pays the resale fee")).toBeInTheDocument();
    expect(screen.getByText("A liquidity provider buys below the unit price")).toBeInTheDocument();
    expect(screen.getByText("A liquidity fee is taken from that price")).toBeInTheDocument();
    expect(screen.getByText("The request stays open for a limited time")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/—%|the — |less —/);
  });

  it("points an investor who pays by installments to selling the position", async () => {
    holdings.mockResolvedValue({ items: [], total: 0 });
    positions.mockResolvedValue({
      items: [{ plan_id: "plan-1", property_id: "prop-9", property_title: "Harbour Gate", units: 10 }],
      total: 1,
    });
    mount();
    fireEvent.click(await screen.findByText("Secondary Market Exit"));
    const box = await screen.findByTestId("exit-plan-positions");
    expect(box).toHaveTextContent(/sold with their plan, as one position/i);
    expect(within(box).getByRole("link", { name: /sell the harbour gate position/i })).toHaveAttribute(
      "href",
      "/secondary-market?tab=sell&plan=plan-1",
    );
    expect(screen.getByText("You have no fully paid units to sell here.")).toBeInTheDocument();
    expect(screen.queryByText(/You have no sellable units yet/)).toBeNull();
  });

  it("says a liquidity provider buys fully paid units only", async () => {
    positions.mockResolvedValue({
      items: [{ plan_id: "plan-1", property_id: "prop-9", property_title: "Harbour Gate", units: 10 }],
      total: 1,
    });
    mount();
    fireEvent.click(await screen.findByText("Liquidity Provider Exit"));
    expect(await screen.findByTestId("exit-plan-positions")).toHaveTextContent(
      /Liquidity providers buy fully paid units only/,
    );
  });
});
