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
import { ApiError } from "@/lib/api";
import { ReinvestProvider } from "@/contexts/ReinvestContext";

// Mock the API client — keep ApiError a real class so `instanceof` checks work.
const createMock = vi.fn();
const sukukMock = vi.fn();
const LIVE = {
  wallet: true,
  card: true,
  apple_pay: true,
  google_pay: true,
  crypto: true,
  pronova: true,
  sukuk: true,
  pronova_discount_pct: "5.0",
};
let options: Record<string, unknown> = LIVE;
// each coin's smallest payment as it was on 2026-10-06 (it moves with the network's fees)
const MINIMUMS: Record<string, string> = { usdttrc20: "12.00", btc: "1.12" };
vi.mock("@/lib/api", () => ({
  investApi: {
    create: (...args: unknown[]) => createMock(...args),
    buyWithSukuk: (...args: unknown[]) => sukukMock(...args),
    paymentOptions: () => Promise.resolve(options),
    pronovaSettings: () => Promise.resolve({ discount_pct: "5.0" }),
    reinvestSettings: () => Promise.resolve({ discount_pct: "5.0" }),
  },
  cryptoApi: {
    coins: () =>
      Promise.resolve({
        items: [
          { code: "usdttrc20", ticker: "USDT", name: "Tether USD (Tron)", network: "TRX", stable: true, popular: true, memo: false },
          { code: "btc", ticker: "BTC", name: "Bitcoin", network: "BTC", stable: false, popular: true, memo: false },
        ],
        total: 2,
      }),
    minimum: (code: string) =>
      Promise.resolve({ coin: code, minimum: MINIMUMS[code] ?? null, currency: "usd" }),
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

function renderCalc(openReview = false) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ReinvestProvider>
        <InvestmentCalculator
          propertyId="prop-123"
          propertyData={propertyData}
          investmentAmount={1000}
          setInvestmentAmount={() => {}}
          openReview={openReview}
        />
      </ReinvestProvider>
    </QueryClientProvider>,
  );
}

describe("InvestmentCalculator unit price", () => {
  it("shows the unit price and how many whole units the amount buys", () => {
    // Regression (review 2026-09-24): the property page never showed the unit price, so an
    // investor typed an amount without knowing what one unit costs
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ReinvestProvider>
          <InvestmentCalculator
            propertyId="prop-123"
            propertyData={{ ...propertyData, unitPrice: 300 }}
            investmentAmount={1000}
            setInvestmentAmount={() => {}}
          />
        </ReinvestProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("unit-price-hint")).toHaveTextContent(
      "Units cost $300 each. This amount buys 3 whole units",
    );
  });
});

describe("InvestmentCalculator on an under-construction listing paid in full", () => {
  const mount = (offplan: boolean) =>
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ReinvestProvider>
          <InvestmentCalculator
            propertyId="prop-123"
            propertyData={propertyData}
            investmentAmount={1000}
            setInvestmentAmount={() => {}}
            offplan={offplan}
          />
        </ReinvestProvider>
      </QueryClientProvider>,
    );

  it("promises no rent before handover: the return is the unit price", () => {
    mount(true);
    expect(screen.getByTestId("offplan-returns")).toHaveTextContent(/pays no rent before handover/i);
    expect(screen.getByTestId("offplan-returns")).toHaveTextContent(/the change in the unit price/i);
    expect(screen.queryByText("Gross Annual Rental")).toBeNull();
    expect(screen.queryByText("Net Annual Income")).toBeNull();
    expect(screen.getByText(/rental distributions, which start after handover/i)).toBeInTheDocument();
  });

  it("keeps the rental figures on a ready property", () => {
    mount(false);
    expect(screen.queryByTestId("offplan-returns")).toBeNull();
    expect(screen.getByText("Gross Annual Rental")).toBeInTheDocument();
  });
});

describe("InvestmentCalculator: what is shown is what is charged", () => {
  const mount = () =>
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ReinvestProvider>
          <InvestmentCalculator
            propertyId="prop-123"
            propertyData={{ ...propertyData, unitPrice: 110 }}
            investmentAmount={1000}
            setInvestmentAmount={() => {}}
          />
        </ReinvestProvider>
      </QueryClientProvider>,
    );
  // a block body: `() => spy.mockReset()` returns the spy, which vitest would then call as
  // a cleanup function after each test
  beforeEach(() => {
    createMock.mockReset();
  });

  it("prices the whole units the amount buys, not the amount typed", async () => {
    // $1,000 at $110 a unit is 9 units = $990; the 2.5% fee is on that: $24.75
    createMock.mockResolvedValue({ units: 9, total_charged: "1014.75", checkout_url: null });
    mount();
    expect(screen.getByText(/Investment Amount \(9 units\)/)).toBeInTheDocument();
    expect(screen.getByText("+$24.75")).toBeInTheDocument();
    expect(screen.getByText("$1014.75")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Invest \$990/i }));
    expect(screen.getByText(/You are about to invest \$\s*990 in this property/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Confirm & Pay/i }));
    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    // the amount of those units, and the price they were shown at
    expect(createMock.mock.calls[0][0]).toEqual({
      property_id: "prop-123",
      amount: 990,
      method: "wallet",
      expected_unit_price: 110,
    });
  });

  it("asks again when the unit price changed while the page was open", async () => {
    // what the API client raises for 409 PRICE_CHANGED (this file's ApiError takes the code
    // and the message)
    const Raised = ApiError as unknown as new (code: string, message: string) => Error;
    createMock.mockImplementation(async () => {
      throw new Raised("PRICE_CHANGED", "The unit price of this property is now $121.");
    });
    mount();
    fireEvent.click(screen.getByRole("button", { name: /Invest \$990/i }));
    fireEvent.click(screen.getByRole("button", { name: /Confirm & Pay/i }));
    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    // the confirmation closes: the page reloads the listing and shows the new amounts
    await waitFor(() => expect(screen.queryByRole("button", { name: /Confirm & Pay/i })).toBeNull());
  });

  it("cannot be confirmed for less than one unit", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ReinvestProvider>
          <InvestmentCalculator
            propertyId="prop-123"
            propertyData={{ ...propertyData, unitPrice: 110 }}
            investmentAmount={100}
            setInvestmentAmount={() => {}}
          />
        </ReinvestProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("button", { name: /Invest \$0/i })).toBeDisabled();
  });
});

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
    fireEvent.click(screen.getByRole("button", { name: /Continue to secure payment/i }));

    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    const [payload] = createMock.mock.calls[0];
    expect(payload).toEqual({ property_id: "prop-123", amount: 1000, method: "pronova" });
  });
});

const checkout = (method: string) => ({
  investment_id: "inv-3",
  property_id: "prop-123",
  status: "pending",
  units: 10,
  amount: "1000.00",
  platform_fee: "25.00",
  total_charged: "1025.00",
  management_fee_rate: "1.0",
  // null keeps jsdom from navigating; the point is which method reaches the server
  checkout_url: null,
  method,
});

describe("InvestmentCalculator — every payment method (the same list on every property)", () => {
  beforeEach(() => {
    createMock.mockReset();
    sukukMock.mockReset();
    options = LIVE;
  });

  it("lists wallet, card, Apple Pay, Google Pay, crypto, Pronova and Nova Sukuk in that order", () => {
    renderCalc();
    const ids = Array.from(document.querySelectorAll("[data-method]")).map((b) =>
      b.getAttribute("data-method"),
    );
    expect(ids).toEqual(["wallet", "card", "apple_pay", "google_pay", "crypto", "pronova", "sukuk"]);
  });

  it("pays in crypto in the coin chosen here, through the crypto checkout", async () => {
    createMock.mockResolvedValue(checkout("crypto"));
    renderCalc();
    fireEvent.click(await screen.findByRole("button", { name: /Cryptocurrency/i }));
    // no coin yet: the review step does not open
    fireEvent.click(screen.getByRole("button", { name: /Invest \$1,000/i }));
    expect(screen.queryByRole("button", { name: /Continue to secure payment/i })).toBeNull();
    fireEvent.click(await screen.findByRole("option", { name: /USDT · Tether USD \(Tron\)/ }));
    expect(await screen.findByTestId("crypto-pay-notice")).toHaveTextContent(
      "Send USDT on the Tron network only",
    );
    expect(screen.getByTestId("crypto-pay-notice")).toHaveTextContent(
      "Send the full amount: if what arrives is clearly less, the purchase is not completed and it goes to your wallet instead",
    );
    // the coin's smallest payment is said under it, before anything is pressed
    expect(await screen.findByTestId("crypto-minimum")).toHaveTextContent(
      "Smallest payment in this coin right now: about $12.00.",
    );
    fireEvent.click(screen.getByRole("button", { name: /Invest \$1,000/i }));
    expect(screen.getByText(/You pay in USDT · Tether USD \(Tron\)\./)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Continue to secure payment/i }));
    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    expect(createMock.mock.calls[0][0]).toEqual({
      property_id: "prop-123",
      amount: 1000,
      method: "crypto",
      pay_currency: "usdttrc20",
    });
  });

  it("does not open the review for a payment under the chosen coin's smallest payment", async () => {
    // 2026-10-06: USDT on Tron took no less than 12 USD while a member was trying 3 and 4.
    // Left unsaid, that is learnt from a refusal after pressing pay: it is said under the coin.
    createMock.mockResolvedValue(checkout("crypto"));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ReinvestProvider>
          <InvestmentCalculator
            propertyId="prop-123"
            propertyData={{ ...propertyData, minInvestment: 5, unitPrice: 5 }}
            investmentAmount={10}
            setInvestmentAmount={() => {}}
          />
        </ReinvestProvider>
      </QueryClientProvider>,
    );
    // 2 units = $10 + the 2.5% fee = $10.25
    fireEvent.click(await screen.findByRole("button", { name: /Cryptocurrency/i }));
    fireEvent.click(await screen.findByRole("option", { name: /USDT · Tether USD \(Tron\)/ }));
    const tooSmall = await screen.findByTestId("crypto-minimum");
    expect(tooSmall).toHaveAttribute("role", "alert");
    expect(tooSmall).toHaveTextContent(
      "USDT · Tether USD (Tron) takes no less than about $12.00 right now, and this payment is $10.25. Choose another coin or a larger amount.",
    );
    fireEvent.click(screen.getByRole("button", { name: /Invest \$10/i }));
    expect(screen.queryByRole("button", { name: /Continue to secure payment/i })).toBeNull();
    // a coin that takes this amount goes through
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    fireEvent.click(await screen.findByRole("option", { name: /BTC · Bitcoin/ }));
    const least = await screen.findByTestId("crypto-minimum");
    expect(least).not.toHaveAttribute("role");
    expect(least).toHaveTextContent("Smallest payment in this coin right now: about $1.12.");
    fireEvent.click(screen.getByRole("button", { name: /Invest \$10/i }));
    fireEvent.click(screen.getByRole("button", { name: /Continue to secure payment/i }));
    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    expect(createMock.mock.calls[0][0]).toMatchObject({ method: "crypto", pay_currency: "btc" });
  });

  it("sends Google Pay as a card payment (it shows on Stripe's checkout)", async () => {
    createMock.mockResolvedValue(checkout("card"));
    renderCalc();
    fireEvent.click(await screen.findByRole("button", { name: /Google Pay/i }));
    fireEvent.click(screen.getByRole("button", { name: /Invest \$1,000/i }));
    fireEvent.click(screen.getByRole("button", { name: /Continue to secure payment/i }));
    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    expect(createMock.mock.calls[0][0].method).toBe("card");
  });

  it("shows a rail without its provider as unavailable instead of hiding it", async () => {
    options = { ...LIVE, crypto: false };
    renderCalc();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Cryptocurrency/i })).toBeDisabled(),
    );
    expect(screen.getByRole("button", { name: /Cryptocurrency/i })).toHaveTextContent(
      /Not available right now/,
    );
  });

  it("submits a Nova Sukuk certificate only with the PDF and the pledge accepted", async () => {
    sukukMock.mockResolvedValue({ certificate_id: "c-1", units: 10, amount_due: "1025.00" });
    renderCalc();
    fireEvent.click(await screen.findByRole("button", { name: /Nova Sukuk/i }));
    expect(screen.getByTestId("sukuk-fields")).toBeInTheDocument();
    expect(screen.getByTestId("nova-pledge-notice")).toHaveTextContent(/pledged to Nova Finance/);

    // nothing attached yet: the review step does not open
    fireEvent.click(screen.getByRole("button", { name: /Invest \$1,000/i }));
    expect(screen.queryByRole("button", { name: /Submit certificate/i })).toBeNull();

    const pdf = new File(["%PDF-1.4"], "nova.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/Certificate \(PDF\)/i), { target: { files: [pdf] } });
    fireEvent.change(screen.getByLabelText(/Certificate no\./i), { target: { value: "NOVA-9" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /stay pledged to Nova Finance/i }));
    fireEvent.click(screen.getByRole("button", { name: /Invest \$1,000/i }));
    fireEvent.click(screen.getByRole("button", { name: /Submit certificate/i }));

    await waitFor(() => expect(sukukMock).toHaveBeenCalledTimes(1));
    const [input, cert, key] = sukukMock.mock.calls[0];
    expect(input).toEqual({ property_id: "prop-123", amount: 1000 });
    expect(cert.file).toBe(pdf);
    expect(cert.certificate_no).toBe("NOVA-9");
    expect(typeof key).toBe("string");
    expect(createMock).not.toHaveBeenCalled();
  });
});

describe("InvestmentCalculator — an order prepared by the assistant", () => {
  beforeEach(() => createMock.mockReset());

  it("opens the review step (the last one before payment) but never pays by itself", async () => {
    renderCalc(true);
    expect(await screen.findByText("Confirm Investment")).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("stays closed without an order", () => {
    renderCalc(false);
    expect(screen.queryByText("Confirm Investment")).toBeNull();
  });
});
