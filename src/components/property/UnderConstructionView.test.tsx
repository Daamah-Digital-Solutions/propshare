/**
 * The restored under-construction page: same sections as the design the client knew, but
 * every block is fed by real listing data and hidden when there is none. The old page's
 * invented text ("96%", "Educational Demo", "on-chain", fake documents) must never return.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { PropertyDetail } from "@/lib/api";

const { docs, prices } = vi.hoisted(() => ({ docs: vi.fn(), prices: vi.fn() }));
vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    assetUrl: (u: string) => u,
    apiUrl: (u: string) => `http://api${u}`,
    documentsApi: { listForProperty: async () => docs() },
    propertyApi: { prices: async (id: string) => prices(id) },
  };
});

import UnderConstructionView from "./UnderConstructionView";

const FEES = { platformFee: 2.5, managementFee: 1, installmentFee: 4, performanceFee: null, exitFee: 2 };

const base: PropertyDetail = {
  id: "p1",
  slug: "creek-tower",
  title: "Creek Tower",
  subtitle: "Off-plan residences",
  location: "Dubai Creek Harbour",
  country: "UAE",
  city: "Dubai",
  model: "installment",
  property_type: "apartment",
  status: "active",
  image: null,
  images: [],
  total_value: 1_000_000,
  minimum_investment: 100,
  unit_price: 100,
  target_yield: null,
  expected_yield: null,
  capital_appreciation: null,
  total_return: null,
  funded_amount: 0,
  funding_progress: 0,
  total_units: 10000,
  available_units: 10000,
  investors_count: 0,
  developer_name: null,
  developer_slug: null,
  description: "A tower under construction.",
  expected_completion: null,
  spv_name: null,
  spv_registration: null,
  legal_structure: null,
  fees: null,
  content: {},
  owner_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  milestones: [],
  construction_progress: 0,
} as PropertyDetail;

const ms = (over: Partial<PropertyDetail["milestones"][number]>) => ({
  id: over.title ?? "m",
  property_id: "p1",
  title: "M",
  description: null,
  status: "planned" as const,
  progress_pct: null,
  value_index: null,
  target_date: null,
  completed_at: null,
  sort_index: 0,
  ...over,
});

const full: PropertyDetail = {
  ...base,
  capital_appreciation: 18,
  investors_count: 54,
  spv_name: "Creek Tower SPV Ltd",
  developer_name: "Harbour Line",
  developer_slug: "harbour-line",
  construction_progress: 40,
  expected_completion: "2028-06-30",
  milestones: [
    ms({ title: "Down payment", status: "completed", value_index: 100, target_date: "2026-06-01" }),
    ms({ title: "Foundation", status: "in_progress", progress_pct: 40, value_index: 105, target_date: "2026-12-01" }),
    ms({ title: "Structure", status: "planned", value_index: 115, target_date: "2027-08-01" }),
    ms({ title: "Handover", status: "planned", value_index: 130, target_date: "2028-06-01" }),
  ],
  content: {
    developer: {
      name: "Harbour Line",
      verified: true,
      rating: 4.6,
      projectsCompleted: 42,
      yearsExperience: 12,
      onTimeDelivery: 96,
      about: "Founded in 2010.",
      previousProjects: ["Marina Heights"],
      verifications: ["Trade license verified"],
    },
    spv: { jurisdiction: "DIFC", assetHolding: "100% title held by the SPV", trustee: "Gulf Trustees" },
    valuation: { provider: "Knight Frank", reportDate: "June 2026", value: 1050000, impactNote: "+5% since foundation", summary: "Supply is limited." },
    construction: { engineeringStatus: "Certified", auditStatus: "On track" },
    cashflow: { rentalProjection: "Income after handover.", exitProjection: "Secondary market." },
    ownershipStructure: [{ label: "Ownership vehicle", value: "DIFC SPV" }],
    investmentStructure: [{ label: "Final settlement", value: "On handover" }],
    marketAnalysis: [{ label: "Area pipeline", value: "12 active towers" }],
    scenarios: [{ label: "On-time delivery", outcome: "About 18% by handover", tone: "positive" }],
    risks: [{ label: "Construction delay", level: "medium", note: "Escrow and milestone audits" }],
    exitMechanisms: [{ name: "Secondary market", eta: "After handover", description: "Sell units" }],
    compliance: ["SPV holds the title", "Escrow-secured payments"],
    // legacy demo blobs the page must NOT render
    installmentTerms: { monthly: "Equal monthly payments tracked on-chain" },
    documents: [{ name: "Fake Deed", type: "PDF", size: "1 MB" }],
  },
} as PropertyDetail;

function mount(detail: PropertyDetail, preview?: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <UnderConstructionView
          detail={detail}
          fees={FEES}
          preview={preview}
          investPanel={<div data-testid="invest-calc" />}
          documentsPanel={<div data-testid="real-docs" />}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// the price line of a listing whose price never changed: its launch price is its only point
const flat = (price: string) => ({
  property_id: "p1",
  current_price: price,
  launch_price: price,
  change_pct: "0.00",
  updated_at: null,
  phase: null,
  points: [{ at: "2026-01-01T00:00:00Z", price, change_pct: "0.00", label: "Launch price", note: null }],
});

const openTab = (name: RegExp) => {
  const tab = screen.getByRole("tab", { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
};

describe("UnderConstructionView", () => {
  beforeEach(() => {
    docs.mockReset();
    prices.mockReset();
    prices.mockReturnValue(flat("100.00"));
  });

  it("restores every section of the old design from real listing data", async () => {
    docs.mockReturnValue([{ id: "d1", property_id: "p1", title: "Valuation", type: "valuation", download_url: "/api/v1/documents/d1/download", created_at: "" }]);
    mount(full);

    // hero + the six tabs of the old page
    expect(screen.getByRole("heading", { level: 1, name: "Creek Tower" })).toBeInTheDocument();
    for (const t of [/overview/i, /financials/i, /spv structure/i, /documents/i, /timeline/i, /developer/i]) {
      expect(screen.getByRole("tab", { name: t })).toBeInTheDocument();
    }
    expect(screen.getByTestId("invest-calc")).toBeInTheDocument(); // investing still works
    expect(screen.getByText("$100 per unit")).toBeInTheDocument(); // the unit price is shown

    // overview blocks
    expect(screen.getByTestId("installment-structure")).toHaveTextContent("15% down");
    const cp = screen.getByTestId("construction-progress");
    expect(cp).toHaveTextContent("40%");
    expect(cp).toHaveTextContent("Foundation");
    expect(cp).toHaveTextContent("Certified");
    // the price now is the real unit price; the stages' price indexes are estimates per unit
    const price = screen.getByTestId("price-appreciation");
    expect(price).toHaveTextContent("Launch Price$100");
    expect(price).toHaveTextContent("Unit Price Now$100Unchanged since launch");
    expect(price).toHaveTextContent("Next Expected Price$105At Foundation · +5% · estimate"); // 100 × 105 / 100
    expect(price).toHaveTextContent("Estimated Delivery Price$130"); // 100 × 130 / 100
    expect(price).toHaveTextContent(/estimates set per construction stage, not guarantees/i);
    const val = screen.getByTestId("valuation-report");
    expect(val).toHaveTextContent("Knight Frank");
    expect(await within(val).findByRole("link", { name: /download valuation report/i })).toHaveAttribute(
      "href",
      "http://api/api/v1/documents/d1/download",
    );
    expect(screen.getByTestId("scenarios")).toHaveTextContent("About 18% by handover");
    expect(screen.getByTestId("risks")).toHaveTextContent("MEDIUM");
    expect(screen.getByTestId("ownership-structure")).toHaveTextContent("DIFC SPV");

    openTab(/financials/i);
    expect(screen.getByText("Final settlement")).toBeInTheDocument();
    expect(screen.getByText("12 active towers")).toBeInTheDocument();
    expect(screen.getByText("Income after handover.")).toBeInTheDocument();
    expect(screen.getByTestId("fee-structure")).toHaveTextContent("4%");
    expect(screen.getByTestId("exit-mechanisms")).toHaveTextContent("After handover");

    openTab(/spv structure/i);
    expect(screen.getByText("Creek Tower SPV Ltd")).toBeInTheDocument();
    expect(screen.getByText("100% title held by the SPV")).toBeInTheDocument();
    expect(screen.getByTestId("compliance")).toHaveTextContent("Escrow-secured payments");

    openTab(/documents/i);
    expect(screen.getByTestId("real-docs")).toBeInTheDocument();
    expect(screen.queryByText("Fake Deed")).toBeNull();

    openTab(/timeline/i);
    expect(screen.getByTestId("timeline")).toHaveTextContent("Price index 115");

    openTab(/developer/i);
    const devTab = screen.getByTestId("developer-tab");
    expect(devTab).toHaveTextContent("Verified developer");
    expect(devTab).toHaveTextContent("96%");
    expect(devTab).toHaveTextContent("Marina Heights");
    expect(within(devTab).getByRole("link", { name: /view full developer profile/i })).toHaveAttribute(
      "href",
      "/developers/harbour-line",
    );

    // the legacy blob with forbidden wording is never shown
    expect(document.body.textContent).not.toMatch(/on-chain/i);
  });

  it("invents nothing for a bare listing", async () => {
    docs.mockReturnValue([]);
    mount(base);
    for (const id of ["construction-progress", "price-appreciation", "valuation-report", "scenarios", "risks", "ownership-structure"]) {
      expect(screen.queryByTestId(id)).toBeNull();
    }
    const text = () => document.body.textContent ?? "";
    expect(text()).not.toMatch(/96%|Educational Demo|on-chain|Verified developer|JLL|Knight Frank/);
    openTab(/spv structure/i);
    expect(screen.getByText(/SPV details have not been published/i)).toBeInTheDocument();
    openTab(/timeline/i);
    expect(screen.getByText(/No project milestones have been published yet/i)).toBeInTheDocument();
    openTab(/developer/i);
    expect(screen.getByText(/No developer is named/i)).toBeInTheDocument();
  });

  it("shows no price progression when milestones carry no price index", () => {
    docs.mockReturnValue([]);
    mount({
      ...base,
      construction_progress: 30,
      milestones: [ms({ title: "Foundation", status: "in_progress", progress_pct: 30 })],
    } as PropertyDetail);
    expect(screen.getByTestId("construction-progress")).toHaveTextContent("30%");
    expect(screen.queryByTestId("price-appreciation")).toBeNull();
  });

  it("shows the recorded unit price and its history, never an estimate the price already passed", async () => {
    docs.mockReturnValue([]);
    // launched at $100, phase 2 opened at $110: the Foundation estimate ($105) is behind it
    prices.mockReturnValue({
      property_id: "p1",
      current_price: "110.00",
      launch_price: "100.00",
      change_pct: "10.00",
      updated_at: "2026-09-01T09:00:00Z",
      phase: "Phase 2",
      points: [
        { at: "2026-01-01T00:00:00Z", price: "100.00", change_pct: "0.00", label: "Launch price", note: null },
        { at: "2026-09-01T09:00:00Z", price: "110.00", change_pct: "10.00", label: "Phase 2", note: "Structure topped out" },
      ],
    });
    // 4,000 of the 10,000 units were sold at $100: the offering's own total is a blend
    mount({
      ...full,
      unit_price: 110,
      launch_price: 100,
      total_value: 1_060_000,
      available_units: 6000,
    } as PropertyDetail);
    const price = await screen.findByTestId("price-appreciation");
    await waitFor(() => expect(price).toHaveTextContent("Unit Price Now$110+10% since launch"));
    expect(price).toHaveTextContent("Launch Price$100");
    expect(price).toHaveTextContent("Phase 2");
    expect(price).not.toHaveTextContent("$105"); // already behind the real price
    expect(price).toHaveTextContent("Next Expected Price$115At Structure"); // 100 × 115 / 100
    expect(price).toHaveTextContent("Estimated Delivery Price$130");
    const history = within(price).getByTestId("unit-price-history");
    expect(history).toHaveTextContent("Sep 1, 2026Phase 2Structure topped out$110 +10%");
    // the asset is every unit at the price now, not the blended total of the offering
    expect(screen.getAllByText("$1,100,000").length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toContain("$1,060,000");
    expect(prices).toHaveBeenCalledWith("p1");
  });

  it("needs no second request to say how far the price has moved", async () => {
    docs.mockReturnValue([]);
    // the history request fails (or has not answered yet): the listing itself carries its
    // launch price, so the tiles and the stage estimates are still right
    prices.mockImplementation(() => {
      throw new Error("offline");
    });
    mount({ ...full, unit_price: 110, launch_price: 100, total_value: 1_060_000 } as PropertyDetail);
    const price = screen.getByTestId("price-appreciation");
    expect(price).toHaveTextContent("Launch Price$100");
    expect(price).toHaveTextContent("Unit Price Now$110+10% since launch");
    expect(price).toHaveTextContent("Next Expected Price$115At Structure");
    expect(price).toHaveTextContent("Estimated Delivery Price$130");
    expect(price).not.toHaveTextContent("Unchanged since launch");
    expect(within(price).queryByTestId("unit-price-history")).toBeNull();
    expect(screen.getAllByText("$1,100,000").length).toBeGreaterThan(0);
  });

  it("names a listing by how it is bought", async () => {
    docs.mockReturnValue([]);
    const { unmount } = mount({ ...base, offplan_payment: "full" } as PropertyDetail);
    // a project sold in phases: no installment card, and the page says how it is paid
    expect(screen.getAllByText(/Property Sold in Phases/).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("installment-structure")).toBeNull();
    expect(screen.getByTestId("phase-structure")).toHaveTextContent(/in full at the price of the phase open today/i);
    expect(screen.getByTestId("phase-structure")).toHaveTextContent("$100 per unit");
    openTab(/financials/i);
    expect(screen.getByTestId("fee-structure")).not.toHaveTextContent(/installment fee/i);
    unmount();

    mount({ ...base, offplan_payment: "both" } as PropertyDetail);
    expect(screen.getAllByText(/Under-Construction Property/).length).toBeGreaterThan(0);
    expect(screen.getByTestId("installment-structure")).toHaveTextContent(/you can also pay for your units in full/i);
    expect(screen.queryByTestId("phase-structure")).toBeNull();
    expect(screen.getByText("Full payment, or an installment plan · 6 to 24 months")).toBeInTheDocument();
  });

  it("asks for no price history while a draft is previewed", () => {
    docs.mockReturnValue([]);
    mount(base, "tok123");
    expect(prices).not.toHaveBeenCalled();
  });

  it("hides the valuation download when no valuation document is uploaded", async () => {
    docs.mockReturnValue([{ id: "d2", property_id: "p1", title: "SPV", type: "spv", download_url: "/x", created_at: "" }]);
    mount({ ...base, content: { valuation: { provider: "Knight Frank" } } } as PropertyDetail);
    const val = screen.getByTestId("valuation-report");
    expect(val).toHaveTextContent("Knight Frank");
    expect(within(val).queryByRole("link", { name: /download/i })).toBeNull();
  });
});
