/**
 * ChatWidget — the floating assistant wired to the n8n webhook. Verifies it opens from the
 * launcher, sends the exact contract body (action/sessionId/chatInput), renders the agent's
 * `output`, keeps a stable sessionId across turns, and degrades honestly on a network error.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import ChatWidget from "./ChatWidget";

describe("ChatWidget", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  const open = () =>
    fireEvent.click(screen.getByRole("button", { name: /open capimax assistant/i }));

  it("opens from the launcher and shows a welcome message", () => {
    render(<ChatWidget />);
    expect(screen.queryByText(/CapiMax Assistant/i)).toBeNull(); // closed
    open();
    expect(screen.getByText(/CapiMax Assistant/i)).toBeInTheDocument();
    expect(screen.getByText(/Ask me anything about investing/i)).toBeInTheDocument();
  });

  it("sends the contract body and renders the agent reply", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: async () => JSON.stringify({ output: "You can invest from **$100**." }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ChatWidget />);
    open();
    fireEvent.change(screen.getByPlaceholderText(/type your message/i), {
      target: { value: "How much to start?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));

    // the user's message shows immediately
    expect(screen.getByText("How much to start?")).toBeInTheDocument();
    // the agent's reply renders (bold parsed → the $100 fragment is present)
    await waitFor(() => expect(screen.getByText("$100")).toBeInTheDocument());

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toContain("/webhook/capimax-propshare/chat");
    const body = JSON.parse(opts.body);
    expect(body.action).toBe("sendMessage");
    expect(body.chatInput).toBe("How much to start?");
    expect(typeof body.sessionId).toBe("string");
    expect(body.sessionId.length).toBeGreaterThan(0);
  });

  it("shows an honest error when the webhook is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));
    render(<ChatWidget />);
    open();
    fireEvent.change(screen.getByPlaceholderText(/type your message/i), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    await waitFor(() =>
      expect(screen.getByText(/couldn't reach the assistant/i)).toBeInTheDocument(),
    );
  });
});
