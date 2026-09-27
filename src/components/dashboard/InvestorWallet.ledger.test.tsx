/**
 * The transaction history shows money in as "+" and money out as "-". The ledger is signed and
 * the API sends it as is; flipping "investment / withdrawal / fee" again turned every purchase
 * and withdrawal into a "+" line (seen on the LP wallet: an exit request funded for $1,940
 * showed as +$1,940).
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  ApiError: class extends Error {},
  walletApi: {
    getMe: async () => ({ balance: "48060.00", pending_balance: "0.00", currency: "USD" }),
    transactions: async () => ({
      items: [
        { id: "t1", type: "investment", amount: "-1940.00", status: "completed", description: "LP fund", payment_method: null, reference_id: "b00cf807-x", created_at: "2026-06-23T10:00:00Z" },
        { id: "t2", type: "deposit", amount: "50000.00", status: "completed", description: "Deposit", payment_method: null, reference_id: null, created_at: "2026-06-22T10:00:00Z" },
        { id: "t3", type: "withdrawal", amount: "-250.00", status: "completed", description: "Payout", payment_method: null, reference_id: null, created_at: "2026-06-24T10:00:00Z" },
      ],
      total: 3,
    }),
    depositMethods: async () => ({ card: true, crypto: true, bank: false }),
  },
  withdrawApi: { create: vi.fn() },
  paymentMethodsApi: { list: async () => [], remove: vi.fn(), setDefault: vi.fn() },
  bankAccountsApi: { list: async () => [], create: vi.fn(), remove: vi.fn(), setDefault: vi.fn() },
  cryptoWalletsApi: { list: async () => [], create: vi.fn(), remove: vi.fn(), setDefault: vi.fn() },
  bankDepositApi: { platformAccounts: async () => [], claim: vi.fn() },
  payoutConfigApi: { get: async () => ({ auto_approve_limit: "5000", instant: { available: false }, methods: {} }) },
  connectApi: { status: async () => ({ status: "none" }), onboard: vi.fn() },
  paymentApi: { get: vi.fn() },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("@/components/exit/ExitButton", () => ({ ExitButton: () => <button>exit</button> }));

import { InvestorWallet } from "./InvestorWallet";

describe("InvestorWallet transaction history", () => {
  it("signs money out with - and money in with +", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <InvestorWallet />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/-\$\s*1,940/)).toBeInTheDocument();
    expect(screen.getByText(/-\$\s*250/)).toBeInTheDocument();
    expect(screen.getByText(/\+\$\s*50,000/)).toBeInTheDocument();
    expect(screen.queryByText(/\+\$\s*1,940/)).toBeNull();
  });
});
