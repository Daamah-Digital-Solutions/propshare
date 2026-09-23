/**
 * AssistantWidget — consent gate for signed-in users, streamed answer + server cards, the
 * confirm card calls the confirm endpoint with the token (never shown to the model), and a
 * 'reset' event withdraws already-streamed text.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import AssistantWidget from "./AssistantWidget";
import type { AssistantStatus } from "@/lib/assistantApi";

// vi.mock factories are hoisted: everything they touch must be hoisted too.
const { authState, api, stream } = vi.hoisted(() => ({
  authState: { isAuthenticated: true, user: { id: "u1" }, isLoading: false },
  api: {
    status: vi.fn(),
    consent: vi.fn(),
    createConversation: vi.fn(),
    messages: vi.fn(),
    confirm: vi.fn(),
    cancel: vi.fn(),
    feedback: vi.fn(),
  },
  stream: { events: [] as unknown[] },
}));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => authState }));
vi.mock("@/lib/assistantApi", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    assistantApi: api,
    sendMessage: async function* () {
      for (const ev of stream.events) yield ev;
    },
  };
});

const enabled: AssistantStatus = {
  enabled: true,
  reason: null,
  provider: "openai",
  model_configured: true,
  encryption: "ok",
  policy_version: "2026-10",
  consent_required: false,
  consent_given: true,
  visitor_allowed: false,
  rollout: "all",
};

function renderIt(status: AssistantStatus) {
  return render(
    <MemoryRouter>
      <AssistantWidget status={status} />
    </MemoryRouter>,
  );
}
const open = () => fireEvent.click(screen.getByRole("button", { name: /open capimax assistant/i }));

describe("AssistantWidget", () => {
  beforeEach(() => {
    localStorage.clear();
    Object.values(api).forEach((m) => m.mockReset());
    api.createConversation.mockResolvedValue({ id: "conv-1" });
    api.messages.mockResolvedValue([]);
    api.feedback.mockResolvedValue(null);
    stream.events = [];
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows the consent gate first and enables the composer after consent", async () => {
    const gated = { ...enabled, enabled: false, reason: "CONSENT_REQUIRED", consent_required: true, consent_given: false };
    api.status.mockResolvedValueOnce(gated).mockResolvedValue(enabled);
    api.consent.mockResolvedValue({ policy_version: "2026-10", accepted_at: "now" });
    renderIt(gated);
    open();
    await waitFor(() => expect(screen.getByTestId("consent-gate")).toBeInTheDocument());
    expect(screen.getByText(/2026-10/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/type your message/i)).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /i agree, continue/i }));
    await waitFor(() => expect(api.consent).toHaveBeenCalledWith("2026-10"));
    await waitFor(() => expect(screen.queryByTestId("consent-gate")).toBeNull());
    expect(screen.getByPlaceholderText(/type your message/i)).not.toBeDisabled();
  });

  it("streams the answer, renders server cards, and confirms an action with the token", async () => {
    api.status.mockResolvedValue(enabled);
    api.confirm.mockResolvedValue({ id: "p1", action: "create_support_ticket", status: "executed", summary: "x", result: { ticket_no: "CPX-001001" }, decided_at: "now" });
    stream.events = [
      { event: "started", data: { conversation_id: "conv-1", user_message_id: "um" } },
      { event: "tool", data: { name: "get_my_wallet", status: "running" } },
      { event: "tool", data: { name: "get_my_wallet", status: "ok" } },
      { event: "delta", data: { text: "Your balance is " } },
      { event: "delta", data: { text: "$5,000.00." } },
      { event: "card", data: { kind: "link", path: "/wallet", label: "Open your wallet" } },
      { event: "card", data: { kind: "confirm_action", proposal_id: "p1", action: "create_support_ticket", summary: "Open a high priority support ticket about payments.", token: "tok-secret", expires_at: "later" } },
      { event: "done", data: { message_id: "m1", confidence: "normal", flags: [], usage: {}, latency_ms: 10, first_token_ms: 2, safe_mode: null } },
    ];
    renderIt(enabled);
    open();
    await waitFor(() => expect(screen.getByText(/What do you need/)).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/type your message/i), { target: { value: "balance?" } });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    await waitFor(() => expect(screen.getByText(/\$5,000\.00/)).toBeInTheDocument());
    expect(api.createConversation).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem("capimax_assistant_conversation:u1")).toBe("conv-1");
    expect(screen.getByText("get my wallet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open your wallet/i })).toHaveAttribute("href", "/wallet");
    expect(screen.getByTestId("confirm-card")).toBeInTheDocument();
    expect(screen.queryByText("tok-secret")).toBeNull(); // the token is never rendered
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));
    await waitFor(() => expect(api.confirm).toHaveBeenCalledWith("p1", "tok-secret"));
    await waitFor(() => expect(screen.getByText(/ticket CPX-001001 opened/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^helpful$/i }));
    await waitFor(() => expect(api.feedback).toHaveBeenCalledWith("m1", "up"));
  });

  it("withdraws streamed text on reset and shows the safe-mode marker", async () => {
    api.status.mockResolvedValue(enabled);
    stream.events = [
      { event: "started", data: { conversation_id: "conv-1", user_message_id: "um" } },
      { event: "delta", data: { text: "The fee is 2" } },
      { event: "reset", data: {} },
      { event: "delta", data: { text: "I couldn't complete that answer just now." } },
      { event: "card", data: { kind: "link", path: "/support", label: "Contact support" } },
      { event: "done", data: { message_id: "m2", confidence: "safe_mode", flags: ["stop:max_tokens"], usage: {}, latency_ms: 10, first_token_ms: 2, safe_mode: "max_tokens" } },
    ];
    renderIt(enabled);
    open();
    fireEvent.change(await screen.findByPlaceholderText(/type your message/i), { target: { value: "fees?" } });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    await waitFor(() => expect(screen.getByText(/couldn't complete that answer/)).toBeInTheDocument());
    expect(screen.queryByText(/The fee is 2/)).toBeNull();
    expect(screen.getByText(/safe mode/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /contact support/i })).toHaveAttribute("href", "/support");
  });

  it("restores the stored conversation for the same identity", async () => {
    localStorage.setItem("capimax_assistant_conversation:u1", "conv-old");
    api.status.mockResolvedValue(enabled);
    api.messages.mockResolvedValue([
      { id: "a", role: "user", text: "hi", cards: [], confidence: null, feedback: null, created_at: "t" },
      { id: "b", role: "assistant", text: "Hello again", cards: [], confidence: "normal", feedback: "up", created_at: "t" },
    ]);
    renderIt(enabled);
    open();
    await waitFor(() => expect(screen.getByText("Hello again")).toBeInTheDocument());
    expect(api.messages).toHaveBeenCalledWith("conv-old");
  });
  it("greets a visitor with the way in and one-tap questions that send themselves", async () => {
    authState.isAuthenticated = false;
    try {
      const visitor = { ...enabled, visitor_allowed: true };
      api.status.mockResolvedValue(visitor);
      stream.events = [
        { event: "started", data: { conversation_id: "conv-1" } },
        { event: "delta", data: { text: "Units are shares of one property." } },
        { event: "done", data: { message_id: "m1", confidence: "normal", safe_mode: null } },
      ];
      renderIt(visitor);
      open();
      const signIn = await screen.findByRole("link", { name: /sign in/i });
      expect(signIn).toHaveAttribute("href", "/auth");
      expect(screen.getByRole("link", { name: /create a free account/i })).toHaveAttribute(
        "href",
        "/auth?tab=register",
      );
      const starters = screen.getByTestId("assistant-starters");
      expect(starters).toHaveTextContent(/how does fractional ownership work/i);
      expect(starters).not.toHaveTextContent(/my balance/i);
      fireEvent.click(screen.getByRole("button", { name: /how does fractional ownership work/i }));
      await screen.findByText("How does fractional ownership work?", { selector: "p, div, span" });
      await screen.findByText(/units are shares of one property/i);
      expect(screen.queryByTestId("assistant-starters")).toBeNull(); // gone once the chat starts
    } finally {
      authState.isAuthenticated = true;
    }
  });

  it("offers a member account questions and no sign-in buttons", async () => {
    api.status.mockResolvedValue(enabled);
    renderIt(enabled);
    open();
    const starters = await screen.findByTestId("assistant-starters");
    expect(starters).toHaveTextContent(/what is my balance/i);
    expect(screen.queryByRole("link", { name: /sign in/i })).toBeNull();
  });
});
