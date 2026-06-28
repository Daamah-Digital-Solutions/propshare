/**
 * Guards the Phase 9 ACTIVE fund click path at the component level: a live exit request
 * renders -> Review & Provide -> enter units -> Confirm Allocation must call
 * POST /liquidity/exit-requests/{id}/fund (liquidityApi.fund) with the units + an
 * Idempotency-Key. This is the test that would catch a dead/unwired "Confirm Allocation".
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import LiquidityProviderMarket from "./LiquidityProviderMarket";

const fundMock = vi.fn();
const listOpenMock = vi.fn();
const positionsMock = vi.fn();

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  },
  liquidityApi: {
    listOpen: (...a: unknown[]) => listOpenMock(...a),
    positions: (...a: unknown[]) => positionsMock(...a),
    fund: (...a: unknown[]) => fundMock(...a),
  },
}));

const REQUEST = {
  request_id: "req-1",
  property_id: "prop-1",
  property_title: "Marina Heights Tower",
  property_location: "Dubai Marina, UAE",
  seller_id: "seller-1",
  units: 10,
  units_remaining: 10,
  unit_price: "100.00",
  discount_pct: "3.0",
  fee_pct: "2.0",
  gross: "1000.00",
  lp_price: "970.00",
  liquidity_fee: "19.40",
  seller_net: "950.60",
  status: "open",
  created_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 3_600_000).toISOString(),
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LiquidityProviderMarket />
    </QueryClientProvider>,
  );
}

describe("LiquidityProviderMarket fund click path", () => {
  beforeEach(() => {
    fundMock.mockReset();
    listOpenMock.mockResolvedValue({ items: [REQUEST], total: 1 });
    positionsMock.mockResolvedValue({ items: [], total: 0 });
  });

  it("calls the fund API with units + Idempotency-Key on Confirm Allocation", async () => {
    fundMock.mockResolvedValue({
      position_id: "pos-1",
      classification: "active",
      property_id: "prop-1",
      units_acquired: 10,
      principal: "970.00",
      spread_at_entry: "30.00",
      status: "active",
      created_at: new Date().toISOString(),
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Review & Provide/i }));
    fireEvent.change(await screen.findByPlaceholderText(/Enter units/i), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Confirm Allocation/i }));

    await waitFor(() => expect(fundMock).toHaveBeenCalledTimes(1));
    const [requestId, units, idempotencyKey] = fundMock.mock.calls[0];
    expect(requestId).toBe("req-1");
    expect(units).toBe(10);
    expect(typeof idempotencyKey).toBe("string");
    expect(idempotencyKey.length).toBeGreaterThan(0);
  });
});
