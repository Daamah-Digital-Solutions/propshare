/**
 * Group 2: PropertyDocuments lists REAL documents from the storage-backed API (the
 * hardcoded mock list is gone) with working download links, and an honest empty state.
 */
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import PropertyDocuments from "./PropertyDocuments";

const listMock = vi.fn();

vi.mock("@/lib/api", () => ({
  documentsApi: { listForProperty: (...a: unknown[]) => listMock(...a) },
  apiUrl: (p: string) => `http://api.test${p}`,
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("PropertyDocuments (Group 2 real documents)", () => {
  beforeEach(() => listMock.mockReset());

  it("renders real documents with a working download link", async () => {
    listMock.mockResolvedValue([
      {
        id: "d1",
        property_id: "p1",
        title: "Offering Memorandum",
        type: "pdf",
        download_url: "/api/v1/documents/d1/download",
        created_at: "2026-06-01T00:00:00Z",
      },
    ]);
    wrap(<PropertyDocuments propertyId="p1" />);
    expect(await screen.findByText("Offering Memorandum")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /download/i });
    expect(link).toHaveAttribute("href", "http://api.test/api/v1/documents/d1/download");
    // mock list retired
    expect(screen.queryByText("SPV Formation Documents")).toBeNull();
    expect(screen.queryByText(/not available yet/i)).toBeNull();
  });

  it("groups documents by category, with who issued each and its date (client letter, 2026-11-18)", async () => {
    listMock.mockResolvedValue([
      { id: "a", property_id: "p1", title: "Policy", type: "insurance", issuer: "AXA Gulf", issued_on: "2026-03-12", download_url: "/a", created_at: "2026-06-01T00:00:00Z" },
      { id: "b", property_id: "p1", title: "Q2 valuation", type: "valuation", issuer: "Knight Frank", issued_on: "2026-06-30", download_url: "/b", created_at: "2026-07-01T00:00:00Z" },
      { id: "c", property_id: "p1", title: "Q1 valuation", type: "valuation", issuer: null, issued_on: null, download_url: "/c", created_at: "2026-04-02T10:00:00Z" },
      { id: "d", property_id: "p1", title: "Brochure", type: "brochure-old", download_url: "/d", created_at: "2026-01-01T00:00:00Z" },
    ]);
    wrap(<PropertyDocuments propertyId="p1" />);
    await screen.findByText("Policy");
    const groups = screen.getAllByTestId("doc-group").map((g) => g.querySelector("h4")?.textContent);
    expect(groups).toEqual(["Valuation Reports", "Insurance Certificates", "Other Documents"]);
    const rows = screen.getAllByTestId("doc-row").map((r) => r.textContent);
    expect(rows[0]).toContain("Issued by Knight Frank");
    expect(rows[0]).toContain("Jun 30, 2026");
    expect(rows[1]).toContain("Apr 2, 2026"); // no date on the document: its upload date
    expect(rows[2]).toContain("Issued by AXA Gulf");
  });

  it("shows an honest empty state when there are no documents", async () => {
    listMock.mockResolvedValue([]);
    wrap(<PropertyDocuments propertyId="p1" />);
    expect(
      await screen.findByText(/No documents have been published/i),
    ).toBeInTheDocument();
  });
});
