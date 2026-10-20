/**
 * Withdrawals: the wallet renders the destination flow the SERVER reports, never a guess.
 *
 * - manual bank  -> pick a saved bank account (the admin pays it by hand)
 * - automatic bank -> offered once the user links a Stripe-held account; then the member
 *   chooses Automatic (ticked first) or Manual (a saved account our team pays by hand), and
 *   an approved automatic request is described as sent, not as queued for our team.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";

// vi.mock factories are hoisted, so everything they close over must be hoisted too.
const { api, toastMock, FakeApiError } = vi.hoisted(() => ({
  api: {
    payoutConfig: vi.fn(),
    connectStatus: vi.fn(),
    connectOnboard: vi.fn(),
    withdrawCreate: vi.fn(),
    withdrawList: vi.fn(),
    receipt: vi.fn(),
    transactions: vi.fn(),
  },
  toastMock: { success: vi.fn(), error: vi.fn() },
  FakeApiError: class extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  },
}));

vi.mock("@/lib/api", () => ({
  ApiError: FakeApiError,
  walletApi: {
    getMe: async () => ({ balance: "500.00", pending_balance: "0.00", currency: "USD" }),
    transactions: () => api.transactions(),
    receipt: (...a: unknown[]) => api.receipt(...a),
    depositMethods: async () => ({ card: true, crypto: true }),
  },
  cryptoApi: { open: async () => [], coins: async () => ({ items: [], total: 0 }) },
  withdrawApi: {
    create: (...a: unknown[]) => api.withdrawCreate(...a),
    list: () => api.withdrawList(),
  },
  paymentMethodsApi: { list: async () => [], remove: vi.fn(), setDefault: vi.fn() },
  bankAccountsApi: {
    list: async () => [
      { id: "b1", bank_name: "Saved Bank", iban: "AE07033123456789", is_default: true },
    ],
    create: vi.fn(),
    remove: vi.fn(),
    setDefault: vi.fn(),
  },
  cryptoWalletsApi: { list: async () => [], create: vi.fn(), remove: vi.fn(), setDefault: vi.fn() },
  bankDepositApi: { platformAccounts: async () => [], claim: vi.fn() },
  payoutConfigApi: { get: () => api.payoutConfig() },
  connectApi: { status: () => api.connectStatus(), onboard: () => api.connectOnboard() },
}));
vi.mock("sonner", () => ({ toast: toastMock }));
vi.mock("@/lib/certificates", () => ({ saveBlob: vi.fn() }));
vi.mock("@/components/exit/ExitButton", () => ({ ExitButton: () => <button>exit</button> }));

import { InvestorWallet } from "./InvestorWallet";

const mode = (bankAuto: boolean, instant = { available: false, reason: "DISABLED" }) => ({
  auto_approve_limit: "5000",
  instant: { fee_pct: "1.0", max_amount: "9999", ...instant },
  methods: {
    bank: {
      mode: bankAuto ? "auto" : "manual",
      connect_required: bankAuto,
      requested_auto: bankAuto,
      provider_configured: true,
    },
    crypto: {
      mode: "manual",
      connect_required: false,
      requested_auto: false,
      provider_configured: false,
    },
  },
});

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <InvestorWallet />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const openWithdraw = async () => {
  fireEvent.click(await screen.findByRole("button", { name: /withdraw/i }));
};

describe("InvestorWallet — withdrawal destination flow", () => {
  beforeEach(() => {
    Object.values(api).forEach((m) => m.mockReset());
    api.withdrawList.mockResolvedValue({ items: [], total: 0 });
    api.transactions.mockResolvedValue({ items: [], total: 0 });
    toastMock.success.mockReset();
    toastMock.error.mockReset();
    api.connectStatus.mockResolvedValue({
      status: "none",
      payouts_enabled: false,
      details_submitted: false,
      stripe_account_id: null,
    });
  });

  it("manual mode keeps the saved bank account picker and never offers Stripe linking", async () => {
    api.payoutConfig.mockResolvedValue(mode(false));
    mount();
    await openWithdraw();
    await waitFor(() => expect(screen.getByText(/Destination account/i)).toBeInTheDocument());
    expect(screen.queryByTestId("connect-bank")).toBeNull();
    expect(api.connectStatus).not.toHaveBeenCalled();
  });

  it("not linked yet: our team pays a saved account, and linking through Stripe is offered", async () => {
    api.payoutConfig.mockResolvedValue(mode(true));
    api.connectOnboard.mockResolvedValue({
      onboarding_url: "https://connect.stripe.com/setup/x",
      account_id: "acct_1",
      status: "pending",
    });
    api.withdrawCreate.mockResolvedValue({
      withdrawal_id: "w0",
      amount: "100.00",
      method: "bank",
      status: "pending_review",
      provider: "manual",
      reference: "WD-ABCDEFGH23",
      destination_label: "Saved Bank · ****6789",
      created_at: null,
    });
    mount();
    await openWithdraw();
    await waitFor(() => expect(screen.getByTestId("connect-bank")).toBeInTheDocument());
    expect(screen.getByText(/Destination account/i)).toBeInTheDocument();
    expect(screen.queryByTestId("bank-route")).toBeNull(); // nothing to choose between yet

    fireEvent.change(screen.getByPlaceholderText(/enter amount/i), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: /^Withdraw \$100$/i }));
    await waitFor(() => expect(api.withdrawCreate).toHaveBeenCalled());
    expect(api.withdrawCreate.mock.calls[0][0]).toEqual({
      amount: 100,
      method: "bank",
      payout_method_id: "b1",
      route: "manual",
    });
    await waitFor(() =>
      expect(toastMock.success).toHaveBeenCalledWith(
        "Withdrawal requested",
        expect.objectContaining({ description: expect.stringMatching(/WD-ABCDEFGH23/) }),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: /link bank account/i }));
    await waitFor(() => expect(api.connectOnboard).toHaveBeenCalled());
  });

  it("linked: automatic is ticked first, and Manual pays a saved account instead", async () => {
    api.payoutConfig.mockResolvedValue(mode(true));
    api.connectStatus.mockResolvedValue({
      status: "verified",
      payouts_enabled: true,
      details_submitted: true,
      stripe_account_id: "acct_1",
    });
    api.withdrawCreate.mockResolvedValue({
      withdrawal_id: "w9",
      amount: "60.00",
      method: "bank",
      status: "pending_review",
      provider: "manual",
      created_at: null,
    });
    mount();
    await openWithdraw();
    await waitFor(() => expect(screen.getByTestId("bank-route")).toBeInTheDocument());
    expect(screen.getByLabelText("Automatic")).toBeChecked();
    expect(screen.queryByText(/Destination account/i)).toBeNull();
    fireEvent.click(screen.getByLabelText(/Manual \(saved bank account\)/));
    expect(screen.getByText(/Destination account/i)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/enter amount/i), { target: { value: "60" } });
    fireEvent.click(screen.getByRole("button", { name: /^Withdraw \$60$/i }));
    await waitFor(() => expect(api.withdrawCreate).toHaveBeenCalled());
    expect(api.withdrawCreate.mock.calls[0][0]).toEqual({
      amount: 60,
      method: "bank",
      payout_method_id: "b1",
      route: "manual",
    });
  });

  it("a linked user gets an approved withdrawal described as sent, with no saved-account id", async () => {
    api.payoutConfig.mockResolvedValue(mode(true));
    api.connectStatus.mockResolvedValue({
      status: "verified",
      payouts_enabled: true,
      details_submitted: true,
      stripe_account_id: "acct_1",
    });
    api.withdrawCreate.mockResolvedValue({
      withdrawal_id: "w1",
      amount: "100.00",
      method: "bank",
      status: "approved",
      created_at: null,
    });
    mount();
    await openWithdraw();
    await waitFor(() => expect(screen.getByTestId("bank-route")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/enter amount/i), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: /^Withdraw \$100$/i }));

    await waitFor(() => expect(api.withdrawCreate).toHaveBeenCalled());
    const [payload] = api.withdrawCreate.mock.calls[0];
    expect(payload).toEqual({ amount: 100, method: "bank", route: "auto" }); // no payout_method_id
    await waitFor(() =>
      expect(toastMock.success).toHaveBeenCalledWith(
        "Withdrawal sent",
        expect.objectContaining({ description: expect.stringMatching(/on its way/i) }),
      ),
    );
  });
  it("offers instant only when the server says this account can take one", async () => {
    api.payoutConfig.mockResolvedValue(mode(true)); // available: false
    api.connectStatus.mockResolvedValue({
      status: "verified",
      payouts_enabled: true,
      details_submitted: true,
      stripe_account_id: "acct_1",
    });
    mount();
    await openWithdraw();
    await waitFor(() => expect(screen.getByTestId("bank-route")).toBeInTheDocument());
    expect(screen.queryByTestId("instant-option")).toBeNull();
  });

  it("shows the fee before confirming and sends speed=instant", async () => {
    api.payoutConfig.mockResolvedValue(mode(true, { available: true, reason: null }));
    api.connectStatus.mockResolvedValue({
      status: "verified",
      payouts_enabled: true,
      details_submitted: true,
      stripe_account_id: "acct_1",
    });
    api.withdrawCreate.mockResolvedValue({
      withdrawal_id: "w2",
      amount: "200.00",
      method: "bank",
      status: "approved",
      speed: "instant",
      fee: "2.00",
      net_amount: "198.00",
      created_at: null,
    });
    mount();
    await openWithdraw();
    await waitFor(() => expect(screen.getByTestId("instant-option")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/enter amount/i), { target: { value: "200" } });
    fireEvent.click(screen.getByLabelText(/get it in minutes/i));
    // the cost is stated before the button is pressed, not after
    await waitFor(() =>
      expect(screen.getByTestId("instant-breakdown")).toHaveTextContent(
        /Fee \$2\.00 · you receive \$198\.00/,
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: /^Withdraw \$200$/i }));
    await waitFor(() => expect(api.withdrawCreate).toHaveBeenCalled());
    expect(api.withdrawCreate.mock.calls[0][0]).toEqual({
      amount: 200,
      method: "bank",
      speed: "instant",
      route: "auto",
    });
    await waitFor(() =>
      expect(toastMock.success).toHaveBeenCalledWith(
        "Withdrawal sent",
        expect.objectContaining({ description: expect.stringMatching(/30 minutes/) }),
      ),
    );
  });

  it("blocks an instant amount over the cap instead of letting the payout fail", async () => {
    api.payoutConfig.mockResolvedValue(mode(true, { available: true, reason: null }));
    api.connectStatus.mockResolvedValue({
      status: "verified",
      payouts_enabled: true,
      details_submitted: true,
      stripe_account_id: "acct_1",
    });
    mount();
    await openWithdraw();
    await waitFor(() => expect(screen.getByTestId("instant-option")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/enter amount/i), { target: { value: "12000" } });
    fireEvent.click(screen.getByLabelText(/get it in minutes/i));
    await waitFor(() => expect(screen.getByText(/capped at \$9,999/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /^Withdraw \$12000$/i })).toBeDisabled();
  });

  it("lists each request with its number, destination and how it stands, and gives receipts", async () => {
    api.payoutConfig.mockResolvedValue(mode(false));
    api.withdrawList.mockResolvedValue({
      total: 2,
      items: [
        {
          id: "w1",
          amount: "120.00",
          method: "bank",
          provider: "manual",
          status: "completed",
          failure_reason: null,
          created_at: "2026-10-20T10:00:00Z",
          completed_at: "2026-10-20T12:00:00Z",
          reference: "WD-PAIDPAID23",
          destination_label: "CIB · ****4321",
          transfer_reference: "FT-77",
        },
        {
          id: "w2",
          amount: "80.00",
          method: "crypto",
          provider: "manual",
          status: "failed",
          failure_reason: "Wrong network",
          created_at: "2026-10-19T10:00:00Z",
          completed_at: null,
          reference: "WD-FAILFAIL23",
          destination_label: "USDT-TRC20 · ****9ab1",
        },
      ],
    });
    api.transactions.mockResolvedValue({
      total: 1,
      items: [
        {
          id: "11111111-2222-3333-4444-555555555555",
          type: "withdrawal",
          amount: "-120.00",
          status: "completed",
          description: "Withdrawal hold",
          payment_method: null,
          reference_id: "w1",
          created_at: "2026-10-20T10:00:00Z",
        },
      ],
    });
    api.receipt.mockResolvedValue(new Blob(["%PDF"]));
    mount();
    const list = await screen.findByTestId("my-withdrawals");
    await waitFor(() => expect(list).toHaveTextContent("WD-PAIDPAID23"));
    expect(list).toHaveTextContent("CIB · ****4321");
    expect(list).toHaveTextContent("Paid");
    expect(list).toHaveTextContent("Transfer reference: FT-77");
    expect(list).toHaveTextContent("Failed — returned to your wallet");
    expect(list).toHaveTextContent("Wrong network");

    fireEvent.click(await screen.findByRole("button", { name: "Download receipt" }));
    await waitFor(() =>
      expect(api.receipt).toHaveBeenCalledWith("11111111-2222-3333-4444-555555555555"),
    );
  });
});
