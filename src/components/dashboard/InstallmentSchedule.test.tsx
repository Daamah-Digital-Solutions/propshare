/**
 * Group 6: the dashboard installment schedule is wired to the real API. The prior "coming
 * soon" placeholder is gone — it renders real plans + payment statuses from installmentsApi
 * (no fabricated schedule), and an honest empty state when there are none.
 */
import { render, screen, waitFor } from "@testing-library/react";
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
    },
  };
});

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
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

  it("renders a real plan with its payment schedule", async () => {
    listMock.mockResolvedValue([
      {
        id: "pl1",
        property_id: "p1",
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
      },
    ]);
    wrap(<InstallmentSchedule />);
    // real plan summary + a payable installment (Pay now) render from the API
    expect(await screen.findByText(/Vesting \(3\/12 units\)/)).toBeInTheDocument();
    expect(screen.getByText("Down payment")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pay now/i })).toBeInTheDocument();
    await waitFor(() => expect(listMock).toHaveBeenCalled());
  });
});
