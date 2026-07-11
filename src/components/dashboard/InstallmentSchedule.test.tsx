/**
 * Group 6 / Task 6: the dashboard installment schedule is wired to the real API and presented
 * PER PROPERTY. It renders real plans + payment statuses from installmentsApi (no fabricated
 * schedule), shows which property each plan is for, reveals the full payment table behind a
 * "View schedule" toggle, and shows an honest empty state when there are none.
 */
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
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

  it("renders a real plan per-property, revealing the schedule on View", async () => {
    listMock.mockResolvedValue([
      {
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
      },
    ]);
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
});
