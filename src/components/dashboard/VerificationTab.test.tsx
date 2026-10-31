/**
 * Verification tab in the investor dashboard: the same Capimax Trust hand-off as the public
 * page, plus the investor's own certificates (client, 2026-10-28): the number and the
 * verification code the server issued, as printed beside each one's QR code, and the link to
 * the certificate's own verification page on the platform.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mine, download, save } = vi.hoisted(() => ({
  save: vi.fn(),
  mine: vi.fn(),
  download: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  certificateApi: { mine: () => mine(), download: (id: string) => download(id) },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("@/lib/certificates", () => ({ saveBlob: (b: Blob, n: string) => save(b, n) }));

import { VerificationTab } from "./VerificationTab";
import { CAPIMAX_TRUST_URL } from "@/components/verification/CapimaxTrustGateway";

const cert = (over: Record<string, unknown>) => ({
  id: "c1",
  property_id: "p1",
  property_title: "Marina Loft",
  number: "PSC-2026-K7M2Q9XA",
  verification_code: "Xq3vN8bKp2LmR5tY7wZa1c",
  verify_path: "/verify/Xq3vN8bKp2LmR5tY7wZa1c",
  verify_url: "https://capimaxpropshare.com/verify/Xq3vN8bKp2LmR5tY7wZa1c",
  units: 10,
  ownership: "0.3%",
  spv_name: null,
  location: "Dubai",
  status: "valid",
  issued_at: "2026-10-20T09:00:00Z",
  ...over,
});

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
    mine.mockReset();
    download.mockReset();
  });

  it("lists each certificate with its number, code, share and its own verification page", async () => {
    mine.mockResolvedValue({
      items: [
        cert({ units: 20, ownership: "0.04762%", property_title: "Creek Tower" }),
        cert({
          id: "c2",
          property_id: "p2",
          number: "PSC-2026-B3N8W4ZT",
          verification_code: "aB3dE5fG7hJ9kL2mN4pQ6r",
          verify_path: "/verify/aB3dE5fG7hJ9kL2mN4pQ6r",
          units: 3,
        }),
      ],
    });
    mount();
    const list = await screen.findByTestId("certificate-refs");
    expect(list).toHaveTextContent("Creek Tower");
    expect(list).toHaveTextContent("20 units · 0.04762% of the property");
    expect(list).toHaveTextContent("3 units · 0.3% of the property");
    expect(list).toHaveTextContent("Certificate PSC-2026-K7M2Q9XA");
    expect(list).toHaveTextContent("Xq3vN8bKp2LmR5tY7wZa1c");
    const links = within(list).getAllByRole("link");
    expect(links.map((a) => [a.getAttribute("aria-label"), a.getAttribute("href")])).toEqual([
      ["Verify certificate PSC-2026-K7M2Q9XA", "/verify/Xq3vN8bKp2LmR5tY7wZa1c"],
      ["Verify certificate PSC-2026-B3N8W4ZT", "/verify/aB3dE5fG7hJ9kL2mN4pQ6r"],
    ]);
    for (const a of links) expect(a).not.toHaveAttribute("target"); // on the platform itself
    expect(list).not.toHaveTextContent(/CIM Global Financial|CMX-/);
  });

  it("copies a verification code to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    mine.mockResolvedValue({ items: [cert({})] });
    mount();
    fireEvent.click(
      await screen.findByRole("button", { name: /copy verification code of PSC-2026-K7M2Q9XA/i }),
    );
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("Xq3vN8bKp2LmR5tY7wZa1c"));
  });

  it("downloads the PDF and reads the list again (a download may issue a new certificate)", async () => {
    mine.mockResolvedValue({ items: [cert({})] });
    const pdf = new Blob(["%PDF"]);
    download.mockResolvedValue(pdf);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /download certificate for marina loft/i }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(pdf, "certificate-Marina Loft.pdf"));
    expect(download).toHaveBeenCalledWith("p1");
    await waitFor(() => expect(mine).toHaveBeenCalledTimes(2));
  });

  it("shows an honest empty state and still hands off to Capimax Trust", async () => {
    mine.mockResolvedValue({ items: [] });
    mount();
    await waitFor(() => expect(screen.getByTestId("no-certificates")).toBeInTheDocument());
    const cta = screen.getByRole("link", { name: /go to capimax trust/i });
    expect(cta).toHaveAttribute("href", CAPIMAX_TRUST_URL);
    expect(cta).toHaveAttribute("target", "_blank");
  });

  it("lists the verification services, certificates first, checked here by their code", async () => {
    mine.mockResolvedValue({ items: [] });
    mount();
    expect(await screen.findByTestId("verification-partners")).toBeInTheDocument();
    expect(screen.getByTestId("certificate-check")).toBeInTheDocument();
    expect(screen.getByText(/Scanning the QR code, or entering the code on the Verification Center/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /verify document \/ certificate/i })).toBeNull();
  });
});
