/**
 * A listing that offers a whole installment plan (client meeting 2026-10-01: the buyer pays
 * the seller what was paid plus the increase, and continues the remaining installments).
 * The card shows the server's figures as they are, asks the buyer to accept the installments
 * before the button works, and sends back the amount it showed so that a position that
 * changed meanwhile is never bought unseen.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SecondaryListing } from "@/lib/api";

const { buy, toastError, toastSuccess } = vi.hoisted(() => ({
  buy: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return { ...real, secondaryApi: { buy: (...a: unknown[]) => buy(...a) } };
});
vi.mock("sonner", () => ({ toast: { error: toastError, success: toastSuccess } }));

import { ApiError } from "@/lib/api";
import PositionListingCard from "./PositionListingCard";

// 10 units bought at $100 on a plan; $300 of principal paid; the seller asks $110 a unit:
// value 1,100 - 700 still to pay = 400 to the seller (300 paid + 100 increase on all 10 units)
const LISTING: SecondaryListing = {
  listing_id: "lst-9",
  property_id: "prop-1",
  property_title: "Creek Tower",
  property_location: "Dubai Creek Harbour",
  seller_id: "seller-1",
  units_for_sale: 10,
  units_remaining: 10,
  price_per_unit: "110.00",
  unit_price_ref: "110.00",
  status: "active",
  created_at: "2026-10-01T10:00:00Z",
  plan_id: "plan-1",
  position: {
    plan_id: "plan-1",
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
    installments_left: 2,
    overdue: 0,
    next_due: "2026-11-01",
    cash: "400.00",
    resale_fee: "4.00",
    total_now: "404.00",
    schedule: [
      { seq: 4, kind: "installment", due_date: "2026-11-01", base_amount: "350.00", fee_amount: "14.00", total_amount: "364.00", status: "scheduled" },
      { seq: 5, kind: "final", due_date: "2026-12-01", base_amount: "350.00", fee_amount: "14.00", total_amount: "364.00", status: "scheduled" },
    ],
  },
} as SecondaryListing;

function mount(listing: SecondaryListing = LISTING) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(qc, "invalidateQueries");
  render(
    <QueryClientProvider client={qc}>
      <PositionListingCard listing={listing} feePct={1} listedAgo="2h ago" />
    </QueryClientProvider>,
  );
  return { invalidate };
}

describe("PositionListingCard", () => {
  beforeEach(() => {
    buy.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
  });

  it("shows what is paid now and what is taken over, from the server's figures", async () => {
    mount();
    const card = screen.getByTestId("position-listing");
    expect(card).toHaveTextContent("Installment position");
    expect(card).toHaveTextContent("10 · 3 paid for");
    expect(card).toHaveTextContent("You pay the seller now$400.00");
    expect(card).toHaveTextContent("Then 2 installment(s)$728.00"); // 700 principal + 28 fees
    expect(card).toHaveTextContent("next Nov 1, 2026");

    fireEvent.click(screen.getByRole("button", { name: /view & buy/i }));
    const sheet = await screen.findByTestId("position-buy");
    expect(sheet).toHaveTextContent("Position value (10 × $110)$1,100.00");
    expect(sheet).toHaveTextContent("−$700.00");
    expect(sheet).toHaveTextContent(
      "= $300.00 paid on the plan + $100.00 price increase on all 10 units since it started",
    );
    expect(sheet).toHaveTextContent("Purchase Fee (1%)+$4.00");
    expect(sheet).toHaveTextContent("Charged from your wallet now$404.00");
    // the schedule the buyer takes over, with its dates
    const rows = within(sheet).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Month 4Nov 1, 2026$364.00");
    expect(rows[2]).toHaveTextContent("Final (month 5)Dec 1, 2026$364.00");
    expect(rows[3]).toHaveTextContent("Total still to pay$728.00");
  });

  it("buys only after the installments are accepted, sending back the amount shown", async () => {
    buy.mockResolvedValue({ trade_id: "t1", total_charged: "404.00" });
    const { invalidate } = mount();
    fireEvent.click(screen.getByRole("button", { name: /view & buy/i }));
    const pay = await screen.findByRole("button", { name: /Pay \$404\.00 and take over the plan/i });
    expect(pay).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /I take over the remaining installments/i }));
    expect(pay).toBeEnabled();
    fireEvent.click(pay);

    await waitFor(() => expect(buy).toHaveBeenCalledTimes(1));
    const [listingId, units, key, expectedCash, expectedFee] = buy.mock.calls[0];
    expect(listingId).toBe("lst-9");
    expect(units).toBe(10); // the whole position, never a part of it
    expect(typeof key).toBe("string");
    expect(expectedCash).toBe("400.00");
    expect(expectedFee).toBe("4.00"); // the fee shown is confirmed with the amount
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["installments"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["wallet"] });
  });

  it("asks again when the position changed since it was shown", async () => {
    buy.mockImplementation(async () => {
      throw new ApiError("POSITION_CHANGED", "This position changed since you opened it.", 409);
    });
    const { invalidate } = mount();
    fireEvent.click(screen.getByRole("button", { name: /view & buy/i }));
    const box = await screen.findByRole("checkbox", { name: /I take over the remaining installments/i });
    fireEvent.click(box);
    fireEvent.click(screen.getByRole("button", { name: /take over the plan/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith("The amounts changed", expect.anything()));
    // the fresh figures are fetched and the acceptance is asked for again
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["secondary"] });
    await waitFor(() => expect(box).not.toBeChecked());
    expect(screen.getByRole("button", { name: /take over the plan/i })).toBeDisabled();
  });

  it("explains the amount by the plan's own figures, whoever the seller is", async () => {
    // A buyer needs what was paid on the plan and how far the price moved since it started.
    // Even if a payload carried the seller's own cost, the card would not print it.
    mount({
      ...LISTING,
      position: { ...LISTING.position!, entry_price: "105.00", cost: "350.00" },
    } as SecondaryListing);
    fireEvent.click(screen.getByRole("button", { name: /view & buy/i }));
    const sheet = await screen.findByTestId("position-buy");
    expect(sheet).toHaveTextContent("= $300.00 paid on the plan + $100.00 price increase");
    expect(sheet).not.toHaveTextContent("$350.00");
  });

  it("says when installments are already due", async () => {
    mount({ ...LISTING, position: { ...LISTING.position!, overdue: 1 } } as SecondaryListing);
    fireEvent.click(screen.getByRole("button", { name: /view & buy/i }));
    expect(
      await screen.findByText(/1 already due: charged at the next automatic charge/i),
    ).toBeInTheDocument();
  });
});
