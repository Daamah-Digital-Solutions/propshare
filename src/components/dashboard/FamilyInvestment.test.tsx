/**
 * Guards the Phase 10 family wiring at the component level: the group/members come
 * from the real API (the "Ahmed Al-Hassan" mock array is retired), and the
 * create-group CTA actually calls familyApi.createGroup (not a dead button).
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { FamilyInvestment } from "./FamilyInvestment";

const getGroupMock = vi.fn();
const createGroupMock = vi.fn();
const listTransfersMock = vi.fn();
const settingsMock = vi.fn();
const holdingsMock = vi.fn();

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {},
  familyApi: {
    getGroup: (...a: unknown[]) => getGroupMock(...a),
    createGroup: (...a: unknown[]) => createGroupMock(...a),
    listTransfers: (...a: unknown[]) => listTransfersMock(...a),
    settings: (...a: unknown[]) => settingsMock(...a),
    addMember: vi.fn(),
    transfer: vi.fn(),
    allocateReturns: vi.fn(),
    reinvest: vi.fn(),
  },
  holdingsApi: { mine: (...a: unknown[]) => holdingsMock(...a) },
}));

// Estate/Gifting is CapiMax's own feature (real backend planned, built last); its mock
// component is no longer mounted by FamilyInvestment, but stub it harmlessly for safety.
vi.mock("./FamilyBeneficiaryGifting", () => ({ FamilyBeneficiaryGifting: () => <div>estate</div> }));

function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <FamilyInvestment />
    </QueryClientProvider>,
  );
}

describe("FamilyInvestment", () => {
  beforeEach(() => {
    getGroupMock.mockReset();
    createGroupMock.mockReset();
    listTransfersMock.mockResolvedValue({ items: [], total: 0 });
    settingsMock.mockResolvedValue({ reinvest_discount_pct: "7.5", transfer_fee_pct: "0" });
    holdingsMock.mockResolvedValue({ items: [], total: 0 });
  });

  it("offers Create Family Group and calls the API when there's no group", async () => {
    getGroupMock.mockResolvedValue(null);
    createGroupMock.mockResolvedValue({ group_id: "g1", name: "My Family", total_returns: "0", members: [] });
    renderIt();
    const btn = await screen.findByRole("button", { name: /Create Family Group/i });
    fireEvent.click(btn);
    await waitFor(() => expect(createGroupMock).toHaveBeenCalledTimes(1));
  });

  it("renders live members from the API (the Ahmed Al-Hassan mock is retired)", async () => {
    getGroupMock.mockResolvedValue({
      group_id: "g1",
      name: "My Family",
      total_returns: "0",
      members: [
        { member_id: "m1", name: "Account Owner", email: "o@x.com", relationship: "Self (Owner)", is_verified: true, is_user: true, pending_units: 0, allocated_returns: "0", real_units: 30 },
        { member_id: "m2", name: "Real Person", email: "r@x.com", relationship: "Son", is_verified: true, is_user: true, pending_units: 0, allocated_returns: "0", real_units: 10 },
      ],
    });
    renderIt();
    expect(await screen.findByText("Real Person")).toBeInTheDocument();
    expect(screen.queryByText(/Ahmed Al-Hassan/)).toBeNull();
  });
});
