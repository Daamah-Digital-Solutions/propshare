/**
 * Guards two things:
 *  - InvestmentCertificates: the rich documents surface renders REAL holdings (from
 *    holdingsApi.mine() -> { items }) with working View/Download + Download-All, an honest
 *    empty state, and NO fabricated CERT-2024-* ids. (holdingsApi.mine returns { items, total } —
 *    reading it as a bare array is what blanked the tab; this test pins the real shape.)
 *  - InvestorWallet "Payment Methods": no fake saved cards/banks on the money page.
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
const propsList = vi.fn();
const returnsGetMine = vi.fn();
const docsList = vi.fn();
const pmList = vi.fn();

vi.mock("@/lib/api", () => ({
  walletApi: {
    getMe: (...a: unknown[]) => walletGetMe(...a),
    transactions: (...a: unknown[]) => walletTxns(...a),
  },
  withdrawApi: { create: vi.fn() },
  connectApi: { status: (...a: unknown[]) => connectStatus(...a), onboard: vi.fn() },
  holdingsApi: { mine: (...a: unknown[]) => holdingsMine(...a) },
  propertyApi: { list: (...a: unknown[]) => propsList(...a) },
  returnsApi: { getMine: (...a: unknown[]) => returnsGetMine(...a) },
  documentsApi: { listForProperty: (...a: unknown[]) => docsList(...a) },
  certificateApi: { download: vi.fn(), downloadAllZip: vi.fn() },
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
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { id: "user-0001" } }) }));
vi.mock("@/components/dashboard/ReinvestReturns", () => ({
  ReinvestReturns: () => <div>reinvest</div>,
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("InvestmentCertificates (real per-holding certificates)", () => {
  beforeEach(() => {
    propsList.mockResolvedValue({ items: [{ id: "p1", total_units: 100 }], total: 1 });
    returnsGetMine.mockResolvedValue({
      total_net: "0",
      total_management_fee: "0",
      count: 0,
      monthly: [],
      items: [],
    });
    docsList.mockResolvedValue([]);
  });

  it("lists real holdings (from { items }) with a working download; no fabricated certs", async () => {
    holdingsMine.mockResolvedValue({
      items: [
        {
          property_id: "p1",
          title: "Marina Loft",
          location: "Dubai",
          units: 8,
          listed_units: 0,
          sellable_units: 8,
          unit_price: "100",
        },
      ],
      total: 1,
    });
    wrap(<InvestmentCertificates />);
    expect(await screen.findByText("Marina Loft")).toBeInTheDocument();
    expect(screen.getByText(/8 units/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download all/i })).toBeEnabled();
    expect(screen.queryByText(/CERT-2024-001/)).toBeNull(); // no fabricated cert ids
  });

  it("shows an honest empty state when there are no holdings", async () => {
    holdingsMine.mockResolvedValue({ items: [], total: 0 });
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
