/**
 * Phase 15c: Investor Communications is a real surface — a per-property composer that
 * sends to net-holders, plus a sent-history showing REAL counts (recipients + in-app
 * reads). No fabricated open/click/delivered metric. The old "coming soon" stub is gone.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { InvestorCommunications } from "./InvestorCommunications";

const listMock = vi.fn();
const sendMock = vi.fn();

vi.mock("@/lib/api", () => ({
  ownerUpdatesApi: {
    list: (...a: unknown[]) => listMock(...a),
    send: (...a: unknown[]) => sendMock(...a),
  },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

const PROJECTS = [
  { id: "p1", name: "Marina Loft" },
  { id: "p2", name: "Business Bay" },
];

describe("InvestorCommunications (Phase 15c)", () => {
  beforeEach(() => {
    listMock.mockReset();
    sendMock.mockReset();
  });

  it("renders the sent history with real recipient + read counts (no open-rate)", async () => {
    listMock.mockResolvedValue([
      {
        id: "u1",
        property_id: "p1",
        subject: "Q2 progress",
        body: "Foundation poured.",
        recipient_count: 12,
        read_count: 5,
        created_at: "2026-06-20T00:00:00Z",
      },
    ]);
    wrap(<InvestorCommunications projects={PROJECTS} />);
    expect(await screen.findByText("Q2 progress")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument(); // recipients (real)
    expect(screen.getByText("5")).toBeInTheDocument(); // in-app reads (real)
    expect(screen.queryByText(/open rate/i)).toBeNull(); // no fabricated email metric
    expect(screen.queryByText(/coming soon/i)).toBeNull();
  });

  it("sends a real update via ownerUpdatesApi.send", async () => {
    listMock.mockResolvedValue([]);
    sendMock.mockResolvedValue({
      id: "u2",
      property_id: "p1",
      subject: "Hello",
      body: "World today",
      recipient_count: 3,
      read_count: 0,
      created_at: "2026-06-24T00:00:00Z",
    });
    wrap(<InvestorCommunications projects={PROJECTS} />);

    fireEvent.click(await screen.findByRole("button", { name: "Send Update" })); // header opens dialog
    fireEvent.change(screen.getByLabelText("Subject"), { target: { value: "Hello" } });
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "World today" } });
    fireEvent.click(screen.getByRole("button", { name: "Send update" })); // dialog footer

    await waitFor(() => expect(sendMock).toHaveBeenCalledTimes(1));
    expect(sendMock).toHaveBeenCalledWith("p1", { subject: "Hello", body: "World today" });
  });
});
