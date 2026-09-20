/**
 * Tickets pages — the list renders the member's tickets from the API with status badges and
 * links; the detail page shows the thread, sends a reply through the API, and offers the
 * CSAT stars only once the ticket is resolved.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import MyTickets from "./MyTickets";
import TicketDetail from "./TicketDetail";

const api = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), reply: vi.fn(), rate: vi.fn() }));
vi.mock("@/lib/assistantApi", () => ({ ticketsApi: api }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

const ticket = (over: Record<string, unknown> = {}) => ({
  id: "t1",
  ticket_no: "CPX-001001",
  category: "payments",
  priority: "normal",
  status: "waiting_user",
  subject: "Missing deposit",
  source: "form",
  created_at: "2026-09-20T10:00:00Z",
  updated_at: "2026-09-20T10:00:00Z",
  resolved_at: null,
  csat: null,
  messages: [
    { id: "m1", author_type: "user", body: "My deposit is missing", created_at: "2026-09-20T10:00:00Z" },
    { id: "m2", author_type: "staff", body: "We are on it", created_at: "2026-09-20T11:00:00Z" },
  ],
  ...over,
});

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/support/tickets" element={<MyTickets />} />
          <Route path="/support/tickets/:id" element={<TicketDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("tickets pages", () => {
  beforeEach(() => Object.values(api).forEach((m) => m.mockReset()));

  it("lists tickets with status and links to the detail", async () => {
    api.list.mockResolvedValue([ticket(), ticket({ id: "t2", ticket_no: "CPX-001002", status: "resolved", subject: "KYC" })]);
    renderAt("/support/tickets");
    await waitFor(() => expect(screen.getByText("Missing deposit")).toBeInTheDocument());
    expect(screen.getByText("Waiting for you")).toBeInTheDocument();
    expect(screen.getByText("Resolved")).toBeInTheDocument();
    expect(screen.getByText("Missing deposit").closest("a")).toHaveAttribute("href", "/support/tickets/t1");
  });

  it("shows the thread, sends a reply, and rates once resolved", async () => {
    api.get.mockResolvedValue(ticket());
    api.reply.mockResolvedValue(ticket({ status: "open", messages: [...ticket().messages, { id: "m3", author_type: "user", body: "Still waiting", created_at: "t" }] }));
    renderAt("/support/tickets/t1");
    await waitFor(() => expect(screen.getByText("We are on it")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /rate 5/i })).toBeNull(); // not resolved yet
    fireEvent.change(screen.getByPlaceholderText(/write a reply/i), { target: { value: "Still waiting" } });
    fireEvent.click(screen.getByRole("button", { name: /send reply/i }));
    await waitFor(() => expect(api.reply).toHaveBeenCalledWith("t1", "Still waiting"));
    await waitFor(() => expect(screen.getByText("Still waiting")).toBeInTheDocument());

    api.get.mockResolvedValue(ticket({ status: "resolved", resolved_at: "t" }));
    api.rate.mockResolvedValue(ticket({ status: "resolved", resolved_at: "t", csat: 4 }));
    renderAt("/support/tickets/t1");
    await waitFor(() => expect(screen.getAllByRole("button", { name: /rate 4/i }).length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole("button", { name: /rate 4/i })[0]);
    await waitFor(() => expect(api.rate).toHaveBeenCalledWith("t1", 4));
    await waitFor(() => expect(screen.getByText(/your rating/i)).toBeInTheDocument());
  });
});
