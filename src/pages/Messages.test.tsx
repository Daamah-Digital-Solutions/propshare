/**
 * Messages: the inbox of what the Capimax PropShare team writes from the admin panel
 * (client, 2026-10-28). Opening one reads it (the server marks it read); a link from the
 * notification or the email opens it directly (/messages?id=...).
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { list, get, readAll } = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  readAll: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  messagesApi: { list: () => list(), get: (id: string) => get(id), readAll: () => readAll() },
  ApiError: class ApiError extends Error {
    code: string;
    status: number;
    constructor(code: string, message: string, status: number) {
      super(message);
      this.code = code;
      this.status = status;
    }
  },
}));

import Messages from "./Messages";
import { ApiError } from "@/lib/api";

const M1 = {
  id: "m1",
  subject: "New tiers open Monday",
  preview: "The pool opens two new tiers…",
  read: false,
  created_at: "2026-10-28T09:00:00Z",
};
const M2 = { ...M1, id: "m2", subject: "Welcome", preview: "Hello", read: true };

function Where() {
  const loc = useLocation();
  return <p data-testid="where">{loc.pathname + loc.search}</p>;
}

function mount(path = "/messages") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/messages"
            element={
              <>
                <Messages />
                <Where />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Messages", () => {
  beforeEach(() => {
    list.mockReset();
    get.mockReset();
    readAll.mockReset();
  });

  it("lists the messages, unread first marked, and opens one", async () => {
    list.mockResolvedValueOnce({ items: [M1, M2], unread: 1 });
    list.mockResolvedValue({ items: [{ ...M1, read: true }, M2], unread: 0 });
    get.mockResolvedValue({ ...M1, read: true, body: "The pool opens\ntwo new tiers." });
    mount();
    const listEl = await screen.findByTestId("message-list");
    expect(screen.getByTestId("unread-count")).toHaveTextContent("1 unread");
    expect(within(listEl).getAllByRole("button").map((b) => b.textContent)).toEqual([
      expect.stringContaining("New tiers open Monday"),
      expect.stringContaining("Welcome"),
    ]);
    expect(within(listEl).getAllByLabelText("Unread")).toHaveLength(1);

    fireEvent.click(within(listEl).getByText("New tiers open Monday"));
    const view = screen.getByTestId("message-view");
    await waitFor(() => expect(view).toHaveTextContent("The pool opens two new tiers."));
    expect(get).toHaveBeenCalledWith("m1");
    expect(view).toHaveTextContent("From the Capimax PropShare team");
    expect(screen.getByTestId("where")).toHaveTextContent("/messages?id=m1");
    // the list is read again: the message reads as read, the badge is gone
    await waitFor(() => expect(screen.queryByTestId("unread-count")).toBeNull());
  });

  it("opens the message a notification or an email links to", async () => {
    list.mockResolvedValue({ items: [M1], unread: 1 });
    get.mockResolvedValue({ ...M1, body: "Body text" });
    mount("/messages?id=m1");
    await waitFor(() => expect(screen.getByTestId("message-view")).toHaveTextContent("Body text"));
    expect(get).toHaveBeenCalledWith("m1");
  });

  it("a message that is not theirs says so", async () => {
    list.mockResolvedValue({ items: [], unread: 0 });
    get.mockRejectedValue(new ApiError("MESSAGE_NOT_FOUND", "Message not found.", 404));
    mount("/messages?id=someone-elses");
    expect(await screen.findByText("This message is not in your inbox.")).toBeInTheDocument();
  });

  it("marks all read, and shows an empty inbox honestly", async () => {
    list.mockResolvedValueOnce({ items: [M1], unread: 1 });
    list.mockResolvedValue({ items: [], unread: 0 });
    readAll.mockResolvedValue({ marked: 1 });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /mark all read/i }));
    await waitFor(() => expect(readAll).toHaveBeenCalled());
    expect(await screen.findByText("No messages yet")).toBeInTheDocument();
  });
});
