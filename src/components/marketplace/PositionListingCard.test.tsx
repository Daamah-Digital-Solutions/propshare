/**
 * A listing that offers an installment plan (client meeting 2026-10-01: the buyer pays the
 * seller what was paid plus the increase, and continues the remaining installments). Since
 * 2026-11-08 a buyer can take some of the units: the card then shows the server's quote for
 * that part (its share of every payment) before anything is bought.
 * The card shows the server's figures as they are, asks the buyer to accept the installments
 * before the button works, and sends back the amount it showed so that a position that
 * changed meanwhile is never bought unseen.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SecondaryListing } from "@/lib/api";

const { buy, quote, toastError, toastSuccess } = vi.hoisted(() => ({
  buy: vi.fn(),
  quote: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    secondaryApi: {
      buy: (...a: unknown[]) => buy(...a),
      quote: (...a: unknown[]) => quote(...a),
    },
  };
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
    quote.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
  });

  it("shows what is paid now and what is taken over, from the server's figures", async () => {
    mount();
    const card = screen.getByTestId("position-listing");
    expect(card).toHaveTextContent("Installment position");
    expect(card).toHaveTextContent("Units for sale10 of 10 on the plan");
    expect(card).toHaveTextContent("You can buy some of them");
    expect(card).toHaveTextContent("You pay the seller now$400.00");
    expect(card).toHaveTextContent("Then 2 installment(s)$728.00"); // 700 principal + 28 fees
    expect(card).toHaveTextContent("next Nov 1, 2026");

    fireEvent.click(screen.getByRole("button", { name: /view & buy/i }));
    const sheet = await screen.findByTestId("position-buy");
    expect(sheet).toHaveTextContent("Value (10 × $110)$1,100.00");
    expect(sheet).toHaveTextContent("−$700.00");
    expect(sheet).toHaveTextContent(
      "= $300.00 paid on these units + $100.00 price increase on 10 units since the plan started",
    );
    expect(sheet).toHaveTextContent("All the plan's units: the plan itself becomes yours.");
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
    expect(units).toBe(10); // every unit listed, unless the buyer chooses fewer
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
    expect(sheet).toHaveTextContent("= $300.00 paid on these units + $100.00 price increase");
    expect(sheet).not.toHaveTextContent("$350.00");
  });

  it("says when installments are already due", async () => {
    mount({ ...LISTING, position: { ...LISTING.position!, overdue: 1 } } as SecondaryListing);
    fireEvent.click(screen.getByRole("button", { name: /view & buy/i }));
    expect(
      await screen.findByText(/1 already due: charged at the next automatic charge/i),
    ).toBeInTheDocument();
  });

  it("shows the part a buyer chooses, from the server's quote, and buys that part", async () => {
    // 3 of the 10: 3 x 110 = 330, less 30% of the 700 = 210 -> 120 to the seller
    quote.mockResolvedValue({
      ...LISTING.position!,
      units: 3,
      plan_units: 10,
      vested_units: 0,
      value: "330.00",
      paid_principal: "90.00",
      remaining_principal: "210.00",
      remaining_fees: "8.40",
      gain: "30.00",
      cash: "120.00",
      resale_fee: "1.20",
      total_now: "121.20",
      listing_id: "lst-9",
      units_remaining: 10,
      whole: false,
      schedule: [
        { seq: 4, kind: "installment", due_date: "2026-11-01", base_amount: "105.00", fee_amount: "4.20", total_amount: "109.20", status: "scheduled" },
        { seq: 5, kind: "final", due_date: "2026-12-01", base_amount: "105.00", fee_amount: "4.20", total_amount: "109.20", status: "scheduled" },
      ],
    });
    buy.mockResolvedValue({ trade_id: "t-1", units: 3, total_charged: "121.20" });
    mount();
    fireEvent.click(screen.getByRole("button", { name: /view & buy/i }));
    const sheet = await screen.findByTestId("position-buy");
    fireEvent.change(within(sheet).getByTestId("position-units"), { target: { value: "3" } });
    await waitFor(() => expect(quote).toHaveBeenCalledWith("lst-9", 3));
    await waitFor(() => expect(sheet).toHaveTextContent("Value (3 × $110)$330.00"));
    expect(sheet).toHaveTextContent("Part of the plan: these units become an installment plan in your name");
    expect(sheet).toHaveTextContent("You pay the seller now$120.00");
    expect(sheet).toHaveTextContent("Charged from your wallet now$121.20");
    const rows = within(sheet).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Month 4Nov 1, 2026$109.20");
    expect(rows[3]).toHaveTextContent("Total still to pay$218.40");
    fireEvent.click(within(sheet).getByRole("checkbox"));
    fireEvent.click(within(sheet).getByRole("button", { name: /Pay \$121\.20 for 3 unit\(s\)/ }));
    await waitFor(() => expect(buy).toHaveBeenCalledTimes(1));
    const [listingId, units, , expectedCash, expectedFee] = buy.mock.calls[0];
    expect([listingId, units, expectedCash, expectedFee]).toEqual(["lst-9", 3, "120.00", "1.20"]);
  });
});
