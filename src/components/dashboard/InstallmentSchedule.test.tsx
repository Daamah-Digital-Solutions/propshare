/**
 * Group 6 / Task 6: the dashboard installment schedule is wired to the real API and presented
 * PER PROPERTY. It renders real plans + payment statuses from installmentsApi (no fabricated
 * schedule), shows which property each plan is for, reveals the full payment table behind a
 * "View schedule" toggle, and shows an honest empty state when there are none.
 */
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { InstallmentSchedule } from "./InstallmentSchedule";

const listMock = vi.fn();
const payMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    installmentsApi: {
      list: (...a: unknown[]) => listMock(...a),
      createPlan: vi.fn(),
      pay: (...a: unknown[]) => payMock(...a),
      downloadSchedule: vi.fn(),
    },
    walletApi: {
      ...actual.walletApi,
      getMe: async () => ({ balance: "500.00", pending_balance: "0.00", currency: "USD" }),
    },
  };
});

function Url() {
  const l = useLocation();
  return <div data-testid="url">{l.pathname + l.search}</div>;
}

// the schedule reads a payment the assistant prepared (?pay=<id>), so it needs a router
function wrap(node: React.ReactNode, url = "/dashboard?tab=installments") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        {node}
        <Url />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("InstallmentSchedule (real API)", () => {
  beforeEach(() => {
    listMock.mockReset();
    payMock.mockReset();
  });

  it("shows an honest empty state when there are no plans", async () => {
    listMock.mockResolvedValue([]);
    wrap(<InstallmentSchedule />);
    expect(await screen.findByText("No installment plans yet")).toBeInTheDocument();
    await waitFor(() => expect(listMock).toHaveBeenCalled());
  });

  it("renders a real plan per-property, revealing the schedule on View", async () => {
    listMock.mockResolvedValue([PLAN]);
    wrap(<InstallmentSchedule />);
    // The property under installment is shown, with a live summary (Task 6).
    expect(await screen.findByText("Downtown Tower")).toBeInTheDocument();
    expect(screen.getByText("Dubai, UAE")).toBeInTheDocument();
    expect(screen.getByText("Contract value")).toBeInTheDocument();

    // The full schedule is behind a "View schedule" toggle — hidden until requested.
    expect(screen.queryByText("Down payment")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /View schedule/i }));

    expect(await screen.findByText("Down payment")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pay now/i })).toBeInTheDocument();
    await waitFor(() => expect(listMock).toHaveBeenCalled());
  });

  it("opens the payment the assistant prepared and charges only on the user's Pay click", async () => {
    listMock.mockResolvedValue([PLAN]);
    payMock.mockResolvedValue(PLAN);
    wrap(<InstallmentSchedule />, "/dashboard?tab=installments&pay=pay1");
    expect(await screen.findByTestId("assistant-installment-banner")).toHaveTextContent(
      /nothing is charged until you press pay/i,
    );
    expect(screen.getByText(/installment \(Month 1\)/)).toBeInTheDocument();
    expect(payMock).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId("url").textContent).toBe("/dashboard?tab=installments"));
    // the button names the exact charge, cents included ($85.09, not a rounded $85)
    fireEvent.click(await screen.findByRole("button", { name: /Pay \$85\.09 from wallet/i }));
    await waitFor(() => expect(payMock).toHaveBeenCalledWith("pay1"));
  });

  it("never opens a payment that is not payable (the down payment, or unknown ids)", async () => {
    listMock.mockResolvedValue([PLAN]);
    wrap(<InstallmentSchedule />, "/dashboard?tab=installments&pay=pay0");
    expect(await screen.findByText("Downtown Tower")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("url").textContent).toBe("/dashboard?tab=installments"));
    expect(screen.queryByTestId("assistant-installment-banner")).toBeNull();
  });
});

describe("InstallmentSchedule: a running plan is a position with a value", () => {
  beforeEach(() => listMock.mockReset());

  // 12 units locked at $100, $300 of principal paid; the unit price is now $110:
  // 12 x 110 = 1,320, less the 900 still to pay = 420 (the 300 paid + 120 on all 12 units)
  const POSITION = {
    price: "110.00",
    entry_price: "100.00",
    value: "1320.00",
    cost: "300.00",
    paid_principal: "300.00",
    remaining_principal: "900.00",
    remaining_fees: "36.00",
    equity: "420.00",
    gain: "120.00",
    installments_left: 11,
    overdue: 0,
    next_due: "2026-07-01",
  };

  it("values the plan at the unit price of the day and offers to sell it whole", async () => {
    listMock.mockResolvedValue([{ ...PLAN, position: POSITION }]);
    wrap(<InstallmentSchedule />);
    const block = await screen.findByTestId("plan-position");
    expect(block).toHaveTextContent("Unit price now$110you locked $100");
    expect(block).toHaveTextContent("Position value now$1,32012 units");
    expect(block).toHaveTextContent("Your part of it$420$300 you put in + $120");
    expect(block).toHaveTextContent("+$120 since you started, on all 12 units.");
    expect(within(block).getByRole("link", { name: /sell this position/i })).toHaveAttribute(
      "href",
      "/secondary-market?tab=sell&plan=pl1",
    );
    // the old rule ("held until the plan completes") is gone
    expect(document.body.textContent).not.toMatch(/held until the plan completes/i);
  });

  it("says when the price fell, and when the position is already for sale", async () => {
    listMock.mockResolvedValue([
      {
        ...PLAN,
        listing_id: "lst-1",
        position: { ...POSITION, price: "95.00", value: "1140.00", equity: "240.00", gain: "-60.00" },
      },
    ]);
    wrap(<InstallmentSchedule />);
    const block = await screen.findByTestId("plan-position");
    expect(block).toHaveTextContent("−$60 since you started, on all 12 units.");
    expect(within(block).getByRole("link", { name: /listed for sale/i })).toHaveAttribute(
      "href",
      "/secondary-market?tab=activity",
    );
    expect(within(block).queryByRole("link", { name: /sell this position/i })).toBeNull();
    // listed is not "you can list": it says what happens until it sells
    const note = within(block).getByTestId("plan-position-note");
    expect(note).toHaveTextContent(/This position is listed for sale\. Until it sells, its installments are still charged/);
    expect(note).not.toHaveTextContent(/You can list the whole position/);
  });

  it("measures a plan that was bought from what its buyer paid, not from the first holder's price", async () => {
    // bought at $110 a unit for $420 (the first holder's $120 gain was paid for): no gain yet
    listMock.mockResolvedValue([
      {
        ...PLAN,
        acquired_at: "2026-09-20T10:00:00Z",
        position: { ...POSITION, entry_price: "110.00", cost: "420.00", gain: "0.00" },
      },
    ]);
    wrap(<InstallmentSchedule />);
    const block = await screen.findByTestId("plan-position");
    expect(block).toHaveTextContent("Unit price now$110you bought at $110");
    expect(block).toHaveTextContent("Your part of it$420$420 you put in + $0");
    expect(block).toHaveTextContent("The unit price has not changed since you bought this position.");
    expect(block).not.toHaveTextContent(/you locked|since you started/);
    expect(block).toHaveTextContent(
      /You took this plan over on Sep 20, 2026; payments before that were made by the previous holder/,
    );
  });

  it("says why a position cannot be sold instead of offering the button", async () => {
    listMock.mockResolvedValue([
      { ...PLAN, id: "a", position: { ...POSITION, blocked: "pledged" } },
      {
        ...PLAN,
        id: "b",
        position: { ...POSITION, blocked: "lockup", lockup_until: "2026-12-15T10:00:00Z" },
      },
      // worth less than what is still to pay: nothing to sell, and nothing owed for it
      { ...PLAN, id: "c", position: { ...POSITION, price: "70.00", value: "840.00", equity: "-60.00", gain: "-360.00" } },
    ]);
    wrap(<InstallmentSchedule />);
    const notes = await screen.findAllByTestId("plan-position-note");
    expect(notes[0]).toHaveTextContent(/pledged to Nova Finance, so the position cannot be sold/);
    expect(notes[1]).toHaveTextContent(/lock-up until Dec 1[45], 2026/);
    expect(notes[2]).toHaveTextContent(/worth less than what is still to pay on it/);
    const blocks = screen.getAllByTestId("plan-position");
    expect(within(blocks[0]).queryByRole("link", { name: /sell this position/i })).toBeNull();
    expect(within(blocks[1]).queryByRole("link", { name: /sell this position/i })).toBeNull();
    expect(within(blocks[2]).queryByRole("link", { name: /sell this position/i })).toBeNull();
    // never a negative "your part"
    expect(blocks[2]).toHaveTextContent("Your part of it$0");
  });

  it("shows no position on a plan that is not running", async () => {
    listMock.mockResolvedValue([{ ...PLAN, status: "completed", position: null }]);
    wrap(<InstallmentSchedule />);
    expect(await screen.findByText("Downtown Tower")).toBeInTheDocument();
    expect(screen.queryByTestId("plan-position")).toBeNull();
  });
});

describe("InstallmentSchedule — a plan that has not started yet", () => {
  beforeEach(() => listMock.mockReset());

  it("waits for its down payment and links back to the open checkout", async () => {
    listMock.mockResolvedValue([
      {
        ...PLAN,
        status: "pending_payment",
        payment_method: "card",
        vested_units: 0,
        checkout_url: "https://checkout.stripe.test/pay",
      },
    ]);
    wrap(<InstallmentSchedule />);
    expect(await screen.findByText("Waiting for the down payment")).toBeInTheDocument();
    expect(screen.getByTestId("plan-state")).toHaveTextContent(/units are held for you/i);
    expect(screen.getByRole("link", { name: /Complete the payment/i })).toHaveAttribute(
      "href",
      "https://checkout.stripe.test/pay",
    );
  });

  it("says a Nova certificate is under review, and why a rejected one did not start", async () => {
    listMock.mockResolvedValue([
      { ...PLAN, id: "a", status: "pending_review", payment_method: "sukuk", vested_units: 0 },
      {
        ...PLAN,
        id: "b",
        status: "cancelled",
        payment_method: "sukuk",
        vested_units: 0,
        failure_reason: "sukuk_rejected",
      },
    ]);
    wrap(<InstallmentSchedule />);
    expect(await screen.findByText("Nova certificate under review")).toBeInTheDocument();
    expect(screen.getByText("Not started")).toBeInTheDocument();
    expect(screen.getByText(/certificate was not accepted/i)).toBeInTheDocument();
  });

  it("offers no Pay now on a plan that has not started", async () => {
    listMock.mockResolvedValue([
      { ...PLAN, status: "pending_review", payment_method: "sukuk", vested_units: 0 },
    ]);
    wrap(<InstallmentSchedule />);
    fireEvent.click(await screen.findByRole("button", { name: /View schedule/i }));
    expect(await screen.findByText("Down payment")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Pay now/i })).toBeNull();
  });

  it("says a late payment was refunded when the units were taken meanwhile", async () => {
    listMock.mockResolvedValue([
      {
        ...PLAN,
        status: "expired",
        payment_method: "card",
        vested_units: 0,
        failure_reason: "units_unavailable_refunded",
      },
    ]);
    wrap(<InstallmentSchedule />);
    expect(await screen.findByText(/payment was refunded to your wallet/i)).toBeInTheDocument();
  });
});

const PLAN = {
  id: "pl1",
  property_id: "p1",
  property_title: "Downtown Tower",
  property_slug: "downtown-tower",
  property_location: "Dubai, UAE",
  property_city: "Dubai",
  property_image: null,
  property_spv: "Downtown Tower SPV",
  units_total: 12,
  unit_price: "100.00",
  down_payment_pct: 25,
  duration_months: 12,
  fee_rate: "4.000",
  vested_units: 3,
  status: "active",
  created_at: "2026-06-01T00:00:00Z",
  completed_at: null,
  payments: [
    {
      id: "pay0",
      seq: 0,
      kind: "downpayment",
      due_date: "2026-06-01",
      base_amount: "300.00",
      fee_amount: "12.00",
      total_amount: "312.00",
      vest_units: 3,
      status: "paid",
      paid_at: "2026-06-01T00:00:00Z",
    },
    {
      id: "pay1",
      seq: 1,
      kind: "installment",
      due_date: "2026-07-01",
      base_amount: "81.82",
      fee_amount: "3.27",
      total_amount: "85.09",
      vest_units: 1,
      status: "scheduled",
      paid_at: null,
    },
  ],
};
