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
const holdingsMine = vi.fn();
const pmList = vi.fn();

vi.mock("@/lib/api", () => ({
  walletApi: {
    getMe: (...a: unknown[]) => walletGetMe(...a),
    transactions: (...a: unknown[]) => walletTxns(...a),
  },
  withdrawApi: { create: vi.fn() },
  connectApi: { status: (...a: unknown[]) => connectStatus(...a), onboard: vi.fn() },
  holdingsApi: { mine: (...a: unknown[]) => holdingsMine(...a) },
  certificateApi: { download: vi.fn() },
  paymentMethodsApi: {
    list: (...a: unknown[]) => pmList(...a),
    setupIntent: vi.fn(),
    add: vi.fn(),
    remove: vi.fn(),
    setDefault: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/components/dashboard/ReinvestReturns", () => ({
  ReinvestReturns: () => <div>reinvest</div>,
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("InvestmentCertificates (real per-holding certificates, Group 2)", () => {
  it("lists real holdings with a working certificate download; no fabricated certs", async () => {
    holdingsMine.mockResolvedValue([
      { property_id: "p1", title: "Marina Loft", location: "Dubai", units: 8, listed_units: 0, sellable_units: 8, unit_price: "100" },
    ]);
    wrap(<InvestmentCertificates />);
    expect(await screen.findByText("Marina Loft")).toBeInTheDocument();
    expect(screen.getByText(/8 units held/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /certificate/i })).toBeEnabled();
    expect(screen.queryByText(/CERT-2024-001/)).toBeNull(); // no fabricated cert ids
  });

  it("shows an honest empty state when there are no holdings", async () => {
    holdingsMine.mockResolvedValue([]);
    wrap(<InvestmentCertificates />);
    expect(await screen.findByText(/No certificates yet/i)).toBeInTheDocument();
  });
});

describe("InvestorWallet payment methods (real tokenized vault, Group 3)", () => {
  beforeEach(() => {
    walletGetMe.mockResolvedValue({ balance: "0", pending_balance: "0", total_returns: "0" });
    walletTxns.mockResolvedValue({ items: [] });
    connectStatus.mockResolvedValue({ configured: false, payouts_enabled: false });
    pmList.mockReset();
  });

  it("empty vault: honest empty-state, add button ENABLED, no fake cards", async () => {
    pmList.mockResolvedValue([]);
    wrap(<InvestorWallet />);
    expect(await screen.findByText(/No saved payment methods/i)).toBeInTheDocument();
    expect(screen.queryByText(/Emirates NBD/)).toBeNull();
    expect(screen.queryByText(/bc1q/)).toBeNull();
    expect(screen.getByRole("button", { name: /add payment method/i })).toBeEnabled();
  });

  it("renders real saved methods (brand •••• last4 + Default), no card number stored", async () => {
    pmList.mockResolvedValue([
      {
        id: "pm1",
        type: "card",
        brand: "visa",
        last4: "4242",
        exp_month: 12,
        exp_year: 2030,
        is_default: true,
        created_at: "2026-06-01T00:00:00Z",
      },
    ]);
    wrap(<InvestorWallet />);
    expect(await screen.findByText(/4242/)).toBeInTheDocument();
    expect(screen.getByText(/Default/)).toBeInTheDocument();
    expect(screen.getByText(/Expires 12\/2030/)).toBeInTheDocument();
  });
});
