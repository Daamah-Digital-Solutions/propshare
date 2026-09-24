/**
 * A sale prepared by the assistant arrives pre-filled: the property, units and price are set,
 * the banner says so, and the listing is created only by the user's own Create Listing click.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { create } = vi.hoisted(() => ({ create: vi.fn() }));
vi.mock("@/lib/api", () => ({
  ApiError: class extends Error {},
  holdingsApi: {
    mine: async () => ({
      items: [
        {
          property_id: "prop-1",
          title: "Marina Loft Income Suite",
          location: "Dubai",
          units: 10,
          listed_units: 0,
          sellable_units: 10,
          unit_price: "100.00",
        },
      ],
      total: 1,
    }),
  },
  secondaryApi: {
    settings: async () => ({ resale_fee_pct: "1.0", lockup_days: 0, price_min_pct: null, price_max_pct: null }),
    create: (...a: unknown[]) => create(...a),
  },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import SellUnitsForm from "./SellUnitsForm";

function show(prefill: Parameters<typeof SellUnitsForm>[0]["prefill"]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SellUnitsForm prefill={prefill} />
    </QueryClientProvider>,
  );
}

describe("SellUnitsForm — prepared by the assistant", () => {
  beforeEach(() => create.mockReset());

  it("arrives filled in and lists only on the user's click", async () => {
    create.mockResolvedValue({ listing_id: "l1" });
    show({ propertyId: "prop-1", units: 5, price: 110 });
    expect(screen.getByTestId("assistant-sale-banner")).toHaveTextContent(/nothing is listed before that/i);
    expect(screen.getByDisplayValue("5")).toBeInTheDocument();
    expect(screen.getByDisplayValue("110")).toBeInTheDocument();
    // the seller receives the full gross; the buyer pays the 1% on top
    expect(await screen.findByText("Receive $550.00")).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /create listing/i }));
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({ property_id: "prop-1", units: 5, price_per_unit: 110 }),
    );
    await waitFor(() => expect(screen.queryByTestId("assistant-sale-banner")).toBeNull());
  });

  it("shows no banner when opened normally", () => {
    show(null);
    expect(screen.queryByTestId("assistant-sale-banner")).toBeNull();
  });
});
