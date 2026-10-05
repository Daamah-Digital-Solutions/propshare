/**
 * Selling a running installment plan as one position: the form previews "value at my price,
 * less what is still to pay = what I receive", refuses a price that does not cover what is
 * still to pay, says why a plan cannot be listed, and lists the plan only on the click.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MyPosition } from "@/lib/api";

const { positions, create, toastSuccess } = vi.hoisted(() => ({
  positions: vi.fn(),
  create: vi.fn(),
  toastSuccess: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    secondaryApi: {
      positions: () => positions(),
      settings: async () => ({ resale_fee_pct: "1.0", lockup_days: 0, price_min_pct: null, price_max_pct: null }),
      create: (...a: unknown[]) => create(...a),
    },
  };
});
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: toastSuccess } }));

import SellPositionForm from "./SellPositionForm";

// 10 units bought at $100 on a plan, $300 of principal paid, the unit price is now $110
const POSITION: MyPosition = {
  plan_id: "plan-1",
  property_id: "prop-1",
  property_title: "Creek Tower",
  property_location: "Dubai",
  unit_price: "110.00",
  units: 10,
  vested_units: 3,
  locked_price: "100.00",
  entry_price: "100.00",
  price: "110.00",
  value: "1100.00",
  cost: "300.00",
  paid_principal: "300.00",
  remaining_principal: "700.00",
  remaining_fees: "28.00",
  gain: "100.00",
  cash: "400.00",
  resale_fee: "4.00",
  total_now: "404.00",
  installments_left: 2,
  overdue: 0,
  next_due: "2026-11-01",
  schedule: [],
  listing_id: null,
  blocked: null,
  lockup_until: null,
};

function mount(prefill?: { planId: string; price?: number }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SellPositionForm prefill={prefill ?? null} />
    </QueryClientProvider>,
  );
}

describe("SellPositionForm", () => {
  beforeEach(() => {
    positions.mockReset();
    create.mockReset();
    toastSuccess.mockReset();
  });

  it("is not shown to an investor with no running plan", async () => {
    positions.mockResolvedValue({ items: [], total: 0 });
    const { container } = mount();
    await waitFor(() => expect(positions).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("previews what the seller receives at the asking price and lists on the click", async () => {
    positions.mockResolvedValue({ items: [POSITION], total: 1 });
    create.mockResolvedValue({ listing_id: "lst-1", position: { cash: "500.00" } });
    mount();
    const row = await screen.findByTestId("position-row");
    expect(row).toHaveTextContent("10 units on the plan · 3 paid for · 2 installment(s) left, next Nov 1, 2026");
    expect(row).toHaveTextContent("Bought at $100 · now $110");
    // at the current price: 1,100 - 700 = 400 = the 300 paid + 100 increase on all 10 units
    expect(row).toHaveTextContent("You receive$400.00");
    expect(row).toHaveTextContent("= $300.00 you put in + $100.00 price increase on all 10 units");
    expect(row).toHaveTextContent("Installment fees you paid are not returned");
    expect(row).toHaveTextContent("The buyer pays a 1% fee on top");
    expect(create).not.toHaveBeenCalled();

    // the seller's own price moves the amount: 10 x 120 - 700 = 500
    fireEvent.change(within(row).getByLabelText(/asking price per unit/i), { target: { value: "120" } });
    expect(row).toHaveTextContent("You receive$500.00");
    fireEvent.click(within(row).getByRole("button", { name: /list this position/i }));
    await waitFor(() => expect(create).toHaveBeenCalledWith({ plan_id: "plan-1", price_per_unit: 120 }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Position listed", expect.anything()));
  });

  it("previews and lists at the price in cents, as the server keeps it", async () => {
    positions.mockResolvedValue({ items: [POSITION], total: 1 });
    create.mockResolvedValue({ listing_id: "lst-1", position: { cash: "405.60" } });
    mount();
    const row = await screen.findByTestId("position-row");
    fireEvent.change(within(row).getByLabelText(/asking price per unit/i), { target: { value: "110.555" } });
    // 110.56 a unit: 1,105.60 - 700, not 1,105.55 - 700
    expect(row).toHaveTextContent("Position value (10 × $110.56)$1,105.60");
    expect(row).toHaveTextContent("You receive$405.60");
    fireEvent.click(within(row).getByRole("button", { name: /list this position/i }));
    await waitFor(() => expect(create).toHaveBeenCalledWith({ plan_id: "plan-1", price_per_unit: 110.56 }));
  });

  it("refuses a price that does not cover what is still to pay", async () => {
    positions.mockResolvedValue({ items: [POSITION], total: 1 });
    mount();
    const row = await screen.findByTestId("position-row");
    expect(row).toHaveTextContent("Must be above $70.00"); // 700 still to pay / 10 units
    fireEvent.change(within(row).getByLabelText(/asking price per unit/i), { target: { value: "70" } });
    expect(within(row).getByRole("button", { name: /list this position/i })).toBeDisabled();
  });

  it("measures a plan that was bought from what its buyer paid for it", async () => {
    // taken over at $110 a unit (400 paid for it); the unit price is now $121
    positions.mockResolvedValue({
      items: [{ ...POSITION, entry_price: "110.00", unit_price: "121.00", price: "121.00", cost: "400.00" }],
      total: 1,
    });
    mount();
    const row = await screen.findByTestId("position-row");
    expect(row).toHaveTextContent("Bought at $110 · now $121");
    // 10 x 121 - 700 = 510 = the 400 put in + 110 (11 a unit on all 10 units)
    expect(row).toHaveTextContent("You receive$510.00");
    expect(row).toHaveTextContent("= $400.00 you put in + $110.00 price increase on all 10 units");
  });

  it("says why a position cannot be listed instead of offering the form", async () => {
    positions.mockResolvedValue({
      items: [
        { ...POSITION, blocked: "pledged" },
        { ...POSITION, plan_id: "plan-2", blocked: "lockup", lockup_until: "2026-12-15" },
        { ...POSITION, plan_id: "plan-3", blocked: "listed", listing_id: "lst-7" },
      ],
      total: 3,
    });
    mount();
    const rows = await screen.findAllByTestId("position-row");
    expect(rows[0]).toHaveTextContent(/pledged to Nova Finance/i);
    expect(rows[1]).toHaveTextContent("lock-up until Dec 15, 2026");
    expect(rows[2]).toHaveTextContent(/already listed for sale/i);
    expect(screen.queryByRole("button", { name: /list this position/i })).toBeNull();
  });

  it("opens on the position a link prepared, with its price, and still waits for the click", async () => {
    positions.mockResolvedValue({
      items: [POSITION, { ...POSITION, plan_id: "plan-2", property_title: "Harbour Gate" }],
      total: 2,
    });
    mount({ planId: "plan-2", price: 115 });
    const rows = await screen.findAllByTestId("position-row");
    // the one asked for comes first, marked as prepared, with the price filled in
    expect(rows[0]).toHaveTextContent("Harbour Gate");
    expect(within(rows[0]).getByTestId("position-prepared-banner")).toHaveTextContent(/nothing is listed before that/i);
    expect(within(rows[0]).getByLabelText(/asking price per unit/i)).toHaveValue(115);
    expect(within(rows[1]).queryByTestId("position-prepared-banner")).toBeNull();
    expect(create).not.toHaveBeenCalled();
  });
});
