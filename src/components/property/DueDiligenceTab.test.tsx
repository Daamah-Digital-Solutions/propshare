import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DueDiligenceTab from "./DueDiligenceTab";

const listMock = vi.fn();
vi.mock("@/lib/api", () => ({
  apiUrl: (p: string) => `http://api.test${p}`,
  documentsApi: { listForProperty: (...a: unknown[]) => listMock(...a) },
}));

const wrap = (ui: React.ReactNode) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

const doc = (id: string, type: string, title: string, issued_on: string | null, issuer: string | null = null) => ({
  id,
  property_id: "p1",
  title,
  type,
  issuer,
  issued_on,
  download_url: `/api/v1/documents/${id}/download`,
  created_at: "2026-01-05T09:00:00Z",
});

describe("DueDiligenceTab (client letter, 2026-11-18)", () => {
  it("valuation, insurance and legal review: who, when, explanation and documents", async () => {
    listMock.mockResolvedValue([
      doc("v1", "valuation", "Q2 valuation", "2026-06-30", "Knight Frank"),
      doc("v2", "valuation", "Q3 valuation", "2026-09-30", "Knight Frank"),
      doc("l1", "due_diligence", "DD report", "2026-08-15", "Al Tamimi & Company"),
      doc("o1", "financial", "Feasibility", null),
    ]);
    wrap(
      <DueDiligenceTab
        propertyId="p1"
        content={{
          valuation: { provider: "Knight Frank", value: 1520000, reportDate: "September 2026", summary: "Comparable sales." },
          legalDueDiligence: { provider: "Al Tamimi & Company", date: "2026-08-15" },
        }}
      />,
    );
    const valuation = screen.getByTestId("dd-valuation");
    expect(await within(valuation).findByText("Q3 valuation")).toBeInTheDocument();
    expect(valuation).toHaveTextContent("Comparable sales.");
    expect(valuation).toHaveTextContent("$1,520,000");
    // newest report first
    const titles = within(valuation).getAllByTestId("doc-row").map((r) => r.querySelector("h4")?.textContent);
    expect(titles).toEqual(["Q3 valuation", "Q2 valuation"]);

    // nothing about insurance: it says so
    expect(screen.getByTestId("dd-insurance-empty")).toHaveTextContent("Not published yet for this property.");

    // the legal review: no summary written, so the standard explanation; its date and report
    const legal = screen.getByTestId("dd-legal");
    expect(legal).toHaveTextContent("The independent legal review of this property");
    expect(legal).toHaveTextContent("Aug 15, 2026");
    expect(legal).toHaveTextContent("Issued by Al Tamimi & Company");
    expect(within(legal).getAllByRole("link", { name: /download/i })[0]).toHaveAttribute(
      "href",
      "http://api.test/api/v1/documents/l1/download",
    );
    // a document of another category is not in this tab
    expect(screen.queryByText("Feasibility")).toBeNull();
  });
});
