/**
 * The investor follows each Nova Sukuk certificate: under review (units held), approved
 * (pledged to Nova Finance), not accepted (with our team's reason) or pledge released.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { SukukCertificatesCard } from "./SukukCertificatesCard";

const mine = vi.fn();
vi.mock("@/lib/api", () => ({ investApi: { mySukuk: () => mine() } }));

const cert = (over: Record<string, unknown>) => ({
  certificate_id: String(Math.random()),
  kind: "purchase",
  status: "pending",
  investment_id: "i1",
  plan_id: null,
  property_id: "p1",
  property_title: "Marina Loft",
  property_slug: null,
  units: 10,
  amount_due: "1025.00",
  certificate_no: "NOVA-1",
  issuer: "Nova Digital Finance",
  review_note: null,
  created_at: null,
  reviewed_at: null,
  released_at: null,
  ...over,
});

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SukukCertificatesCard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SukukCertificatesCard", () => {
  it("shows every certificate with where its review stands", async () => {
    mine.mockResolvedValue([
      cert({}),
      cert({ status: "approved" }),
      cert({ status: "rejected", review_note: "Not signed by Nova." }),
      cert({ status: "released", kind: "installment", plan_id: "pl1", investment_id: null }),
    ]);
    mount();
    expect(await screen.findByText("Under review")).toBeInTheDocument();
    expect(screen.getByText("Approved — pledged to Nova")).toBeInTheDocument();
    expect(screen.getByText(/Reason: Not signed by Nova\./)).toBeInTheDocument();
    expect(screen.getByText("Pledge released")).toBeInTheDocument();
    expect(screen.getByText(/Installment plan down payment — Marina Loft/)).toBeInTheDocument();
    expect(screen.getAllByText(/10 unit\(s\) of Marina Loft · \$1,025\.00/).length).toBe(3);
  });

  it("shows nothing without certificates", async () => {
    mine.mockResolvedValue([]);
    const { container } = mount();
    await new Promise((r) => setTimeout(r, 0));
    expect(container.querySelector("[data-testid='sukuk-certificates']")).toBeNull();
  });
});
