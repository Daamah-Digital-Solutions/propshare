/**
 * Phase 14: in REINVEST mode the calculator must call the server reinvest endpoint
 * (investApi.reinvest — the SERVER computes the discounted units/price), NOT the standard
 * create with a client-computed discounted amount. Proves the discount is server-applied
 * and the client never sends a price.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import InvestmentCalculator from "./InvestmentCalculator";

const createMock = vi.fn();
const reinvestMock = vi.fn();
const reinvestSettingsMock = vi.fn();

vi.mock("@/lib/api", () => ({
  investApi: {
    create: (...a: unknown[]) => createMock(...a),
    reinvest: (...a: unknown[]) => reinvestMock(...a),
    reinvestSettings: (...a: unknown[]) => reinvestSettingsMock(...a),
  },
  ApiError: class ApiError extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  },
}));

// Force reinvest mode via the context.
const clearReinvestment = vi.fn();
vi.mock("@/contexts/ReinvestContext", () => ({
  useReinvest: () => ({
    reinvestState: { isReinvesting: true, reinvestAmount: 1000 },
    setReinvestment: vi.fn(),
    clearReinvestment,
  }),
}));

const propertyData = {
  propertyValue: 100000,
  minInvestment: 100,
  maxInvestment: 100000,
  expectedYield: 8,
  totalReturn: 12,
  fundingProgress: 10,
  fundedAmount: 1000,
  investorsCount: 1,
  daysLeft: 0,
  fees: { platformFee: 2.5, managementFee: 1.0 },
};

function renderCalc() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <InvestmentCalculator
        propertyId="prop-123"
        propertyData={propertyData}
        investmentAmount={1000}
        setInvestmentAmount={() => {}}
      />
    </QueryClientProvider>,
  );
}

describe("InvestmentCalculator reinvest path", () => {
  beforeEach(() => {
    createMock.mockReset();
    reinvestMock.mockReset();
    reinvestSettingsMock.mockReset();
    reinvestSettingsMock.mockResolvedValue({ discount_pct: "5.0" });
    reinvestMock.mockResolvedValue({
      property_id: "prop-123",
      amount: "1000.00",
      discount_pct: "5.0",
      effective_price: "95.00",
      units: 10,
    });
  });

  it("confirms via investApi.reinvest (server-applied discount), not create", async () => {
    renderCalc();
    fireEvent.click(screen.getByRole("button", { name: /Reinvest \$1,000/i }));
    fireEvent.click(screen.getByRole("button", { name: /Confirm & Pay/i }));

    await waitFor(() => expect(reinvestMock).toHaveBeenCalledTimes(1));
    const [payload, key] = reinvestMock.mock.calls[0];
    // The client sends ONLY a property + amount — no price/units/discount.
    expect(payload).toEqual({ property_id: "prop-123", amount: 1000 });
    expect(typeof key).toBe("string");
    expect(createMock).not.toHaveBeenCalled();
  });
});
