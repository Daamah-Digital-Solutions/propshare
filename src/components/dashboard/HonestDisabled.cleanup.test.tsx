/**
 * Pre-launch cleanup: assert the honest-disabled surfaces render a truthful "not
 * available yet" state with NO fabricated data and no dead/fake actions.
 *  - InvestmentCertificates: documents deferred — no mock CERT-2024-* certificates.
 *  - InvestorWallet "Payment Methods": no fake saved cards/banks on the money page;
 *    the add-method button is disabled.
 */
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { InvestmentCertificates } from "./InvestmentCertificates";
import { InvestorWallet } from "./InvestorWallet";

const walletGetMe = vi.fn();
const walletTxns = vi.fn();
const connectStatus = vi.fn();

vi.mock("@/lib/api", () => ({
  walletApi: {
    getMe: (...a: unknown[]) => walletGetMe(...a),
    transactions: (...a: unknown[]) => walletTxns(...a),
  },
  withdrawApi: { create: vi.fn() },
  connectApi: { status: (...a: unknown[]) => connectStatus(...a), onboard: vi.fn() },
  ApiError: class ApiError extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  },
}));
vi.mock("@/components/dashboard/ReinvestReturns", () => ({
  ReinvestReturns: () => <div>reinvest</div>,
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("InvestmentCertificates (honest-disabled)", () => {
  it("renders a not-available state with no fabricated certificates", () => {
    render(<InvestmentCertificates />);
    expect(screen.getByText(/not available yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/CERT-2024-001/)).toBeNull();
    expect(screen.queryByText(/Marina Heights SPV Ltd/)).toBeNull();
    // No dead View/Download buttons.
    expect(screen.queryByRole("button", { name: /download/i })).toBeNull();
  });
});

describe("InvestorWallet payment methods (no fake saved methods)", () => {
  beforeEach(() => {
    walletGetMe.mockResolvedValue({ balance: "0", pending_balance: "0", total_returns: "0" });
    walletTxns.mockResolvedValue({ items: [] });
    connectStatus.mockResolvedValue({ configured: false, payouts_enabled: false });
  });

  it("shows an empty-state and disables the add-method button; no mock cards", async () => {
    wrap(<InvestorWallet />);
    expect(await screen.findByText(/No saved payment methods/i)).toBeInTheDocument();
    expect(screen.queryByText(/Emirates NBD/)).toBeNull();
    expect(screen.queryByText(/bc1q/)).toBeNull();
    expect(
      screen.getByRole("button", { name: /add payment method/i }),
    ).toBeDisabled();
  });
});
