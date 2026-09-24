/**
 * The restored under-construction page: same sections as the design the client knew, but
 * every block is fed by real listing data and hidden when there is none. The old page's
 * invented text ("96%", "Educational Demo", "on-chain", fake documents) must never return.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { PropertyDetail } from "@/lib/api";

const { docs } = vi.hoisted(() => ({ docs: vi.fn() }));
vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    assetUrl: (u: string) => u,
    apiUrl: (u: string) => `http://api${u}`,
    documentsApi: { listForProperty: async () => docs() },
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

function mount(detail: PropertyDetail) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <UnderConstructionView
          detail={detail}
          fees={FEES}
          investPanel={<div data-testid="invest-calc" />}
          documentsPanel={<div data-testid="real-docs" />}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const openTab = (name: RegExp) => {
  const tab = screen.getByRole("tab", { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
};

describe("UnderConstructionView", () => {
  beforeEach(() => docs.mockReset());

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
    const price = screen.getByTestId("price-appreciation");
    expect(price).toHaveTextContent("$1,050,000"); // 1,000,000 × 105 / 100
    expect(price).toHaveTextContent("$1,150,000"); // next phase
    expect(price).toHaveTextContent("$1,300,000"); // delivery
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

  it("hides the valuation download when no valuation document is uploaded", async () => {
    docs.mockReturnValue([{ id: "d2", property_id: "p1", title: "SPV", type: "spv", download_url: "/x", created_at: "" }]);
    mount({ ...base, content: { valuation: { provider: "Knight Frank" } } } as PropertyDetail);
    const val = screen.getByTestId("valuation-report");
    expect(val).toHaveTextContent("Knight Frank");
    expect(within(val).queryByRole("link", { name: /download/i })).toBeNull();
  });
});
