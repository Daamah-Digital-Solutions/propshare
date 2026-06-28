/**
 * Phase 15: the Owner overview cards read the server-authoritative aggregation
 * (ownerStatsApi.portfolioStats) — Total Portfolio Value, Total Investors and current
 * Monthly Revenue are REAL; occupancy is an honest empty state ("No occupancy data
 * yet", never 94%); per-property revenue is real. No fabricated literals remain.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import OwnerDashboard from "./OwnerDashboard";

const listOwnerMock = vi.fn();
const portfolioStatsMock = vi.fn();

vi.mock("@/lib/api", () => ({
  propertyApi: { listOwner: (...a: unknown[]) => listOwnerMock(...a) },
  ownerStatsApi: { portfolioStats: (...a: unknown[]) => portfolioStatsMock(...a) },
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { full_name: "Test Owner", email: "owner@x.com" } }),
}));
vi.mock("@/components/dashboard/InvestorWallet", () => ({
  InvestorWallet: () => <div>wallet</div>,
}));
vi.mock("@/components/dashboard/VirtualCardRequest", () => ({
  VirtualCardRequest: () => <div>cards</div>,
}));
vi.mock("@/components/developer/PropertyCreationForm", () => ({
  PropertyCreationForm: () => <div>form</div>,
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const PROPS = [
  {
    id: "p1",
    title: "Tower A",
    location: "Dubai",
    image: "",
    images: [],
    status: "active",
    model: "ready-income",
    total_value: 5_000_000,
    funded_amount: 1_000_000,
    funding_progress: 50,
    investors_count: 10,
  },
];

const STATS = {
  total_portfolio_value: "5000000.00",
  total_investors: 150,
  occupancy: null,
  monthly_revenue_current: "12000.00",
  monthly_revenue_series: [
    { month: "2026-01", amount: "0.00" },
    { month: "2026-02", amount: "8000.00" },
    { month: "2026-03", amount: "0.00" },
    { month: "2026-04", amount: "0.00" },
    { month: "2026-05", amount: "0.00" },
    { month: "2026-06", amount: "12000.00" },
  ],
  per_property: [{ property_id: "p1", revenue_generated: "20000.00", occupancy: null }],
};

describe("OwnerDashboard real stats (Phase 15)", () => {
  beforeEach(() => {
    listOwnerMock.mockReset();
    portfolioStatsMock.mockReset();
    listOwnerMock.mockResolvedValue(PROPS);
    portfolioStatsMock.mockResolvedValue(STATS);
  });

  it("renders the real portfolio value, investors and current monthly revenue", async () => {
    wrap(<OwnerDashboard />);
    expect(await screen.findByText("$5.0M")).toBeInTheDocument(); // Σ total_value
    expect(screen.getByText("150")).toBeInTheDocument(); // distinct net-holders
    expect(screen.getByText("$12,000")).toBeInTheDocument(); // current-month revenue
    expect(screen.getByText("Test Owner")).toBeInTheDocument(); // real greeting
  });

  it("shows the honest occupancy empty state and real per-property revenue", async () => {
    wrap(<OwnerDashboard />);
    await screen.findByText("$5.0M");
    expect(screen.getAllByText(/No occupancy data yet/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("$20,000")).toBeInTheDocument(); // per-property revenue (overview card)
  });

  it("retires every fabricated literal", async () => {
    wrap(<OwnerDashboard />);
    await screen.findByText("$5.0M");
    expect(screen.queryByText("$12.5M")).toBeNull();
    expect(screen.queryByText("$85,000")).toBeNull();
    expect(screen.queryByText("1,234")).toBeNull();
    expect(screen.queryByText("94%")).toBeNull();
    expect(screen.queryByText("Emaar Properties")).toBeNull();
  });
});
