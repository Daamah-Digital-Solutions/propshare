/**
 * Reports: the unit price over time of what the investor holds (client meeting 2026-10-01:
 * "a chart in Reports & Analytics"). A property whose price moved gets its line and its
 * latest changes; the figures are the server's.
 */
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { InstallmentPlan } from "@/lib/api";

const { holdings, prices } = vi.hoisted(() => ({ holdings: vi.fn(), prices: vi.fn() }));
vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    holdingsApi: { mine: () => holdings() },
    propertyApi: { prices: async (id: string) => prices(id) },
  };
});

import UnitPriceReport from "./UnitPriceReport";

const point = (at: string, price: string, change: string, label: string | null = null) => ({
  at,
  price,
  change_pct: change,
  label,
  note: null,
});
const MOVED = {
  property_id: "prop-1",
  current_price: "115.00",
  launch_price: "100.00",
  change_pct: "15.00",
  updated_at: "2026-09-01T09:00:00Z",
  phase: "Phase 3",
  points: [
    point("2026-01-01T00:00:00Z", "100.00", "0.00", "Launch price"),
    point("2026-05-01T09:00:00Z", "110.00", "10.00", "Phase 2"),
    point("2026-09-01T09:00:00Z", "115.00", "4.55", "Phase 3"),
  ],
};
const FLAT = {
  property_id: "prop-2",
  current_price: "50.00",
  launch_price: "50.00",
  change_pct: "0.00",
  updated_at: null,
  phase: null,
  points: [point("2026-02-01T00:00:00Z", "50.00", "0.00", "Launch price")],
};
const holding = (id: string, title: string, cost: string) => ({
  property_id: id,
  title,
  location: null,
  units: 10,
  listed_units: 0,
  sellable_units: 10,
  unit_price: "0",
  average_cost: cost,
});

function mount(plans: InstallmentPlan[] = []) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UnitPriceReport plans={plans} />
    </QueryClientProvider>,
  );
}

describe("UnitPriceReport", () => {
  beforeEach(() => {
    holdings.mockReset();
    prices.mockReset();
    prices.mockImplementation((id: string) => (id === "prop-1" ? MOVED : FLAT));
  });

  it("is not shown to someone who holds nothing", async () => {
    holdings.mockResolvedValue({ items: [], total: 0 });
    const { container } = mount();
    await vi.waitFor(() => expect(holdings).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("charts each property whose price moved, against what the investor paid", async () => {
    holdings.mockResolvedValue({
      items: [holding("prop-1", "Creek Tower", "110.00"), holding("prop-2", "Marina Loft", "50.00")],
      total: 2,
    });
    mount();
    const chart = await screen.findByTestId("unit-price-chart");
    expect(screen.getAllByTestId("unit-price-chart")).toHaveLength(1); // the flat one has no chart
    expect(chart).toHaveTextContent("Creek Tower");
    expect(chart).toHaveTextContent("Launched at $100 · Phase 3 · updated Sep 1, 2026");
    expect(chart).toHaveTextContent("$115");
    expect(chart).toHaveTextContent("+15% since launch");
    // bought in phase 2 at $110: +4.55% at the price now
    expect(chart).toHaveTextContent("You paid $110 a unit on average: +4.55% at the price now.");
    const history = within(chart).getByTestId("unit-price-history");
    expect(history).toHaveTextContent("Sep 1, 2026Phase 3$115 +4.55%");
    expect(history).toHaveTextContent("May 1, 2026Phase 2$110 +10%");
  });

  it("says so when no price has moved yet", async () => {
    holdings.mockResolvedValue({ items: [holding("prop-2", "Marina Loft", "50.00")], total: 1 });
    mount();
    expect(await screen.findByText(/has not changed since launch/i)).toBeInTheDocument();
    expect(screen.queryByTestId("unit-price-chart")).toBeNull();
  });

  it("follows a property the investor is still paying for, at the price the plan locked", async () => {
    holdings.mockResolvedValue({ items: [], total: 0 });
    mount([
      { id: "pl1", property_id: "prop-1", property_title: "Creek Tower", status: "active", unit_price: "100.00" },
      // a plan that never started is not followed
      { id: "pl2", property_id: "prop-2", property_title: "Marina Loft", status: "cancelled", unit_price: "50.00" },
    ] as InstallmentPlan[]);
    const chart = await screen.findByTestId("unit-price-chart");
    expect(chart).toHaveTextContent("You paid $100 a unit on average: +15% at the price now.");
    expect(prices).toHaveBeenCalledWith("prop-1");
    expect(prices).not.toHaveBeenCalledWith("prop-2");
  });

  it("measures a plan that was bought from the price its holder bought it at", async () => {
    holdings.mockResolvedValue({ items: [], total: 0 });
    mount([
      {
        id: "pl1",
        property_id: "prop-1",
        property_title: "Creek Tower",
        status: "active",
        unit_price: "100.00", // what the plan locked for its first holder
        position: { entry_price: "110.00" }, // what this holder paid a unit
      },
    ] as InstallmentPlan[]);
    const chart = await screen.findByTestId("unit-price-chart");
    expect(chart).toHaveTextContent("You paid $110 a unit on average: +4.55% at the price now.");
  });
});
