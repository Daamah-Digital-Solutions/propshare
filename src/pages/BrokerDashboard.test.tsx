/**
 * Guards the Phase 11 broker wiring at the component level: the dashboard reads the
 * real broker API (the "Premium Realty Partners" / "Ahmed Al-Farsi" / "$125,000" mock
 * arrays are retired), the referral link comes from the API, and Virtual Cards degrade
 * to an honest disabled state (D9 — never a fake issuance).
 */
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import BrokerDashboard from "./BrokerDashboard";
import { VirtualCardRequest } from "@/components/dashboard/VirtualCardRequest";

const dashboardMock = vi.fn();
const codeMock = vi.fn();
const referralsMock = vi.fn();
const commissionsMock = vi.fn();

vi.mock("@/lib/api", () => ({
  brokerApi: {
    dashboard: (...a: unknown[]) => dashboardMock(...a),
    referralCode: (...a: unknown[]) => codeMock(...a),
    referrals: (...a: unknown[]) => referralsMock(...a),
    commissions: (...a: unknown[]) => commissionsMock(...a),
  },
}));

// The Wallet tab embeds the live InvestorWallet (its own API surface) — stub it.
vi.mock("@/components/dashboard/InvestorWallet", () => ({
  InvestorWallet: () => <div>wallet</div>,
}));

function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <BrokerDashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BrokerDashboard", () => {
  beforeEach(() => {
    dashboardMock.mockResolvedValue({
      commission_rate: "10.0",
      total_referrals: 2,
      total_commission: "42.50",
    });
    codeMock.mockResolvedValue({ code: "ABCD2345", share_link: "http://x/auth?ref=ABCD2345" });
    referralsMock.mockResolvedValue({ items: [], total: 0 });
    commissionsMock.mockResolvedValue({ items: [], total: 0 });
  });

  it("renders live broker data and retires the mock arrays", async () => {
    renderIt();
    // referral link from the API
    expect(await screen.findByText("http://x/auth?ref=ABCD2345")).toBeInTheDocument();
    // live commission rate is shown
    expect(await screen.findAllByText(/10\.0%/)).not.toHaveLength(0);
    // the old fabricated mock content is gone
    expect(screen.queryByText(/Premium Realty Partners/)).toBeNull();
    expect(screen.queryByText(/Ahmed Al-Farsi/)).toBeNull();
    expect(screen.queryByText(/\$125,000/)).toBeNull();
  });
});

describe("VirtualCardRequest (D9 honest-disabled)", () => {
  it("shows a not-yet-available state and disables the request button", () => {
    render(<VirtualCardRequest role="broker" />);
    expect(screen.getByText(/not yet available/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Request Virtual Card/i })).toBeDisabled();
    // no fake card numbers are rendered
    expect(screen.queryByText(/••••/)).toBeNull();
  });
});
