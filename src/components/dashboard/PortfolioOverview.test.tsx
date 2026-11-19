/**
 * Phase 13: PortfolioOverview reads the server-authoritative portfolio (the hardcoded
 * $125,000 mock is retired); ProShareCards honest-disables (D9); InstallmentSchedule is now
 * REAL (Group 6, wired to installmentsApi); SecondaryMarketTab routes to the live page.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
const installmentsListMock = vi.fn();
const waitlistMock = vi.fn();
const joinMock = vi.fn();

vi.mock("@/lib/api", () => ({
  investApi: {
    portfolio: (...a: unknown[]) => portfolioMock(...a),
    list: (...a: unknown[]) => listMock(...a),
  },
  returnsApi: { getMine: (...a: unknown[]) => returnsMock(...a) },
  holdingsApi: { mine: async () => ({ items: [{ units: 10, unit_price: "110.00", average_cost: "100.00" }] }) },
  installmentsApi: {
    list: (...a: unknown[]) => installmentsListMock(...a),
    createPlan: vi.fn(),
    pay: vi.fn(),
  },
  cardsApi: {
    waitlist: (...a: unknown[]) => waitlistMock(...a),
    joinWaitlist: (...a: unknown[]) => joinMock(...a),
  },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
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
    expect(await screen.findByTestId("portfolio-value-change")).toHaveTextContent("+$100 (+10%) since purchase");
  });
});

describe("Phase 13 honest-disabled surfaces", () => {
  it("ProShareCards is a design preview: no card is issued, the investor joins the waitlist", async () => {
    // client, 2026-11-19: "Coming soon · Join the Waitlist" instead of issuing a card
    waitlistMock.mockResolvedValue({ joined: false, card_type: null, joined_at: null });
    joinMock.mockResolvedValue({ joined: true, card_type: "family", joined_at: "2026-11-19T10:00:00Z" });
    wrap(<ProShareCards />);
    // Honestly framed as a preview with sample data — not misrepresented as a live feature.
    expect(screen.getByText(/Design preview/i)).toBeInTheDocument();
    expect(screen.queryByText(/Issue New Card/i)).toBeNull();
    const button = await screen.findByRole("button", { name: "Coming soon · Join the Waitlist" });
    fireEvent.click(button);
    const dialog = await screen.findByTestId("card-waitlist-dialog");
    expect(dialog).toHaveTextContent("Cards are not issued yet.");
    fireEvent.click(screen.getByRole("radio", { name: /Family card/ }));
    fireEvent.click(screen.getByTestId("card-waitlist-join"));
    await waitFor(() => expect(joinMock).toHaveBeenCalledWith("family"));
    expect(await screen.findByRole("button", { name: "You're on the waitlist" })).toBeInTheDocument();
  });

  it("InstallmentSchedule is REAL now — honest empty state when there are no plans", async () => {
    installmentsListMock.mockResolvedValue([]); // Group 6: wired to the real API
    wrap(<InstallmentSchedule />);
    expect(await screen.findByText("No installment plans yet")).toBeInTheDocument();
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
