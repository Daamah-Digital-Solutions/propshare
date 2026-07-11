import { useCallback, useEffect, useRef, useState } from "react";
import { MessageCircle, X, Send, RefreshCw, Sparkles, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * CapiMax PropShare assistant — a floating chat widget wired to the platform's n8n agent.
 *
 * The browser calls the webhook DIRECTLY (CORS is pre-enabled for the apex + www); no backend
 * proxy. Contract:
 *   POST { action: "sendMessage", sessionId, chatInput }  ->  { output: "<reply>" }
 * The agent keeps its own memory (last 12 messages) keyed by sessionId, so we hold ONE stable
 * sessionId per conversation (persisted in localStorage) and a fresh one on "New chat". The
 * visible transcript is persisted too, so reopening/reloading keeps the conversation on screen.
 */

const CHAT_URL =
  import.meta.env.VITE_CHATBOT_URL ??
  "https://ai.capimaxgroup.com/webhook/capimax-propshare/chat";

const SESSION_KEY = "capimax_chat_session";
const HISTORY_KEY = "capimax_chat_history";
const MAX_PERSISTED = 50; // bound localStorage growth

type Role = "user" | "assistant";
interface ChatMessage {
  id: string;
  role: Role;
  text: string;
}

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "👋 Hi! I'm the CapiMax PropShare assistant. Ask me anything about investing, properties, fees, or how the platform works.",
};

const uid = () =>
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

function loadSession(): string {
  try {
    const existing = localStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    const fresh = uid();
    localStorage.setItem(SESSION_KEY, fresh);
    return fresh;
  } catch {
    return uid();
  }
}

function loadHistory(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [WELCOME];
    const parsed = JSON.parse(raw) as ChatMessage[];
    return Array.isArray(parsed) && parsed.length ? parsed : [WELCOME];
  } catch {
    return [WELCOME];
  }
}

/** Inline formatting for one line: autolinked URLs + **bold**. Built from React nodes only
 *  (never dangerouslySetInnerHTML), so it's XSS-safe. NB: the per-part URL test uses an
 *  anchored, NON-global regex — calling .test() on a /g regex advances lastIndex and misbehaves. */
function renderInline(text: string, keyBase: string) {
  return text.split(/(https?:\/\/[^\s]+)/g).map((part, i) => {
    if (/^https?:\/\//.test(part)) {
      return (
        <a
          key={`${keyBase}-u${i}`}
          href={part}
          target="_blank"
          rel="noopener noreferrer"
          className="underline break-words text-primary"
        >
          {part}
        </a>
      );
    }
    return part.split(/\*\*(.+?)\*\*/g).map((seg, j) =>
      j % 2 === 1 ? (
        <strong key={`${keyBase}-b${i}-${j}`}>{seg}</strong>
      ) : (
        <span key={`${keyBase}-s${i}-${j}`}>{seg}</span>
      ),
    );
  });
}

/** Lightweight, safe markdown-ish rendering of an assistant reply: bullet lists (- / *),
 *  blockquotes (>), blank-line spacing, plus inline bold + links. Covers the shapes the n8n
 *  agent emits without pulling in a markdown dependency. */
function renderRich(text: string) {
  const lines = text.split("\n");
  const blocks: React.ReactNode[] = [];
  let bullets: string[] = [];
  const flushBullets = (key: string) => {
    if (!bullets.length) return;
    const items = bullets;
    bullets = [];
    blocks.push(
      <ul key={key} className="my-1 ml-4 list-disc space-y-0.5">
        {items.map((b, i) => (
          <li key={i}>{renderInline(b, `${key}-${i}`)}</li>
        ))}
      </ul>,
    );
  };
  lines.forEach((raw, idx) => {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    if (bullet) {
      bullets.push(bullet[1]);
      return;
    }
    flushBullets(`ul-${idx}`);
    if (!line.trim()) {
      blocks.push(<div key={`sp-${idx}`} className="h-2" />);
      return;
    }
    const quote = line.match(/^\s*>\s?(.*)$/);
    if (quote) {
      blocks.push(
        <div
          key={`q-${idx}`}
          className="my-1 border-l-2 border-primary/40 pl-2 text-muted-foreground"
        >
          {renderInline(quote[1], `q-${idx}`)}
        </div>,
      );
      return;
    }
    blocks.push(<div key={`l-${idx}`}>{renderInline(line, `l-${idx}`)}</div>);
  });
  flushBullets("ul-end");
  return blocks;
}

export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(loadHistory);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const sessionRef = useRef<string>(loadSession());
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Persist the visible transcript (bounded) so it survives reloads.
  useEffect(() => {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(messages.slice(-MAX_PERSISTED)));
    } catch {
      /* storage full / disabled — non-fatal */
    }
  }, [messages]);

  // Keep the newest message in view; focus the input when opened.
  useEffect(() => {
    if (open) {
      // optional-call scrollTo: jsdom (tests) doesn't implement it, and `?.` on the ref only
      // guards null, not a missing method.
      scrollRef.current?.scrollTo?.({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth",
      });
      inputRef.current?.focus();
    }
  }, [open, messages, sending]);

  const resetChat = useCallback(() => {
    const fresh = uid();
    sessionRef.current = fresh;
    try {
      localStorage.setItem(SESSION_KEY, fresh);
    } catch {
      /* non-fatal */
    }
    setMessages([WELCOME]);
    setInput("");
  }, []);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;
    const userMsg: ChatMessage = { id: uid(), role: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setSending(true);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60_000);
    try {
      const resp = await fetch(CHAT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "sendMessage",
          sessionId: sessionRef.current,
          chatInput: text,
        }),
        signal: controller.signal,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const raw = await resp.text();
      let reply = "";
      try {
        const data = JSON.parse(raw);
        reply =
          (typeof data === "string" ? data : data?.output ?? data?.reply ?? data?.text ?? "") || "";
      } catch {
        reply = raw; // non-JSON body — show it as-is
      }
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          text: reply.trim() || "Sorry, I didn't catch that. Could you rephrase?",
        },
      ]);
    } catch (err) {
      const aborted = err instanceof DOMException && err.name === "AbortError";
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          text: aborted
            ? "That took too long to answer. Please try again."
            : "I couldn't reach the assistant right now. Please try again in a moment.",
        },
      ]);
    } finally {
      clearTimeout(timeout);
      setSending(false);
    }
  }, [input, sending]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  return (
    <>
      {/* Launcher */}
      {!open && (
        <button
          type="button"
          aria-label="Open CapiMax assistant"
          onClick={() => setOpen(true)}
          className="fixed bottom-5 right-5 z-[60] flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105 active:scale-95"
        >
          <MessageCircle className="h-6 w-6" />
          <span className="absolute -right-0.5 -top-0.5 flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-amber-400" />
          </span>
        </button>
      )}

      {/* Panel */}
      {open && (
        <div
          role="dialog"
          aria-label="CapiMax assistant"
          className="fixed bottom-4 right-4 z-[60] flex w-[calc(100vw-2rem)] max-w-[380px] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl"
          style={{ height: "min(70vh, 560px)" }}
        >
          {/* Header */}
          <div className="flex items-center gap-3 bg-primary px-4 py-3 text-primary-foreground">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15">
              <Sparkles className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold leading-tight">CapiMax Assistant</div>
              <div className="text-[11px] text-primary-foreground/80">
                Investing, properties &amp; fees
              </div>
            </div>
            <button
              type="button"
              aria-label="New chat"
              title="New chat"
              onClick={resetChat}
              className="rounded-md p-1.5 hover:bg-white/15"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
            <button
              type="button"
              aria-label="Close chat"
              onClick={() => setOpen(false)}
              className="rounded-md p-1.5 hover:bg-white/15"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto bg-muted/20 p-3">
            {messages.map((m) => (
              <div
                key={m.id}
                className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}
              >
                <div
                  className={cn(
                    "max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed",
                    m.role === "user"
                      ? "rounded-br-sm bg-primary text-primary-foreground"
                      : "rounded-bl-sm border border-border bg-card text-foreground",
                  )}
                >
                  {renderRich(m.text)}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm border border-border bg-card px-3 py-2.5">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground" />
                </div>
              </div>
            )}
          </div>

          {/* Composer */}
          <div className="border-t border-border bg-card p-2">
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                rows={1}
                placeholder="Type your message…"
                className="max-h-28 min-h-[40px] flex-1 resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <button
                type="button"
                aria-label="Send message"
                onClick={() => void send()}
                disabled={sending || !input.trim()}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-opacity disabled:opacity-50"
              >
                {sending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </button>
            </div>
            <div className="px-1 pt-1 text-[10px] text-muted-foreground">
              AI assistant — may be inaccurate. Not investment advice.
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default ChatWidget;
