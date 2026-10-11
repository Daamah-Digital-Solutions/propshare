/**
 * Guards the Phase 10 family wiring at the component level: the group/members come
 * from the real API (the "Ahmed Al-Hassan" mock array is retired), and the
 * create-group CTA actually calls familyApi.createGroup (not a dead button).
 *
 * And the traces a family action leaves (client, 2026-10-07): the transfer history says who,
 * what and when; a transfer is always sent from the member's own units; a member who was only
 * ever on the receiving side sees what came to them although they have no group.
 */
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { FamilyInvestment } from "./FamilyInvestment";

const getGroupMock = vi.fn();
const createGroupMock = vi.fn();
const listTransfersMock = vi.fn();
const settingsMock = vi.fn();
const holdingsMock = vi.fn();
const activityMock = vi.fn();
const transferMock = vi.fn();

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {},
  familyApi: {
    getGroup: (...a: unknown[]) => getGroupMock(...a),
    createGroup: (...a: unknown[]) => createGroupMock(...a),
    listTransfers: (...a: unknown[]) => listTransfersMock(...a),
    settings: (...a: unknown[]) => settingsMock(...a),
    activity: (...a: unknown[]) => activityMock(...a),
    addMember: vi.fn(),
    transfer: (...a: unknown[]) => transferMock(...a),
    allocateReturns: vi.fn(),
    reinvest: vi.fn(),
  },
  holdingsApi: { mine: (...a: unknown[]) => holdingsMock(...a) },
}));

// The register and the gifting section have their own tests; here they are stand-ins.
vi.mock("./BeneficiaryRegister", () => ({ BeneficiaryRegister: () => <div>beneficiary register</div> }));
vi.mock("./FamilyBeneficiaryGifting", () => ({ FamilyGifting: () => <div>gifting section</div> }));
vi.mock("react-router-dom", () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
}));

function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <FamilyInvestment />
    </QueryClientProvider>,
  );
}

const GROUP = {
  group_id: "g1",
  name: "My Family",
  total_returns: "0",
  members: [
    { member_id: "m1", name: "Account Owner", email: "o@x.com", relationship: "Self (Owner)", is_verified: true, is_user: true, is_self: true, pending_units: 0, allocated_returns: "0", real_units: 30 },
    { member_id: "m2", name: "Real Person", email: "r@x.com", relationship: "Son", is_verified: true, is_user: true, pending_units: 0, allocated_returns: "0", real_units: 10 },
    { member_id: "m3", name: "Sara", email: "s@x.com", relationship: "Daughter", is_verified: false, is_user: false, pending_units: 4, allocated_returns: "120", pending_returns: "120", real_units: 0 },
  ],
};

describe("FamilyInvestment", () => {
  beforeEach(() => {
    getGroupMock.mockReset();
    createGroupMock.mockReset();
    transferMock.mockReset();
    activityMock.mockReset();
    activityMock.mockResolvedValue({ items: [], memberships: [] });
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
    // nothing happened in any family yet: no empty activity card under the invitation
    expect(screen.queryByTestId("family-activity")).toBeNull();
  });

  it("renders live members from the API (the Ahmed Al-Hassan mock is retired)", async () => {
    getGroupMock.mockResolvedValue(GROUP);
    renderIt();
    expect(await screen.findByText("Real Person")).toBeInTheDocument();
    expect(screen.queryByText(/Ahmed Al-Hassan/)).toBeNull();
  });

  it("a member without a group of their own sees what came to them", async () => {
    getGroupMock.mockResolvedValue(null);
    activityMock.mockResolvedValue({
      memberships: [
        { group_name: "The Mansouris", owner_name: "Ahmed Mansouri", relationship: "Son", since: "2026-10-01T10:00:00Z", is_verified: true },
      ],
      items: [
        { id: "transfer:t1", kind: "transfer", direction: "in", at: "2026-10-02T10:00:00Z", counterparty: "Ahmed Mansouri", from_name: "Ahmed Mansouri", property_id: "p1", property_title: "Marina Heights", units: 10, amount: null, fee: null, status: "completed", completed_at: "2026-10-02T10:00:00Z", relationship: null },
        { id: "returns:r1", kind: "returns", direction: "in", at: "2026-10-03T10:00:00Z", counterparty: "Ahmed Mansouri", from_name: null, property_id: null, property_title: null, units: null, amount: "300.00", fee: null, status: "allocated", completed_at: null, relationship: null },
        { id: "member:m9", kind: "member", direction: "in", at: "2026-10-01T10:00:00Z", counterparty: "Ahmed Mansouri", from_name: null, property_id: null, property_title: null, units: null, amount: null, fee: null, status: "verified", completed_at: null, relationship: "Son" },
      ],
    });
    renderIt();
    expect(await screen.findByText("Ahmed Mansouri transferred 10 units of Marina Heights to you")).toBeInTheDocument();
    expect(screen.getByText("Ahmed Mansouri allocated $300.00 to you")).toBeInTheDocument();
    expect(screen.getByText("Ahmed Mansouri added you to their family group as Son")).toBeInTheDocument();
    expect(screen.getByText("Ahmed Mansouri's family group")).toBeInTheDocument();
    expect(screen.getByText(/You are their Son/)).toBeInTheDocument();
    // the dates are on the lines
    expect(screen.getAllByText(/Oct 2, 2026/).length).toBeGreaterThan(0);
  });

  it("the transfer history says who, what and when", async () => {
    getGroupMock.mockResolvedValue(GROUP);
    listTransfersMock.mockResolvedValue({
      total: 2,
      items: [
        { transfer_id: "t2", from_member_id: "m1", to_member_id: "m3", property_id: "p1", units: 4, transfer_fee: "0", status: "pending", created_at: "2026-10-05T09:00:00Z", from_name: "Account Owner", to_name: "Sara", property_title: "Marina Heights", completed_at: null },
        { transfer_id: "t1", from_member_id: "m1", to_member_id: "m2", property_id: "p1", units: 10, transfer_fee: "12.50", status: "completed", created_at: "2026-10-02T09:00:00Z", from_name: "Account Owner", to_name: "Real Person", property_title: "Marina Heights", completed_at: "2026-10-02T09:00:00Z" },
      ],
    });
    renderIt();
    fireEvent.mouseDown(await screen.findByRole("tab", { name: /Transfers/i }));
    const rows = await screen.findAllByTestId("transfer-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Account Owner → Sara")).toBeInTheDocument();
    expect(within(rows[0]).getByText("4 units of Marina Heights")).toBeInTheDocument();
    expect(within(rows[0]).getByText(/Oct 5, 2026 · held until they verify/)).toBeInTheDocument();
    expect(within(rows[1]).getByText("Account Owner → Real Person")).toBeInTheDocument();
    expect(within(rows[1]).getByText("10 units of Marina Heights · fee $12.5")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Oct 2, 2026")).toBeInTheDocument();
  });

  it("a transfer is sent from the member's own units, to someone else", async () => {
    getGroupMock.mockResolvedValue(GROUP);
    holdingsMock.mockResolvedValue({ items: [{ property_id: "p1", title: "Marina Heights", units: 30 }], total: 1 });
    renderIt();
    fireEvent.mouseDown(await screen.findByRole("tab", { name: /Transfers/i }));
    fireEvent.click(await screen.findByRole("button", { name: /New Transfer/i }));
    // no choosing whose units move: they are the member's own
    expect(await screen.findByTestId("transfer-from")).toHaveTextContent("You (30 units)");
    expect(screen.queryByText("From Member")).toBeNull();
    // nothing to send until a recipient, a property and a number of units are chosen
    expect(screen.getByRole("button", { name: "Complete Transfer" })).toBeDisabled();
  });

  it("the Activity, Beneficiaries and Gifting tabs each show their own section", async () => {
    getGroupMock.mockResolvedValue(GROUP);
    renderIt();
    fireEvent.mouseDown(await screen.findByRole("tab", { name: /Activity/i }));
    expect(await screen.findByText("No family activity yet.")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Beneficiaries|Estate/i }));
    expect(await screen.findByText("beneficiary register")).toBeInTheDocument();
    expect(screen.queryByText("gifting section")).toBeNull();
    fireEvent.mouseDown(screen.getByRole("tab", { name: /Gifting/i }));
    // the real gifting section, not a "not available yet" card
    expect(await screen.findByText("gifting section")).toBeInTheDocument();
    expect(screen.queryByText(/not available yet/i)).toBeNull();
  });

  it("says what a member who cannot be paid yet is still owed", async () => {
    getGroupMock.mockResolvedValue(GROUP);
    renderIt();
    fireEvent.mouseDown(await screen.findByRole("tab", { name: /Allocations/i }));
    expect(await screen.findByText("$120 held until they verify")).toBeInTheDocument();
  });
});
