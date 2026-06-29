/**
 * Group 4 + 5: the beneficiary register and the gifting compose flow are both wired to the
 * real API (data layer). The previous hardcoded mock beneficiaries AND the fabricated gift
 * cards are gone; the lists reflect estateApi / giftsApi data and the actions hit the API.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { FamilyBeneficiaryGifting } from "./FamilyBeneficiaryGifting";

const listMock = vi.fn();
const addMock = vi.fn();
const removeMock = vi.fn();
const giftsListMock = vi.fn();
const holdingsMineMock = vi.fn();

vi.mock("@/lib/api", () => ({
  estateApi: {
    list: (...a: unknown[]) => listMock(...a),
    add: (...a: unknown[]) => addMock(...a),
    update: vi.fn(),
    remove: (...a: unknown[]) => removeMock(...a),
  },
  giftsApi: {
    list: (...a: unknown[]) => giftsListMock(...a),
    schedule: vi.fn(),
    cancel: vi.fn(),
  },
  holdingsApi: {
    mine: (...a: unknown[]) => holdingsMineMock(...a),
  },
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("FamilyBeneficiaryGifting (real estate + gifting API)", () => {
  beforeEach(() => {
    listMock.mockReset();
    addMock.mockReset();
    removeMock.mockReset();
    giftsListMock.mockReset();
    holdingsMineMock.mockReset();
    giftsListMock.mockResolvedValue([]);
    holdingsMineMock.mockResolvedValue({ items: [], total: 0 });
  });

  it("renders beneficiaries from the API and retires the hardcoded mock", async () => {
    listMock.mockResolvedValue([
      {
        id: "x1",
        full_name: "Aisha Rahman",
        relationship: "Daughter",
        email: "aisha@x.com",
        phone: null,
        allocation_pct: 70,
        notes: null,
        status: "active",
        is_user: true,
        meta: { role: "heir", scope: ["ownership"], trigger: "death" },
        created_at: "2026-06-01T00:00:00Z",
      },
    ]);
    wrap(<FamilyBeneficiaryGifting />);
    expect(await screen.findByText("Aisha Rahman")).toBeInTheDocument();
    // the deleted mock beneficiaries must not appear
    expect(screen.queryByText("Fatima Al-Hassan")).toBeNull();
    expect(screen.queryByText("Karim Lawyers LLC")).toBeNull();
    await waitFor(() => expect(listMock).toHaveBeenCalled());
  });

  it("loads scheduled gifts from the API with no fabricated gift cards", async () => {
    listMock.mockResolvedValue([]);
    giftsListMock.mockResolvedValue([
      {
        id: "g1",
        recipient_name: "Layla",
        recipient_email: "layla@x.com",
        is_user: true,
        asset_type: "property_shares",
        property_id: "p1",
        units: 5,
        amount: null,
        occasion: "birthday",
        message: "Happy birthday",
        scheduled_for: "2026-12-01",
        recurring: true,
        recurrence_end: null,
        status: "scheduled",
        failure_reason: null,
        created_at: "2026-06-01T00:00:00Z",
      },
    ]);
    wrap(<FamilyBeneficiaryGifting />);
    // a REAL scheduled gift card renders…
    expect(await screen.findByText(/Layla/)).toBeInTheDocument();
    // …and the prior fabricated mock gifts are gone
    expect(screen.queryByText("Omar Al-Hassan")).toBeNull();
    await waitFor(() => expect(giftsListMock).toHaveBeenCalled());
  });
});
