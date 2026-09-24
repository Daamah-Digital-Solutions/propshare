/**
 * A deposit or withdrawal prepared by the assistant arrives as a link
 * (?tab=wallet&action=deposit|withdraw&amount=N&method=M&speed=S). The wallet opens the form
 * filled in and stops there: depositing / withdrawing stays the user's own click. The link is
 * consumed, so a refresh or Back does not reopen it.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";

// vi.mock factories are hoisted, so everything they close over must be hoisted too.
const { api, state } = vi.hoisted(() => {
  const mode = (bankAuto: boolean, instant: boolean) => ({
    auto_approve_limit: "5000",
    instant: { fee_pct: "1.0", max_amount: "9999", available: instant, reason: instant ? null : "DISABLED" },
    methods: {
      bank: { mode: bankAuto ? "auto" : "manual", connect_required: bankAuto, requested_auto: bankAuto, provider_configured: true },
      crypto: { mode: "manual", connect_required: false, requested_auto: false, provider_configured: false },
    },
  });
  return {
    api: { deposit: vi.fn(), withdrawCreate: vi.fn() },
    state: {
      mode,
      config: mode(false, false),
      banks: [] as { id: string; bank_name: string; iban: string; is_default: boolean }[],
    },
  };
});

vi.mock("@/lib/api", () => ({
  ApiError: class extends Error {
    code = "";
  },
  walletApi: {
    getMe: async () => ({ balance: "8000.00", pending_balance: "0.00", currency: "USD" }),
    transactions: async () => ({ items: [], total: 0 }),
    depositMethods: async () => ({ card: true, crypto: true, bank: false }),
    deposit: (...a: unknown[]) => api.deposit(...a),
  },
  withdrawApi: { create: (...a: unknown[]) => api.withdrawCreate(...a) },
  paymentMethodsApi: { list: async () => [], remove: vi.fn(), setDefault: vi.fn() },
  bankAccountsApi: { list: async () => state.banks, create: vi.fn(), remove: vi.fn(), setDefault: vi.fn() },
  cryptoWalletsApi: { list: async () => [], create: vi.fn(), remove: vi.fn(), setDefault: vi.fn() },
  bankDepositApi: { platformAccounts: async () => [], claim: vi.fn() },
  payoutConfigApi: { get: async () => state.config },
  connectApi: {
    status: async () => ({ status: "verified", payouts_enabled: true, details_submitted: true, stripe_account_id: "acct_1" }),
    onboard: vi.fn(),
  },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("@/components/exit/ExitButton", () => ({ ExitButton: () => <button>exit</button> }));

import { InvestorWallet } from "./InvestorWallet";

function Url() {
  const l = useLocation();
  return <div data-testid="url">{l.pathname + l.search}</div>;
}

function mount(url: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <InvestorWallet />
        <Url />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("InvestorWallet — prepared by the assistant", () => {
  beforeEach(() => {
    api.deposit.mockReset();
    api.withdrawCreate.mockReset();
    state.config = state.mode(false, false);
    state.banks = [];
  });

  it("opens the deposit filled in and stops before the user's own click", async () => {
    mount("/dashboard?tab=wallet&action=deposit&amount=5000.00&method=crypto");
    expect(await screen.findByTestId("assistant-prefill-banner")).toHaveTextContent(/nothing is charged/i);
    expect(screen.getByDisplayValue("5000")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deposit $5000" })).toBeEnabled();
    expect(api.deposit).not.toHaveBeenCalled();
    // consumed: a refresh or the Back button does not reopen it
    await waitFor(() => expect(screen.getByTestId("url").textContent).toBe("/dashboard?tab=wallet"));
  });

  it("opens the withdrawal filled in, paying the first saved account when none is default", async () => {
    state.banks = [{ id: "b1", bank_name: "Saved Bank", iban: "AE070331234567890123456", is_default: false }];
    api.withdrawCreate.mockResolvedValue({ withdrawal_id: "w1", amount: "250.00", method: "bank", status: "pending_review", created_at: null });
    mount("/dashboard?tab=wallet&action=withdraw&amount=250.00&method=bank");
    expect(await screen.findByTestId("assistant-prefill-banner")).toHaveTextContent(/nothing is sent/i);
    expect(screen.getByDisplayValue("250")).toBeInTheDocument();
    await screen.findByText(/Destination account/i);
    expect(api.withdrawCreate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Withdraw $250" }));
    await waitFor(() => expect(api.withdrawCreate).toHaveBeenCalled());
    expect(api.withdrawCreate.mock.calls[0][0]).toEqual({ amount: 250, method: "bank", payout_method_id: "b1" });
  });

  it("keeps the instant speed and shows the fee before anything is sent", async () => {
    state.config = state.mode(true, true);
    mount("/dashboard?tab=wallet&action=withdraw&amount=200.00&method=bank&speed=instant");
    await waitFor(() =>
      expect(screen.getByTestId("instant-breakdown")).toHaveTextContent(/Fee \$2\.00 · you receive \$198\.00/),
    );
    expect(screen.getByLabelText(/get it in minutes/i)).toBeChecked();
    expect(api.withdrawCreate).not.toHaveBeenCalled();
  });

  it("ignores anything that is not a prepared deposit or withdrawal", async () => {
    mount("/dashboard?tab=wallet&action=transfer&amount=100");
    await screen.findByRole("button", { name: /add funds/i });
    expect(screen.queryByTestId("assistant-prefill-banner")).toBeNull();
    expect(screen.getByTestId("url").textContent).toBe("/dashboard?tab=wallet&action=transfer&amount=100");
  });
});
