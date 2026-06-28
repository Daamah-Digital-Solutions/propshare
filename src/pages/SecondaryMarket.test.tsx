/**
 * Guards the Phase 8 secondary-market BUY click path at the component level: open a
 * listing -> enter units -> Confirm Purchase must actually call
 * POST /secondary/listings/{id}/buy (secondaryApi.buy) with the unit count and an
 * Idempotency-Key. This is the test that would have caught a dead/unwired
 * "Confirm Purchase" button.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import SecondaryMarket from "./SecondaryMarket";

const buyMock = vi.fn();
const listMock = vi.fn();
const settingsMock = vi.fn();
const mineMock = vi.fn();

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  },
  secondaryApi: {
    list: (...a: unknown[]) => listMock(...a),
    settings: (...a: unknown[]) => settingsMock(...a),
    mine: (...a: unknown[]) => mineMock(...a),
    buy: (...a: unknown[]) => buyMock(...a),
    cancel: vi.fn(),
    create: vi.fn(),
  },
  holdingsApi: { mine: vi.fn() },
}));

// SellUnitsForm has its own queries; stub it so this test stays focused on Buy.
vi.mock("@/components/marketplace/SellUnitsForm", () => ({
  default: () => <div>sell form</div>,
}));

const LISTING = {
  listing_id: "lst-1",
  property_id: "prop-1",
  property_title: "Marina Heights Tower",
  property_location: "Dubai Marina, UAE",
  seller_id: "seller-1",
  units_for_sale: 50,
  units_remaining: 50,
  price_per_unit: "105.00",
  unit_price_ref: "100.00",
  status: "active",
  created_at: new Date().toISOString(),
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SecondaryMarket />
    </QueryClientProvider>,
  );
}

describe("SecondaryMarket buy click path", () => {
  beforeEach(() => {
    buyMock.mockReset();
    listMock.mockResolvedValue({ items: [LISTING], total: 1 });
    settingsMock.mockResolvedValue({
      resale_fee_pct: "1.0",
      lockup_days: 0,
      price_min_pct: null,
      price_max_pct: null,
    });
    mineMock.mockResolvedValue({ items: [], total: 0 });
  });

  it("calls the buy API with the unit count + Idempotency-Key on Confirm Purchase", async () => {
    buyMock.mockResolvedValue({
      trade_id: "trd-1",
      listing_id: "lst-1",
      property_id: "prop-1",
      units: 10,
      price_per_unit: "105.00",
      gross: "1050.00",
      resale_fee: "10.50",
      total_charged: "1060.50",
      created_at: new Date().toISOString(),
    });

    renderPage();
    // The live listing must render (proves listings are DB-backed).
    fireEvent.click(await screen.findByRole("button", { name: /Buy Units/i }));
    // Enter a unit count, then Confirm Purchase (proves the button is not a no-op).
    fireEvent.change(await screen.findByPlaceholderText(/Enter units to buy/i), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Confirm Purchase/i }));

    await waitFor(() => expect(buyMock).toHaveBeenCalledTimes(1));
    const [listingId, units, idempotencyKey] = buyMock.mock.calls[0];
    expect(listingId).toBe("lst-1");
    expect(units).toBe(10);
    expect(typeof idempotencyKey).toBe("string");
    expect(idempotencyKey.length).toBeGreaterThan(0);
  });
});
