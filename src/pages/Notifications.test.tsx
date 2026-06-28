/**
 * Guards the Phase 12 notifications read path at the component level: the page renders
 * the live feed from notificationApi and "mark all read" calls the real API.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Notifications from "./Notifications";

const listMock = vi.fn();
const markReadMock = vi.fn();
const markAllMock = vi.fn();

vi.mock("@/lib/api", () => ({
  notificationApi: {
    list: (...a: unknown[]) => listMock(...a),
    markRead: (...a: unknown[]) => markReadMock(...a),
    markAllRead: (...a: unknown[]) => markAllMock(...a),
  },
}));

function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Notifications />
    </QueryClientProvider>,
  );
}

describe("Notifications page", () => {
  beforeEach(() => {
    listMock.mockReset();
    markAllMock.mockReset();
    markAllMock.mockResolvedValue({ marked: 1 });
  });

  it("renders the live feed and unread count", async () => {
    listMock.mockResolvedValue({
      items: [
        { id: "n1", type: "return", title: "Return distributed", message: "You got paid", read: false, created_at: "2026-01-01T00:00:00Z" },
        { id: "n2", type: "kyc", title: "Identity verified", message: "All set", read: true, created_at: "2026-01-02T00:00:00Z" },
      ],
      total: 2,
      unread_count: 1,
    });
    renderIt();
    expect(await screen.findByText("Return distributed")).toBeInTheDocument();
    expect(screen.getByText("Identity verified")).toBeInTheDocument();
    expect(screen.getByText(/1 unread/)).toBeInTheDocument();
  });

  it("calls the API when marking all read", async () => {
    listMock.mockResolvedValue({
      items: [
        { id: "n1", type: "info", title: "Hi", message: "m", read: false, created_at: "2026-01-01T00:00:00Z" },
      ],
      total: 1,
      unread_count: 1,
    });
    renderIt();
    const btn = await screen.findByRole("button", { name: /Mark all read/i });
    fireEvent.click(btn);
    await waitFor(() => expect(markAllMock).toHaveBeenCalledTimes(1));
  });
});
