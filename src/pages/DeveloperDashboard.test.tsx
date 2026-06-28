/**
 * Phase 15: the Developer dashboard wires real aggregation — core stats (Σ from
 * listOwner), the Monthly Funding chart + "This Month" + Repeat Investors from
 * ownerStatsApi.fundingStats. Milestones + Investor Communications show an honest
 * "coming soon — being built" state (next sub-group), not fabricated data. No mock
 * literals remain.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import DeveloperDashboard from "./DeveloperDashboard";

const listOwnerMock = vi.fn();
const fundingStatsMock = vi.fn();
const milestonesListMock = vi.fn();
const updatesListMock = vi.fn();

vi.mock("@/lib/api", () => ({
  propertyApi: { listOwner: (...a: unknown[]) => listOwnerMock(...a) },
  ownerStatsApi: { fundingStats: (...a: unknown[]) => fundingStatsMock(...a) },
  ownerMilestonesApi: {
    list: (...a: unknown[]) => milestonesListMock(...a),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    reorder: vi.fn(),
  },
  ownerUpdatesApi: {
    list: (...a: unknown[]) => updatesListMock(...a),
    send: vi.fn(),
  },
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { full_name: "Test Dev", email: "dev@x.com" } }),
}));
vi.mock("@/components/dashboard/VirtualCardRequest", () => ({
  VirtualCardRequest: () => <div>cards</div>,
}));
vi.mock("@/components/developer/PropertyCreationForm", () => ({
  PropertyCreationForm: () => <div>form</div>,
}));

function wrap(node: React.ReactNode, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const PROJECTS = [
  {
    id: "p1",
    title: "Project A",
    location: "Dubai",
    image: "",
    images: [],
    status: "active",
    model: "ready-income",
    content: {},
    total_value: 5_000_000,
    funded_amount: 4_000_000,
    funding_progress: 80,
    investors_count: 200,
    expected_completion: "2026",
  },
  {
    id: "p2",
    title: "Project B",
    location: "Dubai",
    image: "",
    images: [],
    status: "active",
    model: "ready-income",
    content: {},
    total_value: 5_000_000,
    funded_amount: 6_000_000,
    funding_progress: 60,
    investors_count: 100,
    expected_completion: "2026",
  },
];

const FUNDING = {
  monthly_funding_series: [
    { month: "2026-01", amount: "0.00" },
    { month: "2026-02", amount: "250000.00" },
    { month: "2026-03", amount: "0.00" },
    { month: "2026-04", amount: "0.00" },
    { month: "2026-05", amount: "0.00" },
    { month: "2026-06", amount: "90000.00" },
  ],
  funding_this_month: "90000.00",
  repeat_investors: { repeat: 1, total: 2, pct: "50.0" },
  distinct_investors: 2,
};

describe("DeveloperDashboard real stats (Phase 15)", () => {
  beforeEach(() => {
    listOwnerMock.mockReset();
    fundingStatsMock.mockReset();
    milestonesListMock.mockReset();
    updatesListMock.mockReset();
    listOwnerMock.mockResolvedValue(PROJECTS);
    fundingStatsMock.mockResolvedValue(FUNDING);
    milestonesListMock.mockResolvedValue([]);
    updatesListMock.mockResolvedValue([]);
  });

  it("renders real core stats and the funding chart, retiring the mocks", async () => {
    wrap(<DeveloperDashboard />);
    expect(await screen.findByText("$10.0M")).toBeInTheDocument(); // Σ funded
    expect(screen.getByText("300")).toBeInTheDocument(); // Σ investors
    expect(screen.getByText("70%")).toBeInTheDocument(); // avg funding
    expect(screen.getByText("Monthly Funding Raised")).toBeInTheDocument(); // real chart card
    expect(screen.getByText("Test Dev")).toBeInTheDocument();
    expect(screen.queryByText("$45.2M")).toBeNull();
    expect(screen.queryByText("3,456")).toBeNull();
    expect(screen.queryByText("92%")).toBeNull();
    expect(screen.queryByText(/Creek Harbour Tower/i)).toBeNull();
  });

  it("shows real This Month funding on the Funding tab (deep-link)", async () => {
    wrap(<DeveloperDashboard />, "/?tab=funding");
    expect(await screen.findByText("$90,000")).toBeInTheDocument();
  });

  it("shows real Repeat Investors and the real Investor Communications surface", async () => {
    wrap(<DeveloperDashboard />, "/?tab=investors");
    expect(await screen.findByText("50.0%")).toBeInTheDocument(); // repeat investors
    // Investor Communications is now real (Phase 15c) — composer enabled, no "coming soon"
    expect(screen.getByText("Investor Communications")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Send Update/i })).toBeEnabled();
    expect(screen.queryByText(/coming soon/i)).toBeNull();
  });

  it("shows the real milestones manager with an enabled add control (Phase 15b)", async () => {
    milestonesListMock.mockResolvedValue([
      {
        id: "m1",
        property_id: "p1",
        title: "Foundation",
        description: null,
        status: "in_progress",
        progress_pct: 40,
        value_index: null,
        target_date: "2026-06-01",
        completed_at: null,
        sort_index: 0,
      },
    ]);
    wrap(<DeveloperDashboard />, "/?tab=milestones");
    const addBtn = await screen.findByRole("button", { name: /Add Milestone Update/i });
    expect(addBtn).toBeEnabled(); // real CRUD, not the old disabled stub
    expect(await screen.findByText("Foundation")).toBeInTheDocument(); // real milestone
    expect(screen.queryByText(/coming soon/i)).toBeNull(); // "coming soon" retired
  });
});
