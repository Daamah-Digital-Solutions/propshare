import { useCallback, useEffect, useRef, useState } from "react";
import { MessageCircle, X, Send, RefreshCw, Sparkles, Loader2, ThumbsUp, ThumbsDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { ApiError } from "@/lib/api";
import {
  assistantApi,
  sendMessage,
  type AssistantCard,
  type AssistantStatus,
  type TurnDone,
} from "@/lib/assistantApi";
import { AssistantCardView } from "@/components/assistant/AssistantCards";

/**
 * Capimax assistant v2 — the in-platform agent (plan Phase 1 §6).
 *
 * Talks ONLY to our backend (SSE); the model runs server-side with the user's real data and
 * a per-tool allow-list. What this component owns: the consent gate for signed-in users, the
 * conversation id (persisted per identity), streaming text, server-built cards (links,
 * properties, confirm/cancel), tool indicators, thumbs feedback, Arabic/English direction.
 * It never invents an answer: on any failure the backend's safe-mode text is what shows.
 */

const CONV_KEY = "capimax_assistant_conversation";
const LANG_KEY = "capimax_assistant_lang";

type Role = "user" | "assistant";
interface Msg {
  id: string;
  role: Role;
  text: string;
  cards: AssistantCard[];
  tools: { name: string; status: "running" | "ok" | "error" }[];
  done?: TurnDone;
  feedback?: "up" | "down";
  streaming?: boolean;
}

const uid = () =>
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const WELCOME_EN =
  "Hi! I can explain how Capimax PropShare works, look up your own account, and take you to the right page. What do you need?";
const WELCOME_AR =
  "أهلًا! أقدر أشرح لك كيف تعمل Capimax PropShare، وأراجع حسابك، وأوصّلك للصفحة الصحيحة. كيف أساعدك؟";

function isArabic(text: string): boolean {
  const letters = text.replace(/[^\p{L}]/gu, "");
  if (!letters) return false;
  const ar = (letters.match(/[؀-ۿ]/g) || []).length;
  return ar / letters.length > 0.5;
}

/** Minimal, safe rendering: paragraphs, bullet lists, **bold**. No HTML injection. */
function renderText(text: string, keyBase: string) {
  const lines = text.split("\n");
  const out: React.ReactNode[] = [];
  let bullets: string[] = [];
  const flush = (k: string) => {
    if (!bullets.length) return;
    const items = bullets;
    bullets = [];
    out.push(
      <ul key={k} className="my-1 ms-4 list-disc space-y-0.5">
        {items.map((b, i) => (
          <li key={i}>{inline(b, `${k}-${i}`)}</li>
        ))}
      </ul>,
    );
  };
  let table: string[][] = [];
  const flushTable = (k: string) => {
    if (!table.length) return;
    const rows = table;
    table = [];
    out.push(
      <div key={k} className="my-1 overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <tbody>
            {rows.map((cells, r) => (
              <tr key={r} className={r === 0 ? "font-semibold" : "border-t border-border"}>
                {cells.map((c, ci) => (
                  <td key={ci} className="px-1.5 py-1 align-top">
                    {inline(c, `${k}-${r}-${ci}`)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>,
    );
  };
  lines.forEach((raw, idx) => {
    const line = raw.trimEnd();
    // markdown table rows: "| a | b |" (the "|---|" separator row is dropped)
    if (/^\s*\|.*\|\s*$/.test(line)) {
      if (!/^\s*\|(\s*:?-+:?\s*\|)+\s*$/.test(line)) {
        table.push(line.trim().slice(1, -1).split("|").map((c) => c.trim()));
      }
      return;
    }
    flushTable(`${keyBase}-t-${idx}`);
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    if (bullet) {
      bullets.push(bullet[1]);
      return;
    }
    flush(`${keyBase}-ul-${idx}`);
    if (!line.trim()) {
      out.push(<div key={`${keyBase}-sp-${idx}`} className="h-2" />);
      return;
    }
    out.push(<div key={`${keyBase}-l-${idx}`}>{inline(line.replace(/^#+\s*/, ""), `${keyBase}-l-${idx}`)}</div>);
  });
  flushTable(`${keyBase}-t-end`);
  flush(`${keyBase}-ul-end`);
  return out;
}

function inline(text: string, keyBase: string) {
  return text.split(/\*\*(.+?)\*\*/g).map((seg, j) =>
    j % 2 === 1 ? <strong key={`${keyBase}-b${j}`}>{seg}</strong> : <span key={`${keyBase}-s${j}`}>{seg}</span>,
  );
}

export function AssistantWidget({ status: initialStatus }: { status: AssistantStatus }) {
  const { isAuthenticated, user } = useAuth();
  const identity = isAuthenticated ? (user?.id ?? "user") : "visitor";
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<AssistantStatus>(initialStatus);
  const [lang, setLang] = useState<"en" | "ar">(() => {
    try {
      return (localStorage.getItem(LANG_KEY) as "en" | "ar") || "en";
    } catch {
      return "en";
    }
  });
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [consenting, setConsenting] = useState(false);
  const [error, setError] = useState<string>("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const welcome = useCallback(
    (): Msg => ({ id: "welcome", role: "assistant", text: lang === "ar" ? WELCOME_AR : WELCOME_EN, cards: [], tools: [] }),
    [lang],
  );

  // Restore (or start) this identity's conversation when the panel opens.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const fresh = await assistantApi.status();
        if (!cancelled) setStatus(fresh);
        if (!fresh.enabled) return;
        let key: string | null = null;
        try {
          key = localStorage.getItem(`${CONV_KEY}:${identity}`);
        } catch {
          /* no storage */
        }
        if (key) {
          try {
            const history = await assistantApi.messages(key);
            if (cancelled) return;
            setConversationId(key);
            setMessages(
              history.length
                ? history.map((m) => ({
                    id: m.id,
                    role: m.role,
                    text: m.text ?? "",
                    cards: m.cards ?? [],
                    tools: [],
                    feedback: (m.feedback as "up" | "down" | null) ?? undefined,
                  }))
                : [welcome()],
            );
            return;
          } catch {
            /* stale id (purged / other account) -> start fresh below */
          }
        }
        if (!cancelled) {
          setConversationId(null);
          setMessages([welcome()]);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "The assistant is not reachable right now.");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, identity]);

  useEffect(() => {
    if (open) {
      scrollRef.current?.scrollTo?.({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
      inputRef.current?.focus();
    }
  }, [open, messages, busy]);

  const ensureConversation = useCallback(async (): Promise<string> => {
    if (conversationId) return conversationId;
    const conv = await assistantApi.createConversation();
    setConversationId(conv.id);
    try {
      localStorage.setItem(`${CONV_KEY}:${identity}`, conv.id);
    } catch {
      /* non-fatal */
    }
    return conv.id;
  }, [conversationId, identity]);

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    setConversationId(null);
    try {
      localStorage.removeItem(`${CONV_KEY}:${identity}`);
    } catch {
      /* non-fatal */
    }
    setMessages([welcome()]);
    setInput("");
    setError("");
  }, [identity, welcome]);

  const giveConsent = useCallback(async () => {
    setConsenting(true);
    try {
      await assistantApi.consent(status.policy_version);
      setStatus(await assistantApi.status());
      setMessages([welcome()]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record your consent.");
    } finally {
      setConsenting(false);
    }
  }, [status.policy_version, welcome]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || busy) return;
    setError("");
    const turnLang: "en" | "ar" = isArabic(text) ? "ar" : lang;
    const userMsg: Msg = { id: uid(), role: "user", text, cards: [], tools: [] };
    const reply: Msg = { id: uid(), role: "assistant", text: "", cards: [], tools: [], streaming: true };
    setMessages((prev) => [...prev, userMsg, reply]);
    setInput("");
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const patch = (fn: (m: Msg) => Msg) =>
      setMessages((prev) => prev.map((m) => (m.id === reply.id ? fn(m) : m)));
    try {
      const cid = await ensureConversation();
      for await (const ev of sendMessage(cid, text, turnLang, controller.signal)) {
        if (ev.event === "delta") patch((m) => ({ ...m, text: m.text + ev.data.text }));
        else if (ev.event === "reset") patch((m) => ({ ...m, text: "" }));
        else if (ev.event === "tool")
          patch((m) => {
            const tools = m.tools.filter((t) => t.name !== ev.data.name || ev.data.status === "running");
            return { ...m, tools: [...tools, ev.data] };
          });
        else if (ev.event === "card") patch((m) => ({ ...m, cards: [...m.cards, ev.data] }));
        else if (ev.event === "done") patch((m) => ({ ...m, done: ev.data, streaming: false }));
        else if (ev.event === "error")
          patch((m) => ({ ...m, text: m.text || ev.data.message, streaming: false }));
      }
      patch((m) => ({ ...m, streaming: false }));
    } catch (err) {
      const aborted = err instanceof DOMException && err.name === "AbortError";
      const msg =
        err instanceof ApiError
          ? err.code === "CONSENT_REQUIRED"
            ? "Please accept the privacy notice first."
            : err.message
          : aborted
            ? "Stopped."
            : "I couldn't reach the assistant right now. Please try again in a moment.";
      patch((m) => ({ ...m, text: m.text || msg, streaming: false }));
      if (err instanceof ApiError && err.code === "CONSENT_REQUIRED") {
        setStatus((s) => ({ ...s, consent_required: true, consent_given: false, enabled: false, reason: "CONSENT_REQUIRED" }));
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }, [input, busy, lang, ensureConversation]);

  const feedback = useCallback(async (m: Msg, value: "up" | "down") => {
    if (!m.done) return;
    setMessages((prev) => prev.map((x) => (x.id === m.id ? { ...x, feedback: value } : x)));
    try {
      await assistantApi.feedback(m.done.message_id, value);
    } catch {
      /* best effort */
    }
  }, []);

  const toggleLang = () => {
    const next = lang === "en" ? "ar" : "en";
    setLang(next);
    try {
      localStorage.setItem(LANG_KEY, next);
    } catch {
      /* non-fatal */
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const dir = lang === "ar" ? "rtl" : "ltr";
  const needsConsent = isAuthenticated && status.consent_required;
  const blocked = !status.enabled && !needsConsent;

  return (
    <>
      {!open && (
        <button
          type="button"
          aria-label="Open Capimax assistant"
          onClick={() => setOpen(true)}
          className="fixed bottom-[calc(5rem_+_env(safe-area-inset-bottom))] right-4 z-[60] flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105 active:scale-95 lg:bottom-5 lg:right-5"
        >
          <MessageCircle className="h-6 w-6" />
        </button>
      )}

      {open && (
        <div
          role="dialog"
          aria-label="Capimax assistant"
          dir={dir}
          className="fixed bottom-[calc(5rem_+_env(safe-area-inset-bottom))] right-4 z-[60] flex w-[calc(100vw-2rem)] max-w-[400px] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl lg:bottom-4"
          style={{ height: "min(70vh, 600px)" }}
        >
          <div className="flex items-center gap-3 bg-primary px-4 py-3 text-primary-foreground">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15">
              <Sparkles className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold leading-tight">Capimax Assistant</div>
              <div className="text-[11px] text-primary-foreground/80">
                {lang === "ar" ? "يقرأ بياناتك الحقيقية · لا ينفّذ بدون تأكيدك" : "Reads your real data · acts only with your confirmation"}
              </div>
            </div>
            <button type="button" aria-label="Switch language" title="EN / AR" onClick={toggleLang} className="rounded-md px-1.5 py-1 text-xs font-semibold hover:bg-white/15">
              {lang === "en" ? "ع" : "EN"}
            </button>
            <button type="button" aria-label="New chat" title="New chat" onClick={newChat} className="rounded-md p-1.5 hover:bg-white/15">
              <RefreshCw className="h-4 w-4" />
            </button>
            <button type="button" aria-label="Close chat" onClick={() => setOpen(false)} className="rounded-md p-1.5 hover:bg-white/15">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto bg-muted/20 p-3">
            {needsConsent && (
              <div className="rounded-xl border border-border bg-card p-3 text-sm" data-testid="consent-gate">
                <div className="font-semibold">{lang === "ar" ? "قبل أن نبدأ" : "Before we start"}</div>
                <p className="mt-1 text-muted-foreground">
                  {lang === "ar"
                    ? "يستخدم المساعد بيانات حسابك ويرسل نص المحادثة إلى مزوّد ذكاء اصطناعي خارجي. تُحفظ محادثاتك مشفّرة. اقرأ "
                    : "The assistant uses your account data and sends the conversation text to an external AI provider. Your conversations are stored encrypted. Read the "}
                  <a href="/privacy" className="text-primary underline" target="_blank" rel="noreferrer">
                    {lang === "ar" ? "سياسة الخصوصية" : "Privacy Policy"}
                  </a>
                  {lang === "ar" ? " (الإصدار " : " (version "}
                  {status.policy_version}).
                </p>
                <button
                  type="button"
                  onClick={() => void giveConsent()}
                  disabled={consenting}
                  className="mt-2 inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-50"
                >
                  {consenting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                  {lang === "ar" ? "أوافق وأكمل" : "I agree, continue"}
                </button>
              </div>
            )}
            {blocked && (
              <div className="rounded-xl border border-border bg-card p-3 text-sm text-muted-foreground" data-testid="assistant-unavailable">
                {status.reason === "SIGN_IN_REQUIRED"
                  ? lang === "ar"
                    ? "سجّل الدخول لاستخدام المساعد."
                    : "Please sign in to use the assistant."
                  : lang === "ar"
                    ? "المساعد غير متاح حاليًا. يمكنك التواصل مع الدعم."
                    : "The assistant is not available right now. You can contact support instead."}{" "}
                <a href="/support" className="text-primary underline">
                  {lang === "ar" ? "الدعم" : "Support"}
                </a>
              </div>
            )}
            {error && <div className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</div>}
            {messages.map((m) => (
              <div key={m.id} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                <div className="max-w-[88%]">
                  <div
                    dir="auto"
                    className={cn(
                      "rounded-2xl px-3 py-2 text-sm leading-relaxed",
                      m.role === "user"
                        ? "rounded-br-sm bg-primary text-primary-foreground"
                        : "rounded-bl-sm border border-border bg-card text-foreground",
                    )}
                  >
                    {m.text ? renderText(m.text, m.id) : m.streaming ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : null}
                  </div>
                  {m.tools.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1" aria-label="tools used">
                      {m.tools.map((t, i) => (
                        <span
                          key={`${t.name}-${i}`}
                          className={cn(
                            "rounded-full px-2 py-0.5 text-[10px]",
                            t.status === "error" ? "bg-destructive/10 text-destructive" : t.status === "running" ? "bg-muted text-muted-foreground" : "bg-primary/10 text-primary",
                          )}
                        >
                          {t.name.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  )}
                  {m.cards.map((c, i) => (
                    <AssistantCardView key={`${m.id}-c${i}`} card={c} onClose={() => setOpen(false)} />
                  ))}
                  {m.role === "assistant" && m.done && (
                    <div className="mt-1 flex items-center gap-1 text-muted-foreground">
                      <button type="button" aria-label="Helpful" onClick={() => void feedback(m, "up")} className={cn("rounded p-1 hover:text-primary", m.feedback === "up" && "text-primary")}>
                        <ThumbsUp className="h-3.5 w-3.5" />
                      </button>
                      <button type="button" aria-label="Not helpful" onClick={() => void feedback(m, "down")} className={cn("rounded p-1 hover:text-destructive", m.feedback === "down" && "text-destructive")}>
                        <ThumbsDown className="h-3.5 w-3.5" />
                      </button>
                      {m.done.safe_mode ? <span className="text-[10px]">· {lang === "ar" ? "وضع آمن" : "safe mode"}</span> : null}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="flex items-end gap-2 border-t border-border bg-card p-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={1}
              dir="auto"
              disabled={needsConsent || blocked}
              placeholder={lang === "ar" ? "اكتب رسالتك…" : "Type your message…"}
              className="max-h-28 min-h-[40px] flex-1 resize-none rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30 disabled:opacity-50"
            />
            <button
              type="button"
              aria-label="Send message"
              onClick={() => void send()}
              disabled={busy || !input.trim() || needsConsent || blocked}
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </button>
          </div>
        </div>
      )}
    </>
  );
}

export default AssistantWidget;
