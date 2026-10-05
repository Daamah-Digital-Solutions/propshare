/**
 * The holdings tab shows each property at its unit price of the day (client meeting
 * 2026-10-01: "an indicator on each property in the dashboard"): the price now, how far it
 * moved since launch, the gain on what the investor paid, and units that are on a running
 * installment plan as what they are, not as "listed for sale".
 */
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { holdings, portfolio } = vi.hoisted(() => ({ holdings: vi.fn(), portfolio: vi.fn() }));
vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    holdingsApi: { mine: () => holdings() },
    investApi: {
      list: async () => ({ items: [], total: 0 }),
      mySukuk: async () => [],
      portfolio: () => portfolio(),
    },
  };
});
vi.mock("@/components/exit/ExitButton", () => ({ ExitButton: () => <button>exit</button> }));
vi.mock("@/components/dashboard/PaymentReturnStatus", () => ({ PaymentReturnStatus: () => null }));
vi.mock("@/components/dashboard/SukukCertificatesCard", () => ({ SukukCertificatesCard: () => null }));

import { ActiveInvestments } from "./ActiveInvestments";

// 10 units bought at $100 while the property was at its launch price; it is now $110
const HOLDING = {
  property_id: "prop-1",
  title: "Creek Tower",
  location: "Dubai",
  units: 10,
  listed_units: 0,
  pledged_units: 0,
  sellable_units: 10,
  unit_price: "110.00",
  held_back: {},
  plan_units: 0,
  launch_price: "100.00",
  price_change_pct: "10.00",
  price_updated_at: "2026-09-28T09:00:00Z",
  average_cost: "100.00",
};

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ActiveInvestments />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ActiveInvestments: the unit price of each holding", () => {
  beforeEach(() => {
    holdings.mockReset();
    portfolio.mockReset();
    portfolio.mockResolvedValue({
      invested: "1000.00",
      current_value: "1100.00",
      total_returns: "0.00",
      properties: 1,
      units: 10,
      sold: "0.00",
    });
  });

  it("shows the price now, the change since launch and the gain on what was paid", async () => {
    holdings.mockResolvedValue({ items: [HOLDING], total: 1 });
    mount();
    const price = await screen.findByTestId("holding-price");
    expect(price).toHaveTextContent("Unit price now$110");
    expect(price).toHaveTextContent("+10.0% since launch");
    expect(price).toHaveTextContent("launched at $100 · updated Sep 28, 2026");
    expect(screen.getByText("bought at $100 on average")).toBeInTheDocument();
    expect(screen.getByText("+$100 on what you paid")).toBeInTheDocument(); // 10 × (110 − 100)
    expect(screen.queryByTestId("holding-plan-units")).toBeNull();
    expect(screen.queryByTestId("value-with-positions")).toBeNull(); // 10 × $110, nothing else
    // Sell opens the sell form on this property
    expect(screen.getByRole("link", { name: /^sell$/i })).toHaveAttribute(
      "href",
      "/secondary-market?tab=sell&property=prop-1",
    );
  });

  it("says a price that fell, in the same place", async () => {
    holdings.mockResolvedValue({
      items: [{ ...HOLDING, unit_price: "95.00", price_change_pct: "-5.00" }],
      total: 1,
    });
    mount();
    expect(await screen.findByTestId("holding-price")).toHaveTextContent("-5.0% since launch");
    expect(screen.getByText("−$50 on what you paid")).toBeInTheDocument();
  });

  it("shows units on a running plan as part of a position, not as listed for sale", async () => {
    // 3 of 4 units were paid for through a plan that is still running; 1 is listed
    holdings.mockResolvedValue({
      items: [
        {
          ...HOLDING,
          units: 4,
          listed_units: 4,
          sellable_units: 0,
          held_back: { listed: 1, installment_plan: 3 },
          plan_units: 3,
        },
      ],
      total: 1,
    });
    mount();
    const note = await screen.findByTestId("holding-plan-units");
    expect(note).toHaveTextContent(/3 of these units are on an installment plan you are still paying/);
    expect(within(note).getByRole("link", { name: /see the plan and sell it/i })).toHaveAttribute(
      "href",
      "/dashboard?tab=installments",
    );
    // "Listed for sale" counts what is really offered: 1, not the 4 held back
    expect(screen.getByText("Listed for sale").nextElementSibling).toHaveTextContent(/^1$/);
  });

  it("sends the Sell button of a holding that is only a plan to the plan itself", async () => {
    holdings.mockResolvedValue({
      items: [{ ...HOLDING, units: 3, sellable_units: 0, plan_units: 3, held_back: { installment_plan: 3 } }],
      total: 1,
    });
    mount();
    await screen.findByTestId("holding-price");
    expect(screen.getByRole("link", { name: /^sell$/i })).toHaveAttribute("href", "/dashboard?tab=installments");
  });

  it("does not explain a difference while the holdings are still loading", async () => {
    holdings.mockReturnValue(new Promise(() => {})); // never answers
    mount();
    expect(await screen.findByText("$1,100")).toBeInTheDocument(); // the server's total is in
    expect(screen.queryByTestId("value-with-positions")).toBeNull();
  });

  it("takes the total value from the server, so a plan counts as its position", async () => {
    // the holding alone is 3 × $110 = $330; the server values the whole plan position: $400
    holdings.mockResolvedValue({ items: [{ ...HOLDING, units: 3, plan_units: 3 }], total: 1 });
    portfolio.mockResolvedValue({
      invested: "300.00",
      current_value: "400.00",
      total_returns: "0.00",
      properties: 1,
      units: 3,
      sold: "0.00",
    });
    mount();
    await screen.findByTestId("holding-price");
    expect(await screen.findByText("$400")).toBeInTheDocument();
    // and says why it is not the sum of the cards below
    expect(screen.getByTestId("value-with-positions")).toHaveTextContent(/installment plans as positions/);
  });
});
