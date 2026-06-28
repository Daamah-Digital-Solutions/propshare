/**
 * Group 4: the beneficiary register is now wired to the real estate API (data layer only —
 * markup/copy unchanged). The previous hardcoded mock beneficiaries are gone; the list
 * reflects estateApi data and Add calls the real endpoint.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { FamilyBeneficiaryGifting } from "./FamilyBeneficiaryGifting";

const listMock = vi.fn();
const addMock = vi.fn();
const removeMock = vi.fn();

vi.mock("@/lib/api", () => ({
  estateApi: {
    list: (...a: unknown[]) => listMock(...a),
    add: (...a: unknown[]) => addMock(...a),
    update: vi.fn(),
    remove: (...a: unknown[]) => removeMock(...a),
  },
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("FamilyBeneficiaryGifting (real estate API)", () => {
  beforeEach(() => {
    listMock.mockReset();
    addMock.mockReset();
    removeMock.mockReset();
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
});
