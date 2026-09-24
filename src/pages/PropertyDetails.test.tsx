/**
 * Go-live audit, Step 1: the public property page must show ONLY what the listing declares.
 * Before the fix every property displayed invented commercial terms ("Quarterly", "5 Years",
 * "Secondary Market (after 6 months)"), a stock Unsplash developer logo, "0 projects completed",
 * and fee rows (performance 10% / exit 1%) that no admin field controlled.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import PropertyDetails from "./PropertyDetails";

const getMock = vi.fn();
const { auth } = vi.hoisted(() => ({ auth: { isAuthenticated: false } }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/lib/api", () => ({
  propertyApi: { get: (...a: unknown[]) => getMock(...a) },
  documentsApi: { listForProperty: async () => [] },
  assetUrl: (u: string) => u,
  apiUrl: (u: string) => u,
}));
vi.mock("@/components/property/PropertyGallery", () => ({ default: () => <div data-testid="gallery" /> }));
vi.mock("@/components/property/InvestmentCalculator", () => ({
  default: (p: { investmentAmount: number; openReview?: boolean }) => (
    <div data-testid="invest-calc" data-amount={p.investmentAmount} data-review={String(!!p.openReview)} />
  ),
}));
vi.mock("@/components/property/InstallmentCalculator", () => ({
  default: (p: { investmentAmount: number; initialDuration?: string }) => (
    <div data-testid="installment-calc" data-amount={p.investmentAmount} data-duration={p.initialDuration ?? ""} />
  ),
}));
vi.mock("@/components/property/PropertyDocuments", () => ({ default: () => <div /> }));
vi.mock("@/components/property/PropertyTimeline", () => ({ default: () => <div /> }));
vi.mock("@/components/exit/ExitButton", () => ({ ExitButton: () => <button>exit</button> }));

const base = {
  id: "p1",
  slug: "p1",
  title: "Bare Listing",
  subtitle: null,
  location: "London",
  country: "UK",
  city: "London",
  model: "ready-income",
  property_type: "residential",
  status: "active",
  image: null,
  images: [],
  total_value: 1000000,
  minimum_investment: 100,
  unit_price: 100,
  target_yield: 7,
  expected_yield: null,
  capital_appreciation: null,
  total_return: null,
  funded_amount: 0,
  funding_progress: 0,
  total_units: 10000,
  available_units: 10000,
  investors_count: 0,
  developer_name: "Crestmark",
  description: "desc",
  expected_completion: null,
  spv_name: null,
  spv_registration: null,
  legal_structure: null,
  fees: { platform_fee: 2.5, management_fee: 1.0, installment_fee: 4.0 },
  content: {},
  owner_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  milestones: [],
  construction_progress: 0,
};

function renderIt(url = "/property/p1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/property/:id" element={<PropertyDetails />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PropertyDetails — admin preview of an unpublished listing", () => {
  beforeEach(() => getMock.mockReset());

  it("passes the ?preview token to the API and shows the preview banner for a draft", async () => {
    getMock.mockResolvedValue({ ...base, status: "draft" });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/property/p1?preview=tok123"]}>
          <Routes>
            <Route path="/property/:id" element={<PropertyDetails />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByRole("heading", { level: 1, name: "Bare Listing" });
    expect(getMock).toHaveBeenCalledWith("p1", "tok123");
    expect(screen.getByTestId("preview-banner").textContent).toMatch(/not visible to investors/);
  });
});

describe("PropertyDetails — no invented content", () => {
  beforeEach(() => getMock.mockReset());

  it("shows no hardcoded terms, fees, stock logo or fake counters for a bare listing", async () => {
    getMock.mockResolvedValue(base);
    const { container } = renderIt();
    await screen.findByRole("heading", { level: 1, name: "Bare Listing" });
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/Quarterly/);
    expect(text).not.toMatch(/5 Years/);
    expect(text).not.toMatch(/after 6 months/);
    expect(text).not.toMatch(/Performance Fee|Exit Fee/);
    expect(text).not.toMatch(/projects completed/);
    expect(text).not.toMatch(/days left/);
    expect(container.querySelector('img[src*="unsplash"]')).toBeNull();
    // ownership-ledger wording, never token/blockchain wording
    expect(text).not.toMatch(/token|blockchain|smart contract|on-chain/i);
    expect(screen.getByTestId("invest-calc")).toBeTruthy();
  });

  it("renders declared terms, per-listing fees and developer stats when the listing has them", async () => {
    getMock.mockResolvedValue({
      ...base,
      content: {
        terms: { distributionFrequency: "Monthly", investmentTerm: "7–10 years", exitOptions: "Secondary market" },
        fees: { performance: 8, exit: 1 },
        developer: { name: "Crestmark Estates", rating: 4.8, projectsCompleted: 184 },
      },
    });
    const { container } = renderIt();
    await screen.findByRole("heading", { level: 1, name: "Bare Listing" });
    expect(container.textContent).toMatch(/184 projects completed/);
    // Financials tab content is mounted only when the tab is active.
    // Radix tabs activate on pointer-down (not click) in jsdom.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Financials" }), { button: 0 });
    await waitFor(() => expect(container.textContent).toMatch(/Monthly/));
    const text = container.textContent ?? "";
    expect(text).toMatch(/7–10 years/);
    expect(text).toMatch(/Performance Fee/);
  });

  it("gives an installment listing the restored under-construction page, with the real calculator", async () => {
    getMock.mockResolvedValue({ ...base, model: "installment", title: "Thames Bay Listing" });
    renderIt();
    await screen.findByRole("heading", { level: 1, name: "Thames Bay Listing" });
    expect(screen.getByTestId("under-construction-view")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("installment-calc")).toBeTruthy());
    expect(screen.getByRole("tab", { name: /developer/i })).toBeInTheDocument(); // the 6th tab
  });

  it("keeps the ready-property layout for ready listings", async () => {
    getMock.mockResolvedValue({ ...base, model: "ready-income", title: "Ready One" });
    renderIt();
    await screen.findByRole("heading", { level: 1, name: "Ready One" });
    expect(screen.queryByTestId("under-construction-view")).toBeNull();
    expect(screen.getByTestId("invest-calc")).toBeInTheDocument();
  });
});

describe("PropertyDetails — developer card", () => {
  beforeEach(() => getMock.mockReset());

  it("View Profile opens the developer's public profile", async () => {
    getMock.mockResolvedValue({ ...base, developer_slug: "crestmark" });
    renderIt();
    const link = await screen.findByRole("link", { name: /view profile/i });
    expect(link).toHaveAttribute("href", "/developers/crestmark");
  });

  it("encodes a non-latin developer slug in the link", async () => {
    getMock.mockResolvedValue({
      ...base,
      developer_name: "إعمار",
      developer_slug: "إعمار",
    });
    renderIt();
    const link = await screen.findByRole("link", { name: /view profile/i });
    expect(link).toHaveAttribute("href", `/developers/${encodeURIComponent("إعمار")}`);
  });

  it("stays disabled only when the listing names no developer", async () => {
    getMock.mockResolvedValue({ ...base, developer_name: null, developer_slug: null });
    renderIt();
    const btn = await screen.findByRole("button", { name: /view profile/i });
    expect(btn).toBeDisabled();
    expect(screen.queryByRole("link", { name: /view profile/i })).toBeNull();
  });
});

describe("PropertyDetails — an order prepared by the assistant", () => {
  beforeEach(() => {
    getMock.mockReset();
    auth.isAuthenticated = false;
  });

  it("fills in the units, shows the banner and opens the review step for a signed-in investor", async () => {
    auth.isAuthenticated = true;
    getMock.mockResolvedValue(base);
    renderIt("/property/p1?units=100");
    const calc = await screen.findByTestId("invest-calc");
    await waitFor(() => expect(calc).toHaveAttribute("data-amount", "10000")); // 100 x $100
    expect(calc).toHaveAttribute("data-review", "true");
    expect(screen.getByTestId("assistant-order-banner")).toHaveTextContent(/100 units/);
  });

  it("never opens the review step for a visitor (sign in comes first)", async () => {
    getMock.mockResolvedValue(base);
    renderIt("/property/p1?units=100");
    const calc = await screen.findByTestId("invest-calc");
    await waitFor(() => expect(calc).toHaveAttribute("data-amount", "10000"));
    expect(calc).toHaveAttribute("data-review", "false");
  });

  it("passes the plan length to an installment listing", async () => {
    auth.isAuthenticated = true;
    getMock.mockResolvedValue({ ...base, model: "installment" });
    renderIt("/property/p1?units=20&months=18");
    const calc = await screen.findByTestId("installment-calc");
    await waitFor(() => expect(calc).toHaveAttribute("data-amount", "2000"));
    expect(calc).toHaveAttribute("data-duration", "18");
  });

  it("ignores a malformed order", async () => {
    getMock.mockResolvedValue(base);
    renderIt("/property/p1?units=abc");
    const calc = await screen.findByTestId("invest-calc");
    expect(calc).toHaveAttribute("data-amount", "100"); // the listing minimum, untouched
    expect(screen.queryByTestId("assistant-order-banner")).toBeNull();
  });
});
