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

  it("shows an honest empty state when there are no documents", async () => {
    listMock.mockResolvedValue([]);
    wrap(<PropertyDocuments propertyId="p1" />);
    expect(
      await screen.findByText(/No documents have been published/i),
    ).toBeInTheDocument();
  });
});
