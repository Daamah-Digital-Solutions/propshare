/**
 * Withdrawals: the wallet renders the destination flow the SERVER reports, never a guess.
 *
 * - manual bank  -> pick a saved bank account (the admin pays it by hand)
 * - automatic bank -> no saved account at all; the user links a Stripe-held account once,
 *   and an approved request is described as sent, not as queued for our team.
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
    transactions: async () => ({ items: [], total: 0 }),
    depositMethods: async () => ({ card: true, crypto: true }),
  },
  withdrawApi: { create: (...a: unknown[]) => api.withdrawCreate(...a) },
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
vi.mock("@/components/exit/ExitButton", () => ({ ExitButton: () => <button>exit</button> }));

import { InvestorWallet } from "./InvestorWallet";

const mode = (bankAuto: boolean) => ({
  auto_approve_limit: "5000",
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

  it("automatic mode asks the user to link a bank once, instead of a saved account", async () => {
    api.payoutConfig.mockResolvedValue(mode(true));
    api.connectOnboard.mockResolvedValue({
      onboarding_url: "https://connect.stripe.com/setup/x",
      account_id: "acct_1",
      status: "pending",
    });
    mount();
    await openWithdraw();
    await waitFor(() => expect(screen.getByTestId("connect-bank")).toBeInTheDocument());
    expect(screen.queryByText(/Destination account/i)).toBeNull();

    // withdrawing before linking is blocked client-side (the server would 409 anyway)
    fireEvent.change(screen.getByPlaceholderText(/enter amount/i), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: /^Withdraw \$100$/i }));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled());
    expect(api.withdrawCreate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /link bank account/i }));
    await waitFor(() => expect(api.connectOnboard).toHaveBeenCalled());
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
    await waitFor(() => expect(screen.getByTestId("connect-bank")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/enter amount/i), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: /^Withdraw \$100$/i }));

    await waitFor(() => expect(api.withdrawCreate).toHaveBeenCalled());
    const [payload] = api.withdrawCreate.mock.calls[0];
    expect(payload).toEqual({ amount: 100, method: "bank" }); // no payout_method_id
    await waitFor(() =>
      expect(toastMock.success).toHaveBeenCalledWith(
        "Withdrawal sent",
        expect.objectContaining({ description: expect.stringMatching(/on its way/i) }),
      ),
    );
  });
});
