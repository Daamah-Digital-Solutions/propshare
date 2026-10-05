/**
 * Guards the Phase 8 secondary-market BUY click path at the component level: open a
 * listing -> enter units -> Confirm Purchase must actually call
 * POST /secondary/listings/{id}/buy (secondaryApi.buy) with the unit count and an
 * Idempotency-Key. This is the test that would have caught a dead/unwired
 * "Confirm Purchase" button.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
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

// SellUnitsForm has its own queries (tested in SellUnitsForm.test); the stub shows what the
// page hands it.
vi.mock("@/components/marketplace/SellUnitsForm", () => ({
  default: ({ prefill }: { prefill?: unknown }) => (
    <div data-testid="sell-form">{JSON.stringify(prefill ?? null)}</div>
  ),
}));
// likewise the form that sells a whole installment plan (SellPositionForm.test)
vi.mock("@/components/marketplace/SellPositionForm", () => ({
  default: ({ prefill }: { prefill?: unknown }) => (
    <div data-testid="sell-position-form">{JSON.stringify(prefill ?? null)}</div>
  ),
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

function Url() {
  const l = useLocation();
  return <div data-testid="url">{l.pathname + l.search}</div>;
}

function renderPage(url = "/secondary-market") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <SecondaryMarket />
        <Url />
      </MemoryRouter>
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

  it("opens Sell with the sale the assistant prepared, then consumes the link", async () => {
    renderPage("/secondary-market?tab=sell&property=prop-1&units=5&price=110.00");
    const form = await screen.findByTestId("sell-form");
    expect(JSON.parse(form.textContent ?? "null")).toEqual({ propertyId: "prop-1", units: 5, price: 110 });
    await waitFor(() => expect(screen.getByTestId("url").textContent).toBe("/secondary-market?tab=sell"));
  });

  it("opens the tab named in the link", async () => {
    renderPage("/secondary-market?tab=sell");
    expect(JSON.parse((await screen.findByTestId("sell-form")).textContent ?? "")).toBeNull();
    // the position form is offered there too, with nothing prepared
    expect(JSON.parse(screen.getByTestId("sell-position-form").textContent ?? "")).toBeNull();
  });
});

describe("SecondaryMarket: installment positions", () => {
  // a running plan offered whole: 10 units at $110, the buyer pays the seller $400 now
  const POSITION_LISTING = {
    ...LISTING,
    listing_id: "lst-pos",
    units_for_sale: 10,
    units_remaining: 10,
    price_per_unit: "110.00",
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
      cash: "400.00",
      resale_fee: "4.00",
      total_now: "404.00",
      installments_left: 2,
      overdue: 0,
      next_due: "2026-11-01",
      schedule: [],
    },
  };

  beforeEach(() => {
    buyMock.mockReset();
    settingsMock.mockResolvedValue({
      resale_fee_pct: "1.0",
      lockup_days: 0,
      price_min_pct: null,
      price_max_pct: null,
    });
    mineMock.mockResolvedValue({ items: [], total: 0 });
  });

  it("shows a position with its own card: what is paid now and what is taken over", async () => {
    listMock.mockResolvedValue({ items: [POSITION_LISTING, LISTING], total: 2 });
    renderPage();
    const card = await screen.findByTestId("position-listing");
    expect(card).toHaveTextContent("Installment position");
    expect(card).toHaveTextContent("You pay the seller now$400.00");
    expect(card).toHaveTextContent("Then 2 installment(s)$728.00");
    // it is bought whole from its own sheet, never through the unit count of a normal listing
    expect(screen.getAllByRole("button", { name: /Buy Units/i })).toHaveLength(1);
    expect(screen.getByRole("button", { name: /view & buy/i })).toBeInTheDocument();
  });

  it("opens Sell on the position a link prepared, then consumes the link", async () => {
    listMock.mockResolvedValue({ items: [], total: 0 });
    renderPage("/secondary-market?tab=sell&plan=plan-1&price=115.00");
    const form = await screen.findByTestId("sell-position-form");
    expect(JSON.parse(form.textContent ?? "null")).toEqual({ planId: "plan-1", price: 115 });
    // loose units are not prepared by a position link
    expect(JSON.parse(screen.getByTestId("sell-form").textContent ?? "")).toBeNull();
    await waitFor(() => expect(screen.getByTestId("url").textContent).toBe("/secondary-market?tab=sell"));
  });

  it("lists the seller's own position under My Listings with what a buyer pays", async () => {
    listMock.mockResolvedValue({ items: [], total: 0 });
    mineMock.mockResolvedValue({ items: [POSITION_LISTING], total: 1 });
    renderPage("/secondary-market?tab=activity");
    expect(await screen.findByText(/Installment position • 10 units/)).toHaveTextContent(
      "a buyer pays you $400.00",
    );
  });
});
