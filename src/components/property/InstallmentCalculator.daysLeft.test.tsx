/**
 * Real listings carry no funding countdown, so the installment sidebar used to render a
 * bare "days left" pill (literally "undefined days left" collapsed to " days left") on
 * every under-construction property page. The pill must only appear for a real countdown.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi } from "vitest";
import InstallmentCalculator from "./InstallmentCalculator";

vi.mock("@/lib/api", () => ({
  installmentApi: { create: vi.fn(), settings: () => Promise.resolve({}) },
  investApi: { pronovaSettings: () => Promise.resolve({ discount_pct: "5.0" }) },
  ApiError: class ApiError extends Error {},
}));

const base = {
  propertyValue: 3200000,
  minInvestment: 500,
  maxInvestment: 3200000,
  expectedYield: 8,
  totalReturn: 12,
  fundingProgress: 0,
  fundedAmount: 0,
  investorsCount: 0,
  expectedCompletion: "2027-06-30",
  constructionProgress: 40,
};

function renderCalc(propertyData: Record<string, unknown>) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <InstallmentCalculator
        propertyId="p1"
        propertyTitle="Creek Rise"
        propertyData={propertyData as never}
        investmentAmount={500}
        setInvestmentAmount={() => {}}
      />
    </QueryClientProvider>,
  );
}

describe("InstallmentCalculator schedule agreement", () => {
  it("tells the truth about a missed payment: retried automatically, no late fee", () => {
    // Regression (review 2026-09-24): the text warned of late fees the platform never charges
    renderCalc(base);
    fireEvent.click(screen.getByRole("button", { name: /review full installment schedule/i }));
    const agreement = screen.getByText(/I agree that installments are due/i);
    expect(agreement).toHaveTextContent(/retried automatically; there is no late fee/i);
    expect(screen.queryByText(/late payments may incur/i)).toBeNull();
  });
});

describe("InstallmentCalculator days-left pill", () => {
  it("is hidden when the listing has no countdown", () => {
    renderCalc(base);
    expect(screen.queryByText(/days left/i)).toBeNull();
    expect(screen.getByText(/0 investors/)).toBeTruthy();
  });
  it("is shown only for a positive countdown", () => {
    renderCalc({ ...base, daysLeft: 12 });
    expect(screen.getByText("12 days left")).toBeTruthy();
  });
});
