/**
 * Guards two things:
 *  - InvestmentCertificates: the rich documents surface renders REAL holdings (from
 *    holdingsApi.mine() -> { items }) with working View/Download + Download-All, an honest
 *    empty state, and NO fabricated CERT-2024-* ids; each holding shows the certificate the
 *    server issued (number, SPV, issue date, status, its /verify page). (holdingsApi.mine returns { items, total } —
 *    reading it as a bare array is what blanked the tab; this test pins the real shape.)
 *  - InvestorWallet "Payment Methods": no fake saved cards/banks on the money page.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { InvestmentCertificates } from "./InvestmentCertificates";
import { InvestorWallet } from "./InvestorWallet";

const walletGetMe = vi.fn();
const walletTxns = vi.fn();
const connectStatus = vi.fn();
const holdingsMine = vi.fn();
const returnsGetMine = vi.fn();
const docsList = vi.fn();
const pmList = vi.fn();
const certsMine = vi.fn();

// the certificate the server issued for the p1 holding
const CERT = {
  id: "c1",
  property_id: "p1",
  property_title: "Marina Loft",
  number: "PSC-2026-K7M2Q9XA",
  verification_code: "Xq3vN8bKp2LmR5tY7wZa1c",
  verify_path: "/verify/Xq3vN8bKp2LmR5tY7wZa1c",
  verify_url: "https://capimaxpropshare.com/verify/Xq3vN8bKp2LmR5tY7wZa1c",
  units: 8,
  ownership: "0.01905%",
  spv_name: "Marina Loft Holdings Ltd",
  location: "Dubai",
  status: "valid",
  issued_at: "2026-10-20T09:00:00Z",
};

vi.mock("@/lib/api", () => ({
  walletApi: {
    getMe: (...a: unknown[]) => walletGetMe(...a),
    transactions: (...a: unknown[]) => walletTxns(...a),
  },
  withdrawApi: { create: vi.fn() },
  cryptoApi: { open: async () => [], coins: async () => ({ items: [], total: 0 }) },
  connectApi: { status: (...a: unknown[]) => connectStatus(...a), onboard: vi.fn() },
  bankAccountsApi: { list: vi.fn().mockResolvedValue([]), add: vi.fn(), remove: vi.fn(), setDefault: vi.fn() },
  cryptoWalletsApi: { list: vi.fn().mockResolvedValue([]), add: vi.fn(), remove: vi.fn(), setDefault: vi.fn() },
  bankDepositApi: { platformAccounts: vi.fn().mockResolvedValue([]), submitClaim: vi.fn() },
  // withdrawals read their destination flow from the server (manual by default here)
  payoutConfigApi: {
    get: vi.fn().mockResolvedValue({
      auto_approve_limit: "5000",
      methods: {
        bank: { mode: "manual", connect_required: false, requested_auto: false, provider_configured: false },
        crypto: { mode: "manual", connect_required: false, requested_auto: false, provider_configured: false },
      },
    }),
  },
  holdingsApi: { mine: (...a: unknown[]) => holdingsMine(...a) },
  returnsApi: { getMine: (...a: unknown[]) => returnsGetMine(...a) },
  documentsApi: { listForProperty: (...a: unknown[]) => docsList(...a) },
  certificateApi: {
    download: vi.fn(),
    downloadAllZip: vi.fn(),
    mine: (...a: unknown[]) => certsMine(...a),
  },
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
  // the wallet reads prepared deposits / withdrawals from the URL, so it needs a router
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("InvestmentCertificates (real per-holding certificates)", () => {
  beforeEach(() => {
    returnsGetMine.mockResolvedValue({
      total_net: "0",
      total_management_fee: "0",
      count: 0,
      monthly: [],
      items: [],
    });
    docsList.mockResolvedValue([]);
    certsMine.mockResolvedValue({ items: [CERT] });
  });

  it("lists real holdings (from { items }) with a working download; no fabricated certs", async () => {
    holdingsMine.mockResolvedValue({
      items: [
        {
          property_id: "p1",
          title: "Marina Loft",
          location: "Dubai",
          units: 8,
          ownership_pct: "0.01905%",
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
    // the share as the certificate prints it (it was rounded to two decimals: "0.02%")
    expect(screen.getByText("0.01905%")).toBeInTheDocument();
    // the certificate the server issued: its number, its SPV, its issue date, its own page
    expect(await screen.findByText("PSC-2026-K7M2Q9XA")).toBeInTheDocument();
    expect(screen.getAllByText("Marina Loft Holdings Ltd").length).toBeGreaterThan(0);
    expect(screen.getByText("Oct 20, 2026")).toBeInTheDocument();
    expect(screen.getByText("Valid")).toBeInTheDocument();
    const verify = screen.getByRole("link", { name: "Verify certificate PSC-2026-K7M2Q9XA" });
    expect(verify).toHaveAttribute("href", "/verify/Xq3vN8bKp2LmR5tY7wZa1c");
    expect(screen.queryByText(/CIM Global Financial/)).toBeNull();
    expect(screen.queryByText(/Marina Loft SPV/)).toBeNull(); // no made-up SPV name
  });

  it("a certificate that no longer states the units says a new one comes on download", async () => {
    holdingsMine.mockResolvedValue({
      items: [
        { property_id: "p1", title: "Marina Loft", location: "Dubai", units: 12, ownership_pct: "1%", listed_units: 0, sellable_units: 12, unit_price: "100" },
      ],
      total: 1,
    });
    certsMine.mockResolvedValue({ items: [{ ...CERT, units: 8 }] });
    wrap(<InvestmentCertificates />);
    expect(await screen.findByText("New one on download")).toBeInTheDocument();
    expect(screen.queryByText("Valid")).toBeNull();
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

  it("empty vault: honest empty-states, add buttons ENABLED, no fake methods", async () => {
    pmList.mockResolvedValue([]);
    wrap(<InvestorWallet />);
    expect(await screen.findByText(/No saved cards/i)).toBeInTheDocument();
    expect(screen.getByText(/No saved bank account/i)).toBeInTheDocument();
    expect(screen.getByText(/No saved crypto wallet/i)).toBeInTheDocument();
    expect(screen.queryByText(/Emirates NBD/)).toBeNull();
    expect(screen.queryByText(/bc1q/)).toBeNull();
    expect(screen.getByRole("button", { name: /add card/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /add bank account/i })).toBeEnabled();
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
