/**
 * Guards the Phase 11 broker wiring at the component level: the dashboard reads the
 * real broker API (the "Premium Realty Partners" / "Ahmed Al-Farsi" / "$125,000" mock
 * arrays are retired), the referral link comes from the API, and Virtual Cards degrade
 * to an honest disabled state (D9 — never a fake issuance).
 */
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import BrokerDashboard from "./BrokerDashboard";
import { VirtualCardRequest } from "@/components/dashboard/VirtualCardRequest";

const dashboardMock = vi.fn();
const codeMock = vi.fn();
const referralsMock = vi.fn();
const commissionsMock = vi.fn();
const leadsMock = vi.fn();
const inviteMock = vi.fn();
const introduceMock = vi.fn();
const cancelMock = vi.fn();

vi.mock("@/lib/api", () => ({
  ApiError: class extends Error {},
  brokerApi: {
    dashboard: (...a: unknown[]) => dashboardMock(...a),
    referralCode: (...a: unknown[]) => codeMock(...a),
    referrals: (...a: unknown[]) => referralsMock(...a),
    commissions: (...a: unknown[]) => commissionsMock(...a),
    leads: (...a: unknown[]) => leadsMock(...a),
    inviteClient: (...a: unknown[]) => inviteMock(...a),
    introduceListing: (...a: unknown[]) => introduceMock(...a),
    cancelLead: (...a: unknown[]) => cancelMock(...a),
  },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// The Wallet tab embeds the live InvestorWallet (its own API surface) — stub it.
vi.mock("@/components/dashboard/InvestorWallet", () => ({
  InvestorWallet: () => <div>wallet</div>,
}));

function renderIt(url = "/broker-dashboard") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <BrokerDashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BrokerDashboard", () => {
  beforeEach(() => {
    dashboardMock.mockResolvedValue({
      commission_rate: "10.0",
      total_referrals: 2,
      total_commission: "42.50",
    });
    codeMock.mockResolvedValue({ code: "ABCD2345", share_link: "http://x/auth?ref=ABCD2345" });
    referralsMock.mockResolvedValue({ items: [], total: 0 });
    commissionsMock.mockResolvedValue({ items: [], total: 0 });
    leadsMock.mockResolvedValue({ items: [], total: 0 });
  });

  it("renders live broker data and retires the mock arrays", async () => {
    renderIt();
    // referral link from the API
    expect(await screen.findByText("http://x/auth?ref=ABCD2345")).toBeInTheDocument();
    // live commission rate is shown
    expect(await screen.findAllByText(/10\.0%/)).not.toHaveLength(0);
    // the old fabricated mock content is gone
    expect(screen.queryByText(/Premium Realty Partners/)).toBeNull();
    expect(screen.queryByText(/Ahmed Al-Farsi/)).toBeNull();
    expect(screen.queryByText(/\$125,000/)).toBeNull();
  });
});

describe("VirtualCardRequest (D9 honest-disabled)", () => {
  it("shows a not-yet-available state and disables the request button", () => {
    render(<VirtualCardRequest role="broker" />);
    expect(screen.getByText(/not yet available/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Request Virtual Card/i })).toBeDisabled();
    // no fake card numbers are rendered
    expect(screen.queryByText(/••••/)).toBeNull();
  });
});

describe("BrokerDashboard — Listings & Referrals (client feedback #2)", () => {
  const lead = (over: Record<string, unknown>) => ({
    id: "l1",
    kind: "client",
    status: "invited",
    name: "Omar Client",
    email: "omar@client.io",
    phone: "+97150",
    details: {},
    documents: [],
    admin_note: null,
    property_id: null,
    created_at: "2026-09-26T10:00:00Z",
    updated_at: null,
    ...over,
  });

  beforeEach(() => {
    dashboardMock.mockResolvedValue({ commission_rate: "10.0", total_referrals: 1, total_commission: "5.00" });
    codeMock.mockResolvedValue({ code: "ABCD2345", share_link: "http://x/auth?ref=ABCD2345" });
    commissionsMock.mockResolvedValue({ items: [], total: 0 });
    referralsMock.mockResolvedValue({
      items: [{ referral_id: "r1", client_masked: "s***@mail.io", created_at: "2026-09-20T10:00:00Z", commission_to_date: "5.00" }],
      total: 1,
    });
    leadsMock.mockResolvedValue({
      items: [
        lead({}),
        lead({
          id: "l2",
          kind: "property",
          status: "contacted",
          name: "Palm Villa 12",
          email: "khaled@owner.io",
          details: { owner_name: "Khaled Owner", location: "Palm Jumeirah" },
          documents: ["deed.pdf"],
          admin_note: "Called the owner.",
        }),
        lead({ id: "l3", kind: "project", status: "new", name: "Creek Rise", details: { owner_name: "Dev Co", location: "Creek" } }),
      ],
      total: 3,
    });
    inviteMock.mockReset();
    introduceMock.mockReset();
    cancelMock.mockReset();
  });

  it("shows one table of clients, properties and projects with their status", async () => {
    renderIt("/broker-dashboard?tab=referrals");
    const table = await screen.findByTestId("listings-referrals-table");
    await waitFor(() => expect(table).toHaveTextContent("Palm Villa 12"));
    for (const text of ["s***@mail.io", "Linked to you", "Omar Client", "Invited", "Owner contacted", "Called the owner.", "Creek Rise", "Project"]) {
      expect(table).toHaveTextContent(text);
    }
    expect(screen.getByRole("tab", { name: /Listings & Referrals/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add client/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add property/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add project/ })).toBeInTheDocument();
  });

  it("invites a client from the dialog", async () => {
    inviteMock.mockResolvedValue(lead({ id: "l9", name: "New Person" }));
    renderIt("/broker-dashboard?tab=referrals");
    fireEvent.click(await screen.findByRole("button", { name: /Add client/ }));
    fireEvent.change(await screen.findByLabelText(/Full name/), { target: { value: "New Person" } });
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: "new@person.io" } });
    fireEvent.click(screen.getByRole("button", { name: /Send invitation/ }));
    await waitFor(() =>
      expect(inviteMock).toHaveBeenCalledWith({ name: "New Person", email: "new@person.io", phone: undefined, notes: undefined }),
    );
  });

  it("introduces a project with the developer contact", async () => {
    introduceMock.mockResolvedValue(lead({ id: "l8", kind: "project", status: "new" }));
    renderIt("/broker-dashboard?tab=referrals");
    fireEvent.click(await screen.findByRole("button", { name: /Add project/ }));
    fireEvent.change(await screen.findByLabelText(/Project name/), { target: { value: "Harbour Gate" } });
    fireEvent.change(screen.getByLabelText(/Location/), { target: { value: "Dubai Creek" } });
    fireEvent.change(screen.getByLabelText(/Developer name/), { target: { value: "Gate Dev" } });
    fireEvent.click(screen.getByRole("button", { name: /Send to our team/ }));
    await waitFor(() => expect(introduceMock).toHaveBeenCalled());
    const [kind, fields] = introduceMock.mock.calls[0];
    expect(kind).toBe("project");
    expect(fields).toMatchObject({ title: "Harbour Gate", location: "Dubai Creek", owner_name: "Gate Dev" });
  });

  it("withdraws an introduction our team has not picked up yet", async () => {
    cancelMock.mockResolvedValue(lead({ id: "l3", kind: "project", status: "withdrawn" }));
    renderIt("/broker-dashboard?tab=referrals");
    await screen.findByText("Creek Rise");
    const buttons = screen.getAllByRole("button", { name: /Withdraw/ });
    // the invited client and the new project can be withdrawn; the contacted property cannot
    expect(buttons).toHaveLength(2);
    fireEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(cancelMock).toHaveBeenCalled());
  });
});
