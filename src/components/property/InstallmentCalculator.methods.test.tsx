/**
 * An installment plan's down payment takes every method a ready property takes (client
 * feedback 2026-09-27, the Capimax BRX concept): the same list, in the same order. The wallet
 * starts the plan at once; card / Apple Pay / Google Pay / crypto / Pronova go through a
 * secure checkout (Pronova with its discount off the down payment); a Nova Sukuk certificate
 * goes to our team for review.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import InstallmentCalculator from "./InstallmentCalculator";
import { PAYMENT_METHODS } from "@/lib/paymentMethods";

const createPlan = vi.fn();
const createPlanWithSukuk = vi.fn();
vi.mock("@/lib/api", () => ({
  installmentsApi: {
    createPlan: (...a: unknown[]) => createPlan(...a),
    createPlanWithSukuk: (...a: unknown[]) => createPlanWithSukuk(...a),
  },
  investApi: {
    paymentOptions: () =>
      Promise.resolve({
        wallet: true,
        card: true,
        apple_pay: true,
        google_pay: true,
        crypto: true,
        pronova: true,
        sukuk: true,
        pronova_discount_pct: "5.0",
      }),
  },
  cryptoApi: {
    coins: () =>
      Promise.resolve({
        items: [
          { code: "usdtbsc", ticker: "USDT", name: "Tether USD (Binance Smart Chain)", network: "BSC", stable: true, popular: true, memo: false },
        ],
        total: 1,
      }),
  },
  ApiError: class ApiError extends Error {},
}));

const property = {
  propertyValue: 3200000,
  minInvestment: 500,
  maxInvestment: 3200000,
  expectedYield: 8,
  totalReturn: 12,
  fundingProgress: 0,
  fundedAmount: 0,
  investorsCount: 0,
  fees: { installmentFee: 4 },
};

function renderCalc() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <InstallmentCalculator
        propertyId="p1"
        propertyTitle="Creek Rise"
        propertyData={property as never}
        investmentAmount={10000}
        setInvestmentAmount={() => {}}
      />
    </QueryClientProvider>,
  );
}

async function pay(buttonName: RegExp) {
  fireEvent.click(screen.getByRole("button", { name: /Start Installment Plan/i }));
  fireEvent.click(await screen.findByRole("checkbox", { name: /reviewed and understand/i }));
  fireEvent.click(screen.getByRole("button", { name: /Proceed to Payment/i }));
  fireEvent.click(await screen.findByRole("button", { name: buttonName }));
}

const plan = {
  id: "plan-1",
  status: "pending_payment",
  checkout_url: null, // keeps jsdom from navigating
  payments: [{ seq: 0, total_amount: "2600.00" }],
};

describe("InstallmentCalculator — the down payment takes every method", () => {
  beforeEach(() => {
    createPlan.mockReset();
    createPlanWithSukuk.mockReset();
  });

  it("offers exactly the list every property offers, in the same order", () => {
    renderCalc();
    const ids = Array.from(document.querySelectorAll("[data-method]")).map((b) =>
      b.getAttribute("data-method"),
    );
    expect(ids).toEqual(PAYMENT_METHODS.map((m) => m.id));
    expect(screen.getByText(/monthly installments come from your wallet/i)).toBeInTheDocument();
  });

  it("pays the down payment by card through the secure checkout", async () => {
    createPlan.mockResolvedValue(plan);
    renderCalc();
    fireEvent.click(await screen.findByRole("button", { name: /Credit \/ Debit Card/i }));
    await pay(/Continue to pay/i);
    await waitFor(() => expect(createPlan).toHaveBeenCalledTimes(1));
    expect(createPlan.mock.calls[0][0]).toEqual({
      property_id: "p1",
      amount: 10000,
      duration_months: 12,
      method: "card",
    });
  });

  it("pays a crypto down payment in the coin chosen here", async () => {
    createPlan.mockResolvedValue(plan);
    renderCalc();
    fireEvent.click(await screen.findByRole("button", { name: /Cryptocurrency/i }));
    fireEvent.click(await screen.findByRole("option", { name: /USDT · Tether USD/ }));
    expect(await screen.findByTestId("crypto-pay-notice")).toHaveTextContent(
      "If less than the down payment arrives, the plan does not start and what arrived goes to your wallet",
    );
    expect(screen.getByTestId("crypto-pay-notice")).toHaveTextContent(
      "Send USDT on the BNB Smart Chain (BSC) network only",
    );
    fireEvent.click(screen.getByRole("button", { name: /Start Installment Plan/i }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /reviewed and understand/i }));
    fireEvent.click(screen.getByRole("button", { name: /Proceed to Payment/i }));
    // the confirm step names the coin as the list does, network included
    expect(
      await screen.findByText(/You pay in USDT · Tether USD \(Binance Smart Chain\)\./),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Continue to pay/i }));
    await waitFor(() => expect(createPlan).toHaveBeenCalledTimes(1));
    expect(createPlan.mock.calls[0][0]).toEqual({
      property_id: "p1",
      amount: 10000,
      duration_months: 12,
      method: "crypto",
      pay_currency: "usdtbsc",
    });
  });

  it("takes the Pronova discount off the down payment", async () => {
    createPlan.mockResolvedValue(plan);
    renderCalc();
    fireEvent.click(await screen.findByRole("button", { name: /Pronova Token/i }));
    // 12 months: 25% down = $2,500 + 4% fee = $2,600; 5% off = $130
    expect(await screen.findByText(/Pronova discount \(-5% of the down payment\)/)).toBeInTheDocument();
    expect(screen.getAllByText("-$130.00").length).toBeGreaterThan(0);
    await pay(/Continue to pay \$2470\.00/i);
    await waitFor(() => expect(createPlan).toHaveBeenCalledTimes(1));
    expect(createPlan.mock.calls[0][0].method).toBe("pronova");
  });

  it("builds the plan on the whole units the amount covers, at the price shown", async () => {
    createPlan.mockResolvedValue(plan);
    render(
      <QueryClientProvider client={new QueryClient()}>
        <InstallmentCalculator
          propertyId="p1"
          propertyTitle="Creek Rise"
          propertyData={{ ...property, unitPrice: 110 } as never}
          investmentAmount={1000}
          setInvestmentAmount={() => {}}
        />
      </QueryClientProvider>,
    );
    // $1,000 at $110 a unit covers 9 units = $990: 25% down is $247.50 + 4% fee = $257.40
    expect(screen.getByTestId("plan-units-hint")).toHaveTextContent(
      "Units cost $110 each. This amount covers 9 whole units ($990.00): the plan is for those.",
    );
    expect(screen.getAllByText("$257.40").length).toBeGreaterThan(0);
    fireEvent.click(await screen.findByRole("button", { name: /Credit \/ Debit Card/i }));
    await pay(/Continue to pay/i);
    await waitFor(() => expect(createPlan).toHaveBeenCalledTimes(1));
    expect(createPlan.mock.calls[0][0]).toEqual({
      property_id: "p1",
      amount: 990,
      duration_months: 12,
      method: "card",
      expected_unit_price: 110,
    });
  });

  it("sends a Nova Sukuk certificate for the down payment to review", async () => {
    createPlanWithSukuk.mockResolvedValue({ certificate_id: "c-1", amount_due: "2600.00" });
    renderCalc();
    fireEvent.click(await screen.findByRole("button", { name: /Nova Sukuk/i }));
    const pdf = new File(["%PDF-1.4"], "nova.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/Certificate \(PDF\)/i), { target: { files: [pdf] } });
    fireEvent.click(screen.getByRole("checkbox", { name: /stay pledged to Nova Finance/i }));
    await pay(/Submit certificate/i);
    await waitFor(() => expect(createPlanWithSukuk).toHaveBeenCalledTimes(1));
    const [payload, cert] = createPlanWithSukuk.mock.calls[0];
    expect(payload).toEqual({ property_id: "p1", amount: 10000, duration_months: 12 });
    expect(cert.file).toBe(pdf);
    expect(createPlan).not.toHaveBeenCalled();
  });
});
