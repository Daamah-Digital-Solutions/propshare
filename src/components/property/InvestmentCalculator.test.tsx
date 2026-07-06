/**
 * Guards the Phase 5 invest click path end-to-end at the component level: select a
 * funding method -> Invest -> Confirm & Pay must actually call POST /investments
 * (investApi.create) with the property id, amount, method, and an Idempotency-Key.
 * This is the test that would have caught a dead/unwired "Invest" button.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import InvestmentCalculator from "./InvestmentCalculator";
import { ReinvestProvider } from "@/contexts/ReinvestContext";

// Mock the API client — keep ApiError a real class so `instanceof` checks work.
const createMock = vi.fn();
vi.mock("@/lib/api", () => ({
  investApi: {
    create: (...args: unknown[]) => createMock(...args),
    pronovaSettings: () => Promise.resolve({ discount_pct: "5.0" }),
    reinvestSettings: () => Promise.resolve({ discount_pct: "5.0" }),
  },
  ApiError: class ApiError extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  },
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
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ReinvestProvider>
        <InvestmentCalculator
          propertyId="prop-123"
          propertyData={propertyData}
          investmentAmount={1000}
          setInvestmentAmount={() => {}}
        />
      </ReinvestProvider>
    </QueryClientProvider>,
  );
}

describe("InvestmentCalculator invest click path", () => {
  beforeEach(() => createMock.mockReset());

  it("calls the invest API with wallet method + Idempotency-Key on Confirm & Pay", async () => {
    createMock.mockResolvedValue({
      investment_id: "inv-1",
      property_id: "prop-123",
      status: "confirmed",
      units: 10,
      amount: "1000.00",
      platform_fee: "25.00",
      total_charged: "1025.00",
      management_fee_rate: "1.0",
      checkout_url: null,
    });

    renderCalc();
    // The Invest CTA must open the confirmation (proves the button is not a no-op).
    fireEvent.click(screen.getByRole("button", { name: /Invest \$1,000/i }));
    fireEvent.click(screen.getByRole("button", { name: /Confirm & Pay/i }));

    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    const [payload, idempotencyKey] = createMock.mock.calls[0];
    expect(payload).toEqual({ property_id: "prop-123", amount: 1000, method: "wallet" });
    expect(typeof idempotencyKey).toBe("string");
    expect(idempotencyKey.length).toBeGreaterThan(0);
  });

  it("invests via Pronova (selectable, settles as a card checkout) with method 'pronova'", async () => {
    // Pronova returns a hosted checkout (settles via card); null here keeps jsdom from
    // navigating — the point of the test is that method 'pronova' is wired through.
    createMock.mockResolvedValue({
      investment_id: "inv-2",
      property_id: "prop-123",
      status: "pending",
      units: 10,
      amount: "1000.00",
      platform_fee: "25.00",
      total_charged: "973.75",
      management_fee_rate: "1.0",
      checkout_url: null,
    });

    renderCalc();
    const pronova = screen.getByRole("button", { name: /Pronova Token/i });
    expect(pronova).not.toBeDisabled(); // now enabled (owner-launched)
    fireEvent.click(pronova);
    fireEvent.click(screen.getByRole("button", { name: /Invest \$1,000/i }));
    fireEvent.click(screen.getByRole("button", { name: /Confirm & Pay/i }));

    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    const [payload] = createMock.mock.calls[0];
    expect(payload).toEqual({ property_id: "prop-123", amount: 1000, method: "pronova" });
  });
});
