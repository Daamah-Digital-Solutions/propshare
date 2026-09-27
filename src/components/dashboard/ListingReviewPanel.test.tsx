/**
 * A listing sent back with "changes requested": the owner reads our message, opens the same
 * form filled with what they sent, fixes it and sends it for review again.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { api } = vi.hoisted(() => ({
  api: { update: vi.fn(), submit: vi.fn(), create: vi.fn(), uploadImage: vi.fn(), upload: vi.fn() },
}));
vi.mock("@/lib/api", () => ({
  ApiError: class extends Error {},
  propertyApi: {
    update: (...a: unknown[]) => api.update(...a),
    submit: (...a: unknown[]) => api.submit(...a),
    create: (...a: unknown[]) => api.create(...a),
    uploadImage: (...a: unknown[]) => api.uploadImage(...a),
  },
  documentsApi: { upload: (...a: unknown[]) => api.upload(...a) },
}));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ListingReviewPanel } from "./ListingReviewPanel";
import type { PropertyDetail } from "@/lib/api";

const listing = (over: Partial<PropertyDetail>) =>
  ({
    id: "p1",
    title: "Cristamar Residence",
    location: "Marbella",
    property_type: "apartment",
    description: "Sea view",
    total_value: 1000000,
    unit_price: 100,
    total_units: 10000,
    minimum_investment: 500,
    target_yield: null,
    expected_completion: null,
    spv_name: null,
    spv_registration: null,
    legal_structure: null,
    status: "draft",
    ...over,
  }) as unknown as PropertyDetail;

function mount(p: PropertyDetail) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ListingReviewPanel property={p} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ListingReviewPanel", () => {
  beforeEach(() => {
    Object.values(api).forEach((f) => f.mockReset());
  });

  it("shows nothing for a listing on the market", () => {
    const { container } = mount(listing({ status: "active" }));
    expect(container).toBeEmptyDOMElement();
  });

  it("edits and resubmits a listing our team sent back", async () => {
    api.update.mockResolvedValue({ id: "p1" });
    api.submit.mockResolvedValue({ id: "p1", status: "under_review" });
    mount(
      listing({
        submitted_at: "2026-09-25T10:00:00Z",
        review_outcome: "changes_requested",
        review_note: "Minimum should be 1,000.",
      }),
    );
    expect(screen.getByText("Changes requested")).toBeInTheDocument();
    expect(screen.getByText(/Minimum should be 1,000\./)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Edit & resubmit/ }));
    // the form comes back filled with what the owner sent
    const minimum = await screen.findByLabelText(/Minimum Investment/);
    expect(minimum).toHaveValue(500);
    expect(screen.getByLabelText(/Property Title/)).toHaveValue("Cristamar Residence");
    fireEvent.change(minimum, { target: { value: "1000" } });
    fireEvent.click(screen.getByRole("button", { name: /Save & send for review/ }));

    await waitFor(() => expect(api.submit).toHaveBeenCalledWith("p1"));
    expect(api.create).not.toHaveBeenCalled();
    expect(api.update).toHaveBeenCalledWith("p1", expect.objectContaining({ minimum_investment: 1000 }));
  });

  it("offers to submit a draft that never reached us", async () => {
    api.submit.mockResolvedValue({ id: "p1", status: "under_review" });
    mount(listing({ submitted_at: null }));
    expect(screen.getByText("Draft — not submitted")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Submit for review as is/ }));
    await waitFor(() => expect(api.submit).toHaveBeenCalledWith("p1"));
  });

  it("explains a listing under review", () => {
    mount(listing({ status: "under_review", submitted_at: "2026-09-26T10:00:00Z" }));
    expect(screen.getByTestId("listing-review")).toHaveTextContent(/Our team is reviewing it/);
  });
});
