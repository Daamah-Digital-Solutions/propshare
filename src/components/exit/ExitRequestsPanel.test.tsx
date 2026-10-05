/**
 * An investor's instant-exit request to the liquidity providers shows in their exit requests
 * (waiting, then paid) and can be cancelled while it waits — not only secondary listings.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { api, listings } = vi.hoisted(() => ({
  api: { cancelRequest: vi.fn(), cancelListing: vi.fn(), myRequests: vi.fn() },
  listings: { items: [] as unknown[] },
}));
vi.mock("@/lib/api", () => ({
  secondaryApi: {
    mine: async () => ({ items: listings.items }),
    cancel: (...a: unknown[]) => api.cancelListing(...a),
  },
  liquidityApi: {
    myRequests: (...a: unknown[]) => api.myRequests(...a),
    cancelRequest: (...a: unknown[]) => api.cancelRequest(...a),
  },
  holdingsApi: { mine: async () => ({ items: [] }) },
}));
vi.mock("./ExitButton", () => ({ ExitButton: () => <button>exit</button> }));

import { ExitRequestsPanel } from "./ExitRequestsPanel";

const lpRequest = (status: string) => ({
  request_id: "lp-1",
  property_id: "prop-1",
  property_title: "Marina Heights",
  property_location: "Dubai",
  seller_id: "me",
  units: 10,
  units_remaining: status === "filled" ? 0 : 10,
  unit_price: "100.00",
  discount_pct: "3.0",
  fee_pct: "2.0",
  gross: "1000.00",
  lp_price: "970.00",
  liquidity_fee: "19.40",
  seller_net: "950.60",
  status,
  created_at: "2026-09-27T09:00:00Z",
  expires_at: "2026-09-28T09:00:00Z",
});

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ExitRequestsPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ExitRequestsPanel — instant exits to the liquidity providers", () => {
  beforeEach(() => {
    Object.values(api).forEach((f) => f.mockReset());
    listings.items = [];
  });

  it("shows a waiting request and cancels it through the liquidity API", async () => {
    api.myRequests.mockResolvedValue({ items: [lpRequest("open")], total: 1 });
    api.cancelRequest.mockResolvedValue({ request_id: "lp-1", status: "cancelled" });
    mount();
    expect(await screen.findByText("Marina Heights")).toBeInTheDocument();
    expect(screen.getByText(/Waiting for a liquidity provider/)).toBeInTheDocument();
    expect(screen.getByText("Liquidity provider")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(api.cancelRequest).toHaveBeenCalledWith("lp-1"));
    expect(api.cancelListing).not.toHaveBeenCalled();
  });

  it("shows a request that expired partly funded as partly paid, with the part paid", async () => {
    api.myRequests.mockResolvedValue({
      items: [{ ...lpRequest("expired"), units_remaining: 6 }],
      total: 1,
    });
    mount();
    fireEvent.mouseDown(await screen.findByRole("tab", { name: /Completed/i }));
    expect(await screen.findByText(/Partly funded: 4 of 10 units paid to your wallet; the rest expired/)).toBeInTheDocument();
    expect(screen.getByText("$380.24")).toBeInTheDocument(); // 950.60 / 10 x 4
  });

  it("shows an installment position for what its seller is paid, not units x price", async () => {
    // 10 units at $110 on a plan with $700 still to pay: the seller is paid $400, not $1,100
    const position = {
      listing_id: "lst-1",
      property_id: "prop-1",
      property_title: "Creek Tower",
      property_location: "Dubai",
      seller_id: "me",
      units_for_sale: 10,
      units_remaining: 10,
      price_per_unit: "110.00",
      unit_price_ref: "110.00",
      status: "active",
      created_at: "2026-10-01T09:00:00Z",
      plan_id: "plan-1",
      position: { cash: "400.00" },
      cash: "400.00",
    };
    listings.items = [position];
    api.myRequests.mockResolvedValue({ items: [], total: 0 });
    const { unmount } = mount();
    expect(await screen.findByText("Creek Tower")).toBeInTheDocument();
    expect(screen.getAllByText("$400").length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toContain("$1,100");
    unmount();

    // once sold the row no longer carries the position: what it was sold for stays
    listings.items = [{ ...position, status: "sold", units_remaining: 0, position: null }];
    mount();
    fireEvent.mouseDown(await screen.findByRole("tab", { name: /Completed/i }));
    expect(await screen.findByText("Creek Tower")).toBeInTheDocument();
    expect(screen.getAllByText("$400").length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toContain("$1,100");
  });

  it("shows a funded request as paid, with what the seller received", async () => {
    api.myRequests.mockResolvedValue({ items: [lpRequest("filled")], total: 1 });
    mount();
    fireEvent.mouseDown(await screen.findByRole("tab", { name: /Completed/i }));
    expect(await screen.findByText("Paid to your wallet")).toBeInTheDocument();
    expect(screen.getByText("$950.6")).toBeInTheDocument();
  });
});
