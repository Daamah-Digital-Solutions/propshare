/**
 * Verification tab in the investor dashboard: the same Capimax Trust hand-off as the public
 * page, plus the investor's own certificate references (the exact value printed on each PDF).
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { holdings, download } = vi.hoisted(() => ({
  holdings: vi.fn(),
  download: vi.fn(),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "abcd1234-0000-0000-0000-000000000000" } }),
}));
vi.mock("@/lib/api", () => ({
  holdingsApi: { mine: () => holdings() },
  certificateApi: { download: (id: string) => download(id) },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { VerificationTab } from "./VerificationTab";
import { CAPIMAX_TRUST_URL } from "@/components/verification/CapimaxTrustGateway";

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <VerificationTab />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("VerificationTab", () => {
  beforeEach(() => {
    holdings.mockReset();
    download.mockReset();
  });

  it("lists each held certificate with the same reference the PDF carries", async () => {
    holdings.mockResolvedValue({
      items: [
        { property_id: "9f3e7777-aaaa", title: "Marina Loft", location: "Dubai", units: 10, listed_units: 0, sellable_units: 10, unit_price: "100" },
        { property_id: "0000-sold-out", title: "Sold Out", location: "Dubai", units: 0, listed_units: 0, sellable_units: 0, unit_price: "100" },
      ],
      total: 2,
    });
    mount();
    const list = await screen.findByTestId("certificate-refs");
    // "CMX-" + property_id[:4] + user_id[:4], upper-cased (certificate_service.py)
    expect(list).toHaveTextContent("CMX-9F3EABCD");
    expect(list).toHaveTextContent("Marina Loft");
    expect(list).not.toHaveTextContent("Sold Out"); // no units, no certificate
    expect(list).not.toHaveTextContent("of the property"); // no share given, none shown
  });

  it("puts the share of the property and the link to Capimax Verify with each certificate", async () => {
    // Client (2026-10-01): under the certificate number, the link to where it is verified;
    // and how much of the property the units are (20 of 42,000 used to read 0.05%).
    holdings.mockResolvedValue({
      items: [
        { property_id: "9f3e7777-aaaa", title: "Creek Tower", location: "Dubai", units: 20, ownership_pct: "0.04762%", listed_units: 0, sellable_units: 20, unit_price: "50" },
        { property_id: "5b21cccc-bbbb", title: "Marina Loft", location: "Dubai", units: 3, ownership_pct: "0.3%", listed_units: 0, sellable_units: 3, unit_price: "100" },
      ],
      total: 2,
    });
    mount();
    const list = await screen.findByTestId("certificate-refs");
    expect(list).toHaveTextContent("20 units · 0.04762% of the property");
    expect(list).toHaveTextContent("3 units · 0.3% of the property");
    const links = within(list).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("aria-label"))).toEqual([
      "Verify certificate CMX-9F3EABCD at CIM Global Financial",
      "Verify certificate CMX-5B21ABCD at CIM Global Financial",
    ]);
    for (const a of links) {
      expect(a).toHaveTextContent("Verify at CIM Global Financial");
      expect(a).toHaveAttribute("href", "https://www.cimglobalfinancial.com/capimax-verify");
      expect(a).toHaveAttribute("target", "_blank");
      expect(a).toHaveAttribute("rel", "noopener noreferrer");
    }
  });

  it("copies a reference to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    holdings.mockResolvedValue({
      items: [{ property_id: "9f3e7777-aaaa", title: "Marina Loft", location: null, units: 5, listed_units: 0, sellable_units: 5, unit_price: "100" }],
      total: 1,
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /copy reference CMX-9F3EABCD/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("CMX-9F3EABCD"));
  });

  it("shows an honest empty state and still hands off to Capimax Trust", async () => {
    holdings.mockResolvedValue({ items: [], total: 0 });
    mount();
    await waitFor(() => expect(screen.getByTestId("no-certificates")).toBeInTheDocument());
    const cta = screen.getByRole("link", { name: /go to capimax trust/i });
    expect(cta).toHaveAttribute("href", CAPIMAX_TRUST_URL);
    expect(cta).toHaveAttribute("target", "_blank");
  });

  it("lists the verification partners, certificates first at Capimax Verify", async () => {
    holdings.mockResolvedValue({ items: [], total: 0 });
    mount();
    expect(await screen.findByTestId("verification-partners")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /verify document \/ certificate/i })).toHaveAttribute(
      "href",
      "https://www.cimglobalfinancial.com/capimax-verify",
    );
    expect(screen.getByText(/the certificate number you enter at\s+Capimax Verify/)).toBeInTheDocument();
  });
});
