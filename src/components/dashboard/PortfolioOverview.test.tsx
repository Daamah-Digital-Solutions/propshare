/**
 * Phase 13: PortfolioOverview reads the server-authoritative portfolio (the hardcoded
 * $125,000 mock is retired); ProShareCards + InstallmentSchedule honest-disable (D9 /
 * deferred); SecondaryMarketTab routes to the live page. DELETE NOTHING — components stay.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { PortfolioOverview } from "./PortfolioOverview";
import { ProShareCards } from "./ProShareCards";
import { InstallmentSchedule } from "./InstallmentSchedule";
import { SecondaryMarketTab } from "./SecondaryMarketTab";

const portfolioMock = vi.fn();
const listMock = vi.fn();
const returnsMock = vi.fn();

vi.mock("@/lib/api", () => ({
  investApi: {
    portfolio: (...a: unknown[]) => portfolioMock(...a),
    list: (...a: unknown[]) => listMock(...a),
  },
  returnsApi: { getMine: (...a: unknown[]) => returnsMock(...a) },
}));
vi.mock("@/components/exit/ExitButton", () => ({ ExitButton: () => <button>exit</button> }));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PortfolioOverview (live)", () => {
  beforeEach(() => {
    listMock.mockResolvedValue({ items: [], total: 0 });
    returnsMock.mockResolvedValue({ total_net: "0", total_management_fee: "0", count: 0, monthly: [], items: [] });
  });

  it("shows server portfolio values and retires the $125,000 mock", async () => {
    portfolioMock.mockResolvedValue({
      invested: "1000.00",
      current_value: "1500.00",
      total_returns: "200.00",
      properties: 2,
      units: 15,
    });
    wrap(<PortfolioOverview />);
    expect(await screen.findByText("$1,500")).toBeInTheDocument(); // current value (live)
    expect(screen.getByText("$1,000")).toBeInTheDocument(); // invested
    expect(screen.queryByText("$125,000")).toBeNull(); // mock retired
  });
});

describe("Phase 13 honest-disabled surfaces", () => {
  it("ProShareCards is not available yet (D9)", () => {
    render(<ProShareCards />);
    expect(screen.getByText(/not yet available/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Request Card/i })).toBeDisabled();
  });

  it("InstallmentSchedule is not available yet", () => {
    render(<InstallmentSchedule />);
    expect(screen.getByText(/not available yet/i)).toBeInTheDocument();
  });

  it("SecondaryMarketTab routes to the live secondary market", () => {
    render(
      <MemoryRouter>
        <SecondaryMarketTab />
      </MemoryRouter>,
    );
    const link = screen.getByRole("link", { name: /Open Secondary Market/i });
    expect(link).toHaveAttribute("href", "/secondary-market");
  });
});
