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
    uploadAttachment: vi.fn(),
    attachmentBlob: vi.fn(),
    deleteAttachment: vi.fn(),
  },
  stream: { events: [] as unknown[], calls: [] as unknown[][] },
}));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => authState }));
vi.mock("@/lib/assistantApi", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    assistantApi: api,
    sendMessage: async function* (...args: unknown[]) {
      stream.calls.push(args);
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

function renderIt(status: AssistantStatus, url = "/") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <AssistantWidget status={status} />
    </MemoryRouter>,
  );
}
const open = () => fireEvent.click(screen.getByRole("button", { name: /open propshare assistant/i }));

describe("AssistantWidget", () => {
  beforeEach(() => {
    localStorage.clear();
    Object.values(api).forEach((m) => m.mockReset());
    api.createConversation.mockResolvedValue({ id: "conv-1" });
    api.messages.mockResolvedValue([]);
    api.feedback.mockResolvedValue(null);
    api.deleteAttachment.mockResolvedValue(undefined);
    stream.events = [];
    stream.calls = [];
    // jsdom has no object URLs: previews of picked pictures need them
    URL.createObjectURL = vi.fn(() => "blob:preview");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => vi.restoreAllMocks());

  const withAttachments = { ...enabled, attachments: { per_message: 3, max_mb: 10, max_pages: 30 } };
  const done = { event: "done", data: { message_id: "m1", confidence: "normal", flags: [], usage: {}, latency_ms: 1, first_token_ms: 1, safe_mode: null } };

  it("sends a picture with the message: picked, uploaded, shown, its id sent", async () => {
    api.status.mockResolvedValue(withAttachments);
    api.uploadAttachment.mockResolvedValue({ id: "att-1", kind: "image", filename: "shot.png", mime: "image/png", size_bytes: 3, width: 800, height: 600 });
    stream.events = [{ event: "delta", data: { text: "That is the wallet page." } }, done];
    renderIt(withAttachments);
    open();
    await waitFor(() => expect(screen.getByRole("button", { name: /attach a file or picture/i })).toBeInTheDocument());
    const file = new File(["png"], "shot.png", { type: "image/png" });
    fireEvent.change(screen.getByTestId("attachment-input"), { target: { files: [file] } });
    await waitFor(() => expect(api.uploadAttachment).toHaveBeenCalledWith("conv-1", file));
    expect(screen.getByTestId("pending-attachments")).toBeInTheDocument();
    // a picture alone can be sent: no text needed
    await waitFor(() => expect(screen.getByRole("button", { name: /send message/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    await waitFor(() => expect(screen.getByText("That is the wallet page.")).toBeInTheDocument());
    expect(stream.calls[0][5]).toEqual(["att-1"]);
    expect(screen.getByTestId("chat-picture")).toHaveAttribute("src", "blob:preview");
    expect(screen.queryByTestId("pending-attachments")).toBeNull();
  });

  it("sends a PDF with the message and shows it as a file the user can download again", async () => {
    api.status.mockResolvedValue(withAttachments);
    api.uploadAttachment.mockResolvedValue({ id: "att-2", kind: "file", filename: "receipt.pdf", mime: "application/pdf", size_bytes: 52000, pages: 1 });
    api.attachmentBlob.mockResolvedValue(new Blob(["%PDF"], { type: "application/pdf" }));
    stream.events = [{ event: "delta", data: { text: "The receipt shows a transfer of $900." } }, done];
    renderIt(withAttachments);
    open();
    await waitFor(() => expect(screen.getByTestId("attachment-input")).toBeInTheDocument());
    const pdf = new File(["%PDF-1.7"], "receipt.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByTestId("attachment-input"), { target: { files: [pdf] } });
    await waitFor(() => expect(api.uploadAttachment).toHaveBeenCalledWith("conv-1", pdf));
    expect(screen.getByTestId("pending-attachments")).toHaveTextContent("receipt.pdf");
    fireEvent.change(screen.getByPlaceholderText(/type your message/i), { target: { value: "Is my transfer here?" } });
    await waitFor(() => expect(screen.getByRole("button", { name: /send message/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    await waitFor(() => expect(screen.getByText("The receipt shows a transfer of $900.")).toBeInTheDocument());
    expect(stream.calls[0][5]).toEqual(["att-2"]);
    const chip = screen.getByTestId("chat-file");
    expect(chip).toHaveTextContent("receipt.pdf");
    fireEvent.click(chip);
    await waitFor(() => expect(api.attachmentBlob).toHaveBeenCalledWith("att-2"));
  });

  it("takes a file off before sending: gone from the server too, so its slot frees up", async () => {
    api.status.mockResolvedValue(withAttachments);
    api.uploadAttachment.mockResolvedValue({ id: "att-3", kind: "file", filename: "old.pdf", mime: "application/pdf", size_bytes: 900, pages: 1 });
    renderIt(withAttachments);
    open();
    await waitFor(() => expect(screen.getByTestId("attachment-input")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("attachment-input"), {
      target: { files: [new File(["%PDF"], "old.pdf", { type: "application/pdf" })] },
    });
    await waitFor(() => expect(screen.getByTestId("pending-attachments")).toHaveTextContent("old.pdf"));
    await waitFor(() => expect(screen.getByRole("button", { name: /send message/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /remove old\.pdf/i }));
    expect(api.deleteAttachment).toHaveBeenCalledWith("att-3");
    expect(screen.queryByTestId("pending-attachments")).toBeNull();
  });

  it("gives the attachments back when the message is not taken, instead of losing them", async () => {
    api.status.mockResolvedValue(withAttachments);
    api.uploadAttachment.mockResolvedValue({ id: "att-4", kind: "image", filename: "shot.png", mime: "image/png", size_bytes: 3, width: 8, height: 8 });
    stream.events = [{ event: "error", data: { code: "DAILY_CAP", message: "You have reached today's message limit." } }];
    renderIt(withAttachments);
    open();
    await waitFor(() => expect(screen.getByTestId("attachment-input")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("attachment-input"), {
      target: { files: [new File(["png"], "shot.png", { type: "image/png" })] },
    });
    await waitFor(() => expect(screen.getByRole("button", { name: /send message/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    expect(await screen.findByText("You have reached today's message limit.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("pending-attachments")).toBeInTheDocument());
    expect(screen.queryByTestId("chat-picture")).toBeNull(); // it was not sent: back in the box
    expect(api.deleteAttachment).not.toHaveBeenCalled();
  });

  it("puts pictures picked one right after the other in one new conversation", async () => {
    api.status.mockResolvedValue(withAttachments);
    let created: (v: { id: string }) => void = () => undefined;
    api.createConversation.mockReturnValue(new Promise((resolve) => (created = resolve)));
    api.uploadAttachment.mockImplementation(async (_cid: string, file: File) => ({
      id: `att-${file.name}`, kind: "image", filename: file.name, mime: "image/png", size_bytes: 3, width: 8, height: 8,
    }));
    renderIt(withAttachments);
    open();
    await waitFor(() => expect(screen.getByTestId("attachment-input")).toBeInTheDocument());
    const input = screen.getByTestId("attachment-input");
    fireEvent.change(input, { target: { files: [new File(["a"], "a.png", { type: "image/png" })] } });
    fireEvent.change(input, { target: { files: [new File(["b"], "b.png", { type: "image/png" })] } });
    created({ id: "conv-7" });
    await waitFor(() => expect(api.uploadAttachment).toHaveBeenCalledTimes(2));
    expect(api.createConversation).toHaveBeenCalledTimes(1);
    expect(api.uploadAttachment.mock.calls.map((c) => c[0])).toEqual(["conv-7", "conv-7"]);
  });

  it("refuses a kind of file the platform does not take before uploading it", async () => {
    api.status.mockResolvedValue(withAttachments);
    renderIt(withAttachments);
    open();
    await waitFor(() => expect(screen.getByTestId("attachment-input")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("attachment-input"), {
      target: { files: [new File(["MZ"], "setup.exe", { type: "application/x-msdownload" })] },
    });
    expect(await screen.findByText(/send a picture, a pdf, a word, excel/i)).toBeInTheDocument();
    expect(api.uploadAttachment).not.toHaveBeenCalled();
  });

  it("offers no attach button to visitors or when the platform does not offer attachments", async () => {
    api.status.mockResolvedValue(enabled);
    renderIt(enabled);
    open();
    await waitFor(() => expect(screen.getByPlaceholderText(/type your message/i)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /attach a file or picture/i })).toBeNull();
  });

  it("shows the pictures and files of a reopened chat, fetched back from the server", async () => {
    api.status.mockResolvedValue(withAttachments);
    localStorage.setItem("capimax_assistant_conversation:u1", "conv-9");
    api.messages.mockResolvedValue([
      {
        id: "u1m", role: "user", text: "", cards: [], confidence: null, feedback: null, created_at: "now",
        attachments: [
          { id: "att-9", kind: "image", filename: "shot.png", mime: "image/png", size_bytes: 10, width: 10, height: 10 },
          { id: "att-10", kind: "file", filename: "statement.xlsx", mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", size_bytes: 2048 },
        ],
      },
      { id: "a1m", role: "assistant", text: "I see the error.", cards: [], confidence: "normal", feedback: null, created_at: "now" },
    ]);
    api.attachmentBlob.mockResolvedValue(new Blob(["png"], { type: "image/png" }));
    renderIt(withAttachments);
    open();
    await waitFor(() => expect(api.attachmentBlob).toHaveBeenCalledWith("att-9"));
    await waitFor(() => expect(screen.getByTestId("chat-picture")).toHaveAttribute("src", "blob:preview"));
    expect(screen.getByTestId("chat-file")).toHaveTextContent("statement.xlsx");
    expect(api.attachmentBlob).not.toHaveBeenCalledWith("att-10"); // a file downloads only on a click
  });

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
    api.confirm.mockResolvedValue({ id: "p1", action: "create_support_ticket", status: "executed", summary: "x", result: { ticket_no: "CPX-001001", ticket_id: "t-1" }, decided_at: "now" });
    stream.events = [
      { event: "started", data: { conversation_id: "conv-1", user_message_id: "um" } },
      { event: "tool", data: { name: "get_my_wallet", status: "running" } },
      { event: "tool", data: { name: "get_my_wallet", status: "ok" } },
      { event: "delta", data: { text: "Your balance is " } },
      { event: "delta", data: { text: "$5,000.00." } },
      { event: "card", data: { kind: "link", path: "/wallet", label: "Open your wallet" } },
      { event: "card", data: { kind: "confirm_action", proposal_id: "p1", action: "create_support_ticket", summary: "Open a customer service ticket (payments).", details: [["Subject", "Deposit missing"], ["What happened", "I paid by card and it is not in my wallet."]], token: "tok-secret", expires_at: "later" } },
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
    expect(screen.getByText("Checked your wallet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open your wallet/i })).toHaveAttribute("href", "/wallet");
    expect(screen.getByTestId("confirm-card")).toBeInTheDocument();
    // the user reads exactly what the ticket will say before confirming
    expect(screen.getByTestId("confirm-details")).toHaveTextContent("I paid by card and it is not in my wallet.");
    expect(screen.queryByText("tok-secret")).toBeNull(); // the token is never rendered
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));
    await waitFor(() => expect(api.confirm).toHaveBeenCalledWith("p1", "tok-secret"));
    await waitFor(() =>
      expect(screen.getByText(/customer service ticket CPX-001001 is open/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("link", { name: /view your ticket/i })).toHaveAttribute("href", "/support/tickets/t-1");
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
      const visitor = { ...enabled, visitor_allowed: true, privacy_notice: true };
      api.status.mockResolvedValue(visitor);
      stream.events = [
        { event: "started", data: { conversation_id: "conv-1" } },
        { event: "delta", data: { text: "Units are shares of one property." } },
        { event: "done", data: { message_id: "m1", confidence: "normal", safe_mode: null } },
      ];
      renderIt(visitor);
      open();
      // before a visitor's first message leaves for the AI provider, they are told so, once
      const notice = await screen.findByTestId("consent-gate");
      expect(notice).toHaveTextContent(/OpenAI/);
      expect(screen.queryByTestId("assistant-starters")).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: /i understand, continue/i }));
      expect(localStorage.getItem("capimax_assistant_visitor_notice")).toBe(visitor.policy_version);
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

  it("shows a visitor no notice at all when the platform does not ask for one", async () => {
    authState.isAuthenticated = false;
    try {
      const visitor = { ...enabled, visitor_allowed: true, privacy_notice: false };
      api.status.mockResolvedValue(visitor);
      renderIt(visitor);
      open();
      await screen.findByTestId("assistant-starters");
      expect(screen.queryByTestId("consent-gate")).toBeNull();
    } finally {
      authState.isAuthenticated = true;
    }
  });

  it("does not show the visitor notice again once acknowledged in this browser", async () => {
    authState.isAuthenticated = false;
    try {
      const visitor = { ...enabled, visitor_allowed: true, privacy_notice: true };
      localStorage.setItem("capimax_assistant_visitor_notice", visitor.policy_version);
      api.status.mockResolvedValue(visitor);
      renderIt(visitor);
      open();
      await screen.findByTestId("assistant-starters");
      expect(screen.queryByTestId("consent-gate")).toBeNull();
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
  it("stays in English when the assistant is set to reply in English only", async () => {
    localStorage.setItem("capimax_assistant_lang", "ar"); // a visitor who once picked Arabic
    const englishOnly = { ...enabled, reply_language: "en" as const };
    api.status.mockResolvedValue(englishOnly);
    renderIt(englishOnly);
    open();
    await screen.findByTestId("assistant-starters");
    expect(screen.queryByRole("button", { name: /switch language/i })).toBeNull();
    expect(screen.getByText(/your PropShare concierge/)).toBeInTheDocument();
    expect(screen.getByTestId("assistant-starters")).toHaveTextContent(/what is my balance/i);
  });
  it("shows a one-time teaser next to the launcher, and never again once dismissed", async () => {
    vi.useFakeTimers();
    try {
      api.status.mockResolvedValue(enabled);
      const { unmount } = renderIt(enabled);
      expect(screen.queryByText(/questions about investing/i)).toBeNull();
      await vi.advanceTimersByTimeAsync(4100);
      expect(screen.getByText(/questions about investing/i)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
      expect(screen.queryByText(/questions about investing/i)).toBeNull();
      unmount();
      renderIt(enabled);
      await vi.advanceTimersByTimeAsync(5000);
      expect(screen.queryByText(/questions about investing/i)).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("greets a member by name on the welcome screen", async () => {
    const prev = authState.user;
    (authState as { user: unknown }).user = { id: "u1", full_name: "Sara Investor" };
    try {
      api.status.mockResolvedValue(enabled);
      renderIt(enabled);
      open();
      const hero = await screen.findByTestId("assistant-hero");
      expect(hero).toHaveTextContent(/, Sara/);
    } finally {
      (authState as { user: unknown }).user = prev;
    }
  });
  it("does not repeat a property shown as a tile as a second button", async () => {
    api.status.mockResolvedValue(enabled);
    stream.events = [
      { event: "started", data: { conversation_id: "conv-1" } },
      { event: "delta", data: { text: "Two towers match." } },
      { event: "card", data: { kind: "properties", items: [{ slug: "eval-tower", title: "Eval Tower", city: "Dubai", status: "active", unit_price: 100, expected_yield: 7, path: "/property/eval-tower" }] } },
      { event: "card", data: { kind: "link", path: "/property/eval-tower", label: "Eval Tower" } },
      { event: "card", data: { kind: "link", path: "/marketplace", label: "Marketplace" } },
      { event: "done", data: { message_id: "m1", confidence: "normal", safe_mode: null } },
    ];
    renderIt(enabled);
    open();
    await screen.findByTestId("assistant-starters");
    fireEvent.change(screen.getByPlaceholderText(/type your message/i), { target: { value: "towers?" } });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    await screen.findByText(/two towers match/i);
    expect(screen.getAllByRole("link", { name: /eval tower/i })).toHaveLength(1); // the tile only
    expect(screen.getByRole("link", { name: /marketplace/i })).toHaveAttribute("href", "/marketplace");
    expect(screen.queryByTestId("assistant-hero")).toBeNull();
  });
  it("shows a prepared order with a Continue to payment link and no duplicate property button", async () => {
    api.status.mockResolvedValue(enabled);
    stream.events = [
      { event: "started", data: { conversation_id: "conv-1" } },
      { event: "delta", data: { text: "Your order is ready." } },
      { event: "card", data: { kind: "checkout", title: "Eval Tower", units: 100, unit_price: "100.00", subtotal: "10000.00", platform_fee: "250.00", total_now: "10250.00", purchase_type: "direct", duration_months: null, notes: [], ready: true, path: "/property/eval-tower?units=100" } },
      { event: "card", data: { kind: "link", path: "/property/eval-tower", label: "Eval Tower" } },
      { event: "card", data: { kind: "property", slug: "eval-tower", title: "Eval Tower", path: "/property/eval-tower" } },
      { event: "done", data: { message_id: "m1", confidence: "normal", safe_mode: null } },
    ];
    renderIt(enabled);
    open();
    await screen.findByTestId("assistant-starters");
    fireEvent.change(screen.getByPlaceholderText(/type your message/i), { target: { value: "100 units please" } });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    const card = await screen.findByTestId("checkout-card");
    expect(card).toHaveTextContent("$10,250.00");
    expect(card).toHaveTextContent(/nothing is charged until you confirm payment/i);
    expect(screen.getByRole("link", { name: /continue to payment/i })).toHaveAttribute(
      "href",
      "/property/eval-tower?units=100",
    );
    expect(screen.queryByRole("link", { name: /^eval tower$/i })).toBeNull();
  });
  it("knows the page: property questions on a property page, sent with the page path", async () => {
    api.status.mockResolvedValue(enabled);
    stream.events = [
      { event: "started", data: { conversation_id: "conv-1" } },
      { event: "delta", data: { text: "Your order is ready." } },
      { event: "done", data: { message_id: "m1", confidence: "normal", safe_mode: null } },
    ];
    renderIt(enabled, "/property/eval-tower?preview=tok");
    open();
    const starters = await screen.findByTestId("assistant-starters");
    expect(screen.getByText("About this property")).toBeInTheDocument();
    expect(starters).not.toHaveTextContent(/what is my balance/i);
    fireEvent.click(screen.getByRole("button", { name: /prepare 10 units of this property/i }));
    await screen.findByText(/your order is ready/i);
    const [, text, , , page] = stream.calls[0];
    expect(text).toBe("Prepare 10 units of this property");
    expect(page).toBe("/property/eval-tower?preview=tok"); // the server keeps only what it trusts
  });

  it("offers wallet actions on the wallet page and drops a plain wallet button beside a wallet card", async () => {
    api.status.mockResolvedValue(enabled);
    stream.events = [
      { event: "started", data: { conversation_id: "conv-1" } },
      { event: "delta", data: { text: "Your deposit is ready." } },
      { event: "card", data: { kind: "deposit", amount: "1000.00", currency: "USD", method: "card", method_label: "Card", notes: [], ready: true, path: "/dashboard?tab=wallet&action=deposit&amount=1000.00&method=card" } },
      { event: "card", data: { kind: "link", path: "/dashboard?tab=wallet", label: "Open your wallet" } },
      { event: "done", data: { message_id: "m1", confidence: "normal", safe_mode: null } },
    ];
    renderIt(enabled, "/dashboard?tab=wallet");
    open();
    const starters = await screen.findByTestId("assistant-starters");
    expect(starters).toHaveTextContent(/statement for the last 3 months/i);
    fireEvent.click(screen.getByRole("button", { name: /add \$1,000 to my wallet by card/i }));
    await screen.findByTestId("deposit-card");
    expect(screen.getByRole("link", { name: /continue to payment/i })).toHaveAttribute(
      "href",
      "/dashboard?tab=wallet&action=deposit&amount=1000.00&method=card",
    );
    expect(screen.queryByRole("link", { name: /open your wallet/i })).toBeNull();
    expect(stream.calls[0][4]).toBe("/dashboard?tab=wallet");
  });

  it("does not pop the teaser after the panel was opened before its timer fired", async () => {
    vi.useFakeTimers();
    try {
      api.status.mockResolvedValue(enabled);
      renderIt(enabled);
      await vi.advanceTimersByTimeAsync(1000);
      open(); // opened early
      fireEvent.click(screen.getByRole("button", { name: /close chat/i }));
      await vi.advanceTimersByTimeAsync(5000);
      expect(screen.queryByText(/questions about investing/i)).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
