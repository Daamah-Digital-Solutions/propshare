import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  ArrowUp,
  Building2,
  Check,
  Copy,
  FileText,
  HelpCircle,
  ImagePlus,
  Lock,
  Loader2,
  Paperclip,
  Maximize2,
  Minimize2,
  Receipt,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Square,
  ThumbsDown,
  ThumbsUp,
  TrendingUp,
  Wallet,
  X,
  type LucideIcon,
} from "lucide-react";
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
import { AssistantCardView, LinkButton } from "@/components/assistant/AssistantCards";
import { saveBlob } from "@/lib/certificates";
import { coveredPaths, greeting, pageStarters, toolLabel } from "@/components/assistant/assistantUi";

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
const TEASER_KEY = "capimax_assistant_teaser_seen";
// a visitor has no account to record consent on: the notice is acknowledged in this browser,
// per policy version, before their first message leaves for the AI provider
const VISITOR_NOTICE_KEY = "capimax_assistant_visitor_notice";

type Role = "user" | "assistant";
/** A picture or a file in a user's message: a picture shows from the local file when just sent
 * (src) or is fetched back from the server (id) when the chat is reopened; a file shows its
 * name and downloads again on a click. */
interface MsgAttachment {
  kind: "image" | "file";
  id?: string;
  src?: string;
  filename: string;
  size?: number;
}
interface Msg {
  id: string;
  role: Role;
  text: string;
  cards: AssistantCard[];
  tools: { name: string; status: "running" | "ok" | "error" }[];
  attachments?: MsgAttachment[];
  done?: TurnDone;
  feedback?: "up" | "down";
  streaming?: boolean;
}

/** Something chosen for the next message: uploading, ready (has the server id) or refused. */
interface PendingAttachment {
  key: string;
  kind: "image" | "file";
  src?: string; // pictures: a local preview
  name: string;
  size: number;
  state: "uploading" | "ready" | "error";
  id?: string;
  error?: string;
}

const PICTURE_TYPES = ["image/png", "image/jpeg", "image/webp"];
// what the server accepts; it checks each file's real content again
const FILE_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".txt"];
const ACCEPT = [...PICTURE_TYPES, ...FILE_EXTENSIONS].join(",");

const isPicture = (file: File) => PICTURE_TYPES.includes(file.type);
const hasFileExtension = (file: File) =>
  FILE_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext));

/** A local preview of a picture, remembered so it can be released with its chat. */
function previewUrl(urls: Set<string>, file: File) {
  const url = URL.createObjectURL(file);
  urls.add(url);
  return url;
}
function dropUrl(urls: Set<string>, url?: string) {
  if (url && urls.delete(url)) URL.revokeObjectURL(url);
}

const fileSize = (bytes?: number) =>
  bytes === undefined
    ? ""
    : bytes < 1024 * 1024
      ? `${Math.max(1, Math.round(bytes / 1024))} KB`
      : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

/** A picture the user sent, shown in their message bubble. */
function ChatPicture({ image }: { image: MsgAttachment }) {
  const [src, setSrc] = useState<string | null>(image.src ?? null);
  useEffect(() => {
    if (image.src || !image.id) return;
    let url: string | null = null;
    let cancelled = false;
    assistantApi
      .attachmentBlob(image.id)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setSrc(url);
      })
      .catch(() => {
        /* gone (purged) or not reachable: the placeholder stays */
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [image.id, image.src]);
  return src ? (
    <img
      src={src}
      alt={image.filename || "Picture you sent"}
      className="max-h-48 w-auto max-w-full rounded-xl border border-white/20 object-contain shadow-sm"
      data-testid="chat-picture"
    />
  ) : (
    <div className="flex h-24 w-32 items-center justify-center rounded-xl border border-border bg-muted text-muted-foreground">
      <ImagePlus className="h-5 w-5" />
    </div>
  );
}

/** A file the user sent: its name and size; a click downloads it again (owner only). */
function ChatFile({ file }: { file: MsgAttachment }) {
  const [busy, setBusy] = useState(false);
  const download = async () => {
    if (!file.id || busy) return;
    setBusy(true);
    try {
      saveBlob(await assistantApi.attachmentBlob(file.id), file.filename);
    } catch {
      /* gone (purged) or not reachable: nothing to download */
    } finally {
      setBusy(false);
    }
  };
  return (
    <button
      type="button"
      onClick={() => void download()}
      disabled={!file.id}
      data-testid="chat-file"
      className="flex max-w-full items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-left text-xs text-foreground shadow-sm transition hover:border-primary/40 disabled:cursor-default"
    >
      {busy ? <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" /> : <FileText className="h-4 w-4 shrink-0 text-primary" />}
      <span className="min-w-0">
        <span className="block truncate font-medium">{file.filename}</span>
        {file.size !== undefined && <span className="block text-[10.5px] text-muted-foreground">{fileSize(file.size)}</span>}
      </span>
    </button>
  );
}

const uid = () =>
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const WELCOME_EN =
  "I'm your PropShare concierge. I can explain how PropShare works, look up your own account and take you to the right page. What do you need?";
const WELCOME_AR =
  "أهلًا! أقدر أشرح لك كيف تعمل Capimax PropShare، وأراجع حسابك، وأوصّلك للصفحة الصحيحة. كيف أساعدك؟";

/** One-tap questions under the welcome message, so nobody faces an empty box. */
const STARTERS: Record<"visitor" | "member", Record<"en" | "ar", string[]>> = {
  visitor: {
    en: ["How does fractional ownership work?", "Show me properties in Dubai", "What fees will I pay?", "How do I start investing?"],
    ar: ["إزاي الملكية الجزئية بتشتغل؟", "وريني العقارات المتاحة في دبي", "إيه الرسوم اللي هدفعها؟", "أبدأ استثمار إزاي؟"],
  },
  member: {
    en: ["What is my balance?", "Show my investments", "I need an account statement", "How do I withdraw my money?"],
    ar: ["رصيدي كام؟", "وريني استثماراتي", "عايز كشف حساب", "أسحب فلوسي إزاي؟"],
  },
};
const STARTER_ICONS: Record<"visitor" | "member", LucideIcon[]> = {
  visitor: [HelpCircle, Building2, Receipt, TrendingUp],
  member: [Wallet, TrendingUp, FileText, Receipt],
};

/** A visitor sees the way in from the first message, not only after asking. */
const VISITOR_WELCOME_CARDS: AssistantCard[] = [
  { kind: "link", path: "/auth", label: "Sign in" },
  { kind: "link", path: "/auth?tab=register", label: "Create a free account" },
];

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
  // the page the user has open travels with each message ("this property", "my wallet here")
  const location = useLocation();
  const page = `${location.pathname}${location.search}`;
  const identity = isAuthenticated ? (user?.id ?? "user") : "visitor";
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [teaser, setTeaser] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [status, setStatus] = useState<AssistantStatus>(initialStatus);
  const [chosenLang, setLang] = useState<"en" | "ar">(() => {
    try {
      return (localStorage.getItem(LANG_KEY) as "en" | "ar") || "en";
    } catch {
      return "en";
    }
  });
  const englishOnly = status.reply_language === "en";
  const lang: "en" | "ar" = englishOnly ? "en" : chosenLang;
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [consenting, setConsenting] = useState(false);
  const [visitorNoticed, setVisitorNoticed] = useState(() => {
    try {
      return localStorage.getItem(VISITOR_NOTICE_KEY) === initialStatus.policy_version;
    } catch {
      return false; // no storage: ask each visit
    }
  });
  const [error, setError] = useState<string>("");
  const [pending, setPending] = useState<PendingAttachment[]>([]);
  const [dragging, setDragging] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // what is chosen right now, ahead of the next render: two picks in a row must see each other
  const pendingRef = useRef<PendingAttachment[]>([]);
  // the first message or attachment creates the conversation: everything at once shares it
  const creatingRef = useRef<Promise<string> | null>(null);
  // local previews of pictures (in the composer and in sent bubbles), released with the chat
  const urlsRef = useRef<Set<string>>(new Set());
  // pictures and files: signed-in users, when the platform offers them (status.attachments)
  const attach = isAuthenticated ? (status.attachments ?? null) : null;

  const welcome = useCallback(
    (): Msg => ({
      id: "welcome",
      role: "assistant",
      text: lang === "ar" ? WELCOME_AR : WELCOME_EN,
      cards: isAuthenticated ? [] : VISITOR_WELCOME_CARDS,
      tools: [],
    }),
    [lang, isAuthenticated],
  );

  useEffect(() => {
    const seen = () => {
      try {
        return localStorage.getItem(TEASER_KEY) === "1";
      } catch {
        return true; // no storage: stay quiet
      }
    };
    if (seen() || !initialStatus.enabled) return;
    // re-checked when the timer fires: the panel may have been opened in the meantime
    const t = setTimeout(() => {
      if (!seen()) setTeaser(true);
    }, 4000);
    return () => clearTimeout(t);
  }, [initialStatus.enabled]);

  const dismissTeaser = useCallback(() => {
    setTeaser(false);
    try {
      localStorage.setItem(TEASER_KEY, "1");
    } catch {
      /* non-fatal */
    }
  }, []);

  const openPanel = useCallback(() => {
    dismissTeaser();
    setOpen(true);
  }, [dismissTeaser]);

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
            creatingRef.current = null;
            setConversationId(key);
            // the bubbles come back from the server: local previews only stay for the composer
            releaseUrls(pendingRef.current.map((p) => p.src));
            setMessages(
              history.length
                ? history.map((m) => ({
                    id: m.id,
                    role: m.role,
                    text: m.text ?? "",
                    cards: m.cards ?? [],
                    tools: [],
                    attachments: (m.attachments ?? []).map((a) => ({
                      kind: a.kind,
                      id: a.id,
                      filename: a.filename,
                      size: a.size_bytes,
                    })),
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
          creatingRef.current = null;
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
    if (open) scrollRef.current?.scrollTo?.({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [open, messages, busy]);

  useEffect(() => {
    pendingRef.current = pending;
  }, [pending]);

  /** Release the local previews nothing shows any more (the chat they were in is gone). */
  const releaseUrls = useCallback((keep: (string | undefined)[] = []) => {
    urlsRef.current.forEach((url) => {
      if (!keep.includes(url)) {
        URL.revokeObjectURL(url);
        urlsRef.current.delete(url);
      }
    });
  }, []);
  useEffect(() => () => releaseUrls(), [releaseUrls]);

  // Focus the box when the panel opens and when a reply has finished: not on every streamed
  // word, and never on a touch screen, where focusing pops the keyboard over the reply.
  useEffect(() => {
    if (!open || busy) return;
    const touch = typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;
    if (!touch) inputRef.current?.focus();
  }, [open, busy]);

  const ensureConversation = useCallback(async (): Promise<string> => {
    if (conversationId) return conversationId;
    // several pictures picked at once (or a picture and the message) share ONE new conversation
    creatingRef.current ??= assistantApi.createConversation().then(
      (conv) => {
        setConversationId(conv.id);
        try {
          localStorage.setItem(`${CONV_KEY}:${identity}`, conv.id);
        } catch {
          /* non-fatal */
        }
        return conv.id;
      },
      (err: unknown) => {
        creatingRef.current = null;
        throw err;
      },
    );
    return creatingRef.current;
  }, [conversationId, identity]);

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    creatingRef.current = null;
    setConversationId(null);
    try {
      localStorage.removeItem(`${CONV_KEY}:${identity}`);
    } catch {
      /* non-fatal */
    }
    setMessages([welcome()]);
    setInput("");
    setError("");
    // uploaded and never sent: off the server too, so nothing waits for the nightly purge
    for (const p of pendingRef.current) {
      if (p.id) void assistantApi.deleteAttachment(p.id).catch(() => undefined);
    }
    pendingRef.current = [];
    setPending([]);
    releaseUrls();
  }, [identity, welcome, releaseUrls]);

  /** Pictures and files picked, pasted or dropped: checked here first, then uploaded straight
   * away so the message goes out as soon as the user presses send. */
  const addAttachments = useCallback(
    async (files: File[]) => {
      if (!attach || !files.length) return;
      setError("");
      const room = attach.per_message - pendingRef.current.length;
      if (room <= 0) {
        setError(`You can send up to ${attach.per_message} files with a message.`);
        return;
      }
      if (files.length > room) setError(`Only ${attach.per_message} files fit in one message.`);
      const chosen = files.slice(0, room);
      const fresh: PendingAttachment[] = chosen.map((file) => {
        const picture = isPicture(file);
        const problem =
          !picture && !hasFileExtension(file)
            ? "Send a picture, a PDF, a Word, Excel or PowerPoint file, or a CSV or text file."
            : file.size > attach.max_mb * 1024 * 1024
              ? `A file can be up to ${attach.max_mb} MB.`
              : undefined;
        return {
          key: uid(),
          kind: picture ? "image" : "file",
          src: picture ? previewUrl(urlsRef.current, file) : undefined,
          name: file.name || (picture ? "picture" : "file"),
          size: file.size,
          state: problem ? "error" : "uploading",
          error: problem,
        };
      });
      // taken now, not at the next render: a second pick right after must see these
      pendingRef.current = [...pendingRef.current, ...fresh];
      setPending((prev) => [...prev, ...fresh]);
      const update = (key: string, patch: Partial<PendingAttachment>) =>
        setPending((prev) => prev.map((p) => (p.key === key ? { ...p, ...patch } : p)));
      let cid: string;
      try {
        cid = await ensureConversation();
      } catch (err) {
        fresh.forEach((p) => update(p.key, { state: "error", error: err instanceof ApiError ? err.message : "Upload failed." }));
        return;
      }
      await Promise.all(
        chosen.map(async (file, i) => {
          const p = fresh[i];
          if (p.state === "error") return;
          try {
            const att = await assistantApi.uploadAttachment(cid, file);
            if (!pendingRef.current.some((x) => x.key === p.key)) {
              // taken off while it was uploading: off the server too, so its slot frees up
              void assistantApi.deleteAttachment(att.id).catch(() => undefined);
              return;
            }
            // the server says what the file really is and the name it keeps
            update(p.key, { state: "ready", id: att.id, kind: att.kind, name: att.filename });
          } catch (err) {
            update(p.key, { state: "error", error: err instanceof ApiError ? err.message : "Upload failed." });
          }
        }),
      );
    },
    [attach, ensureConversation],
  );

  const removeAttachment = useCallback((key: string) => {
    const gone = pendingRef.current.find((p) => p.key === key);
    if (!gone) return;
    pendingRef.current = pendingRef.current.filter((p) => p.key !== key);
    setPending((prev) => prev.filter((p) => p.key !== key));
    dropUrl(urlsRef.current, gone.src);
    // already uploaded: off the server too, so its slot frees up for another file
    if (gone.id) void assistantApi.deleteAttachment(gone.id).catch(() => undefined);
  }, []);

  const onPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!attach) return;
    const files = Array.from(e.clipboardData?.files ?? []);
    if (files.length) {
      e.preventDefault();
      void addAttachments(files);
    }
  };

  const acknowledgeVisitorNotice = useCallback(() => {
    setVisitorNoticed(true);
    try {
      localStorage.setItem(VISITOR_NOTICE_KEY, status.policy_version);
    } catch {
      /* non-fatal: asked again next visit */
    }
  }, [status.policy_version]);

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

  const send = useCallback(async (preset?: string) => {
    const text = (preset ?? input).trim();
    // a starter chip sends its own text only; the box sends its text and the attachments with it
    const attached = preset === undefined ? pending.filter((p) => p.state === "ready" && p.id) : [];
    if ((!text && !attached.length) || busy) return;
    if (preset === undefined && pending.some((p) => p.state === "uploading")) return;
    setError("");
    const turnLang: "en" | "ar" = englishOnly ? "en" : isArabic(text) ? "ar" : lang;
    const userMsg: Msg = {
      id: uid(),
      role: "user",
      text,
      cards: [],
      tools: [],
      attachments: attached.map((p) => ({ kind: p.kind, id: p.id, src: p.src, filename: p.name, size: p.size })),
    };
    const reply: Msg = { id: uid(), role: "assistant", text: "", cards: [], tools: [], streaming: true };
    setMessages((prev) => [...prev, userMsg, reply]);
    setInput("");
    if (preset === undefined) {
      // sent attachments live on in the message bubble (unless the server does not take them)
      pendingRef.current = [];
      setPending([]);
    }
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const patch = (fn: (m: Msg) => Msg) =>
      setMessages((prev) => prev.map((m) => (m.id === reply.id ? fn(m) : m)));
    let accepted = false; // the server stored the message, and took its attachments with it
    let refusal: string | undefined;
    try {
      const cid = await ensureConversation();
      const ids = attached.flatMap((p) => (p.id ? [p.id] : []));
      for await (const ev of sendMessage(cid, text, turnLang, controller.signal, page, ids)) {
        // anything but an error comes only after the server stored the message
        if (ev.event !== "error") accepted = true;
        if (ev.event === "delta") patch((m) => ({ ...m, text: m.text + ev.data.text }));
        else if (ev.event === "reset") patch((m) => ({ ...m, text: "" }));
        else if (ev.event === "tool")
          patch((m) => {
            const tools = m.tools.filter((t) => t.name !== ev.data.name || ev.data.status === "running");
            return { ...m, tools: [...tools, ev.data] };
          });
        else if (ev.event === "card") patch((m) => ({ ...m, cards: [...m.cards, ev.data] }));
        else if (ev.event === "done") patch((m) => ({ ...m, done: ev.data, streaming: false }));
        else if (ev.event === "error") {
          refusal = ev.data.code;
          patch((m) => ({ ...m, text: m.text || ev.data.message, streaming: false }));
        }
      }
      patch((m) => ({ ...m, streaming: false }));
    } catch (err) {
      if (err instanceof ApiError) refusal = err.code;
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
      // not taken (a limit, the network): the attachments go back to the composer to send
      // again, instead of being lost, unless the server no longer has them
      if (!accepted && attached.length && refusal !== "ATTACHMENT_NOT_FOUND") {
        setMessages((prev) => prev.map((m) => (m.id === userMsg.id ? { ...m, attachments: [] } : m)));
        pendingRef.current = [...attached, ...pendingRef.current];
        setPending((prev) => [...attached, ...prev]);
      }
    }
  }, [input, pending, busy, lang, englishOnly, ensureConversation, page]);

  const copyText = useCallback(async (m: Msg) => {
    try {
      await navigator.clipboard.writeText(m.text);
      setCopied(m.id);
      setTimeout(() => setCopied((c) => (c === m.id ? null : c)), 1500);
    } catch {
      /* clipboard blocked: nothing to do */
    }
  }, []);

  const stop = useCallback(() => abortRef.current?.abort(), []);

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

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [input]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const dir = lang === "ar" ? "rtl" : "ltr";
  // only when the platform asks for a notice (off by default: the Privacy Policy covers it)
  const needsVisitorNotice =
    !isAuthenticated && status.enabled && Boolean(status.privacy_notice) && !visitorNoticed;
  const needsConsent = (isAuthenticated && status.consent_required) || needsVisitorNotice;
  const blocked = !status.enabled && !needsConsent;

  const firstName = (user?.full_name ?? "").trim().split(/\s+/)[0] || null;
  const showHero = messages.length === 1 && messages[0]?.id === "welcome" && !needsConsent && !blocked;
  const starterSet = isAuthenticated ? "member" : "visitor";
  const onPage = pageStarters(location.pathname, location.search, isAuthenticated);
  const starterLang = lang === "ar" ? "ar" : "en";
  const starters = onPage ? onPage[starterLang] : STARTERS[starterSet][starterLang];
  const starterIcons = onPage ? onPage.icons : STARTER_ICONS[starterSet];
  const running = (m: Msg) => [...m.tools].reverse().find((t) => t.status === "running");

  return (
    <>
      {!open && (
        <div className="fixed bottom-[calc(5rem_+_env(safe-area-inset-bottom))] right-4 z-[60] flex flex-col items-end gap-2 lg:bottom-5 lg:right-5">
          {teaser && (
            <div className="relative max-w-[250px] animate-in fade-in slide-in-from-bottom-2 rounded-2xl border border-border bg-card px-4 py-3 text-sm shadow-xl duration-500">
              <button
                type="button"
                aria-label="Dismiss"
                onClick={dismissTeaser}
                className="absolute right-1.5 top-1.5 rounded-full p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-3 w-3" />
              </button>
              <div className="pr-4 font-semibold text-foreground">Questions about investing?</div>
              <div className="mt-0.5 text-xs text-muted-foreground">
                Ask me about properties, fees or your account. I answer in seconds.
              </div>
            </div>
          )}
          <button
            type="button"
            aria-label="Open PropShare assistant"
            onClick={openPanel}
            className="group relative flex h-14 items-center gap-2.5 rounded-full bg-[linear-gradient(135deg,hsl(152_69%_24%),hsl(158_62%_36%))] pl-2 pr-2 text-white shadow-[0_14px_34px_-10px_hsl(152_69%_20%/0.75)] ring-1 ring-white/10 transition hover:-translate-y-0.5 hover:shadow-[0_18px_40px_-10px_hsl(152_69%_20%/0.85)] active:translate-y-0 sm:pr-5"
          >
            <span className="relative flex h-10 w-10 items-center justify-center rounded-full bg-white/15 ring-1 ring-white/20">
              <Sparkles className="h-5 w-5" />
              <span className="absolute -right-0.5 -top-0.5 flex h-3 w-3">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
                <span className="relative inline-flex h-3 w-3 rounded-full border-2 border-[hsl(152_69%_26%)] bg-accent" />
              </span>
            </span>
            <span className="hidden text-sm font-semibold tracking-tight sm:inline">Ask PropShare AI</span>
          </button>
        </div>
      )}

      {open && (
        <div
          role="dialog"
          aria-label="PropShare assistant"
          dir={dir}
          onDragOver={(e) => {
            if (!attach || !Array.from(e.dataTransfer?.types ?? []).includes("Files")) return;
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={(e) => {
            if (e.currentTarget === e.target) setDragging(false);
          }}
          onDrop={(e) => {
            if (!attach) return;
            e.preventDefault();
            setDragging(false);
            void addAttachments(Array.from(e.dataTransfer?.files ?? []));
          }}
          className={cn(
            "fixed inset-0 z-[60] flex animate-in fade-in slide-in-from-bottom-4 flex-col overflow-hidden bg-background duration-300",
            "sm:inset-auto sm:bottom-5 sm:right-5 sm:rounded-3xl sm:border sm:border-border sm:shadow-[0_30px_80px_-20px_rgba(0,0,0,0.35)]",
            expanded ? "sm:h-[88vh] sm:w-[min(720px,calc(100vw-2.5rem))]" : "sm:h-[min(720px,85vh)] sm:w-[420px]",
            dragging && "ring-4 ring-primary/40",
          )}
        >
          {/* header */}
          <div className="relative overflow-hidden bg-[linear-gradient(135deg,hsl(152_69%_18%),hsl(156_64%_30%))] px-4 pb-3.5 pt-[calc(0.875rem_+_env(safe-area-inset-top))] text-white sm:pt-3.5">
            <div className="pointer-events-none absolute -right-10 -top-16 h-40 w-40 rounded-full bg-white/10 blur-2xl" />
            <div className="pointer-events-none absolute -bottom-12 left-10 h-24 w-24 rounded-full bg-accent/20 blur-2xl" />
            <div className="relative flex items-center gap-3">
              <div className="relative flex h-10 w-10 items-center justify-center rounded-2xl bg-white/15 ring-1 ring-white/25 backdrop-blur">
                <Sparkles className="h-5 w-5" />
                <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-[hsl(154_66%_24%)] bg-emerald-300" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[15px] font-semibold leading-tight tracking-tight">PropShare AI Concierge</div>
                <div className="mt-0.5 text-[11px] text-white/75">
                  {lang === "ar" ? "Capimax PropShare · متصل" : "Capimax PropShare · Online"}
                </div>
              </div>
              {!englishOnly && (
                <button type="button" aria-label="Switch language" title="EN / AR" onClick={toggleLang} className="rounded-lg px-2 py-1.5 text-xs font-semibold text-white/90 hover:bg-white/15">
                  {lang === "en" ? "ع" : "EN"}
                </button>
              )}
              <button type="button" aria-label={expanded ? "Shrink" : "Expand"} title={expanded ? "Shrink" : "Expand"} onClick={() => setExpanded((v) => !v)} className="hidden rounded-lg p-2 text-white/90 hover:bg-white/15 sm:inline-flex">
                {expanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </button>
              <button type="button" aria-label="New chat" title="New chat" onClick={newChat} className="rounded-lg p-2 text-white/90 hover:bg-white/15">
                <RefreshCw className="h-4 w-4" />
              </button>
              <button type="button" aria-label="Close chat" onClick={() => setOpen(false)} className="rounded-lg p-2 text-white/90 hover:bg-white/15">
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div className="h-px bg-gradient-to-r from-transparent via-accent/70 to-transparent" />

          {/* conversation */}
          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto bg-gradient-to-b from-muted/40 via-background to-background px-4 py-4">
            {needsConsent && (
              <div className="rounded-2xl border border-border bg-card p-4 text-sm shadow-sm" data-testid="consent-gate">
                <div className="flex items-center gap-2 font-semibold">
                  <Lock className="h-4 w-4 text-primary" />
                  {lang === "ar" ? "قبل أن نبدأ" : "Before we start"}
                </div>
                <p className="mt-1.5 text-muted-foreground">
                  {needsVisitorNotice
                    ? lang === "ar"
                      ? "يرسل المساعد رسائلك إلى مزوّد ذكاء اصطناعي خارجي (OpenAI) ليجيب عنها. لا تكتب بيانات شخصية أو بيانات دفع. اقرأ "
                      : "The assistant sends your messages to an external AI provider (OpenAI) to answer them. Please don't share personal or payment details. Read the "
                    : lang === "ar"
                      ? "يرسل المساعد رسائلك، وبيانات حسابك التي يحتاجها ليجيب (مثل اسمك وحالة التحقق وأرصدتك وعملياتك)، إلى مزوّد ذكاء اصطناعي خارجي (OpenAI). تُحفظ محادثاتك مشفّرة. اقرأ "
                      : "The assistant sends your messages, and the account details it needs to answer them (such as your name, verification status, balances and transactions), to an external AI provider (OpenAI). Your conversations are stored encrypted. Read the "}
                  <a href="/privacy#ai-assistant" className="text-primary underline" target="_blank" rel="noreferrer">
                    {lang === "ar" ? "سياسة الخصوصية" : "Privacy Policy"}
                  </a>
                  {lang === "ar" ? " (الإصدار " : " (version "}
                  {status.policy_version}).
                </p>
                <button
                  type="button"
                  onClick={() => (needsVisitorNotice ? acknowledgeVisitorNotice() : void giveConsent())}
                  disabled={consenting}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-sm disabled:opacity-50"
                >
                  {consenting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                  {needsVisitorNotice
                    ? lang === "ar" ? "فهمت، أكمل" : "I understand, continue"
                    : lang === "ar" ? "أوافق وأكمل" : "I agree, continue"}
                </button>
              </div>
            )}
            {blocked && (
              <div className="rounded-2xl border border-border bg-card p-4 text-sm text-muted-foreground" data-testid="assistant-unavailable">
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
            {error && <div className="rounded-xl bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</div>}

            {showHero && (
              <div className="animate-in fade-in slide-in-from-bottom-2 duration-500" data-testid="assistant-hero">
                <div className="flex flex-col items-center pt-2 text-center">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,hsl(152_69%_24%),hsl(158_62%_38%))] text-white shadow-[0_12px_30px_-12px_hsl(152_69%_20%/0.9)]">
                    <Sparkles className="h-7 w-7" />
                  </div>
                  <div className="mt-3 text-lg font-semibold tracking-tight text-foreground">
                    {greeting(isAuthenticated ? firstName : null)}
                  </div>
                  <p dir="auto" className="mt-1 max-w-[320px] text-sm leading-relaxed text-muted-foreground">
                    {messages[0].text}
                  </p>
                  <div className="mt-3 flex flex-wrap justify-center gap-1.5 text-[10.5px] text-muted-foreground">
                    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-2 py-0.5">
                      <Wallet className="h-3 w-3 text-primary" /> Live account data
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-2 py-0.5">
                      <ShieldCheck className="h-3 w-3 text-primary" /> Nothing happens without your OK
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-2 py-0.5">
                      <Lock className="h-3 w-3 text-primary" /> Encrypted
                    </span>
                  </div>
                </div>
                {messages[0].cards.length > 0 && (
                  <div className="mt-4 flex flex-wrap justify-center gap-2">
                    {messages[0].cards.map((c, i) =>
                      c.kind === "link" ? (
                        <LinkButton key={c.path} card={c} primary={i === 0} onClose={() => setOpen(false)} />
                      ) : null,
                    )}
                  </div>
                )}
                <div className="mt-5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {onPage ? onPage.title[starterLang] : lang === "ar" ? "اقتراحات" : "Try asking"}
                </div>
                <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2" data-testid="assistant-starters">
                  {starters.map((q, i) => {
                    const Icon = starterIcons[i] ?? Sparkles;
                    return (
                      <button
                        key={q}
                        type="button"
                        dir="auto"
                        disabled={busy}
                        onClick={() => void send(q)}
                        className="group flex items-center gap-2.5 rounded-2xl border border-border bg-card px-3 py-2.5 text-left text-xs font-medium text-foreground shadow-sm transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md disabled:opacity-50 rtl:text-right"
                      >
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary transition group-hover:bg-primary group-hover:text-primary-foreground">
                          <Icon className="h-4 w-4" />
                        </span>
                        {q}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {!showHero &&
              // the welcome only lives on the hero screen; once the chat starts it steps aside
              messages.filter((m) => m.id !== "welcome").map((m) => {
                // a page a card already opens does not get a second, button-shaped link
                const tiled = new Set(m.cards.flatMap(coveredPaths));
                const links = m.cards.filter((c) => c.kind === "link" && !tiled.has(c.path));
                // an order or a comparison is the focus of its reply: property previews are noise
                const focus = m.cards.some((c) => c.kind === "checkout" || c.kind === "comparison");
                const others = m.cards.filter(
                  (c) => c.kind !== "link" && !(focus && (c.kind === "property" || c.kind === "properties")),
                );
                const busyTool = m.streaming ? running(m) : undefined;
                const finished = m.tools.filter((t) => t.status !== "running");
                return (
                  <div
                    key={m.id}
                    className={cn("flex animate-in fade-in slide-in-from-bottom-1 gap-2.5 duration-300", m.role === "user" ? "justify-end" : "justify-start")}
                  >
                    {m.role === "assistant" && (
                      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-[linear-gradient(135deg,hsl(152_69%_24%),hsl(158_62%_38%))] text-white shadow-sm">
                        <Sparkles className="h-3.5 w-3.5" />
                      </div>
                    )}
                    <div className={cn("group min-w-0", m.role === "user" ? "max-w-[82%]" : "max-w-[calc(100%-2.5rem)] flex-1")}>
                      {m.attachments && m.attachments.length > 0 && (
                        <div className="mb-1.5 flex flex-wrap justify-end gap-1.5">
                          {m.attachments.map((a, i) =>
                            a.kind === "image" ? (
                              <ChatPicture key={a.id ?? a.src ?? i} image={a} />
                            ) : (
                              <ChatFile key={a.id ?? i} file={a} />
                            ),
                          )}
                        </div>
                      )}
                      {(m.text || (!m.streaming && m.role === "assistant")) && (
                        <div
                          dir="auto"
                          className={cn(
                            "text-[13.5px] leading-relaxed",
                            m.role === "user"
                              ? "rounded-2xl rounded-tr-md bg-[linear-gradient(135deg,hsl(152_69%_28%),hsl(156_60%_36%))] px-3.5 py-2.5 text-white shadow-sm"
                              : "rounded-2xl rounded-tl-md border border-border/70 bg-card px-3.5 py-2.5 text-foreground shadow-sm",
                          )}
                        >
                          {renderText(m.text, m.id)}
                        </div>
                      )}
                      {m.streaming && !m.text && (
                        <div className="inline-flex items-center gap-2.5 rounded-2xl rounded-tl-md border border-border/70 bg-card px-3.5 py-3 shadow-sm">
                          <span className="flex gap-1">
                            {[0, 1, 2].map((d) => (
                              <span
                                key={d}
                                className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary/70"
                                style={{ animationDelay: `${d * 150}ms` }}
                              />
                            ))}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {busyTool ? toolLabel(busyTool.name, "running") : lang === "ar" ? "يفكّر…" : "Thinking…"}
                          </span>
                        </div>
                      )}
                      {m.role === "assistant" && finished.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1" aria-label="tools used">
                          {finished.map((t, i) => (
                            <span
                              key={`${t.name}-${i}`}
                              className={cn(
                                "inline-flex items-center gap-1 text-[10.5px]",
                                t.status === "error" ? "text-destructive" : "text-muted-foreground",
                              )}
                            >
                              {t.status === "error" ? <X className="h-3 w-3" /> : <Check className="h-3 w-3 text-primary" />}
                              {toolLabel(t.name, t.status)}
                            </span>
                          ))}
                        </div>
                      )}
                      {others.map((c, i) => (
                        <AssistantCardView key={`${m.id}-c${i}`} card={c} onClose={() => setOpen(false)} />
                      ))}
                      {links.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {links.map((c, i) =>
                            c.kind === "link" ? (
                              <LinkButton key={`${m.id}-l${c.path}`} card={c} primary={i === 0} onClose={() => setOpen(false)} />
                            ) : null,
                          )}
                        </div>
                      )}
                      {m.role === "assistant" && m.done && (
                        <div className="mt-1.5 flex items-center gap-0.5 text-muted-foreground opacity-70 transition group-hover:opacity-100">
                          <button type="button" aria-label="Copy" title="Copy" onClick={() => void copyText(m)} className="rounded-md p-1 hover:bg-muted hover:text-foreground">
                            {copied === m.id ? <Check className="h-3.5 w-3.5 text-primary" /> : <Copy className="h-3.5 w-3.5" />}
                          </button>
                          <button type="button" aria-label="Helpful" onClick={() => void feedback(m, "up")} className={cn("rounded-md p-1 hover:bg-muted hover:text-primary", m.feedback === "up" && "text-primary")}>
                            <ThumbsUp className="h-3.5 w-3.5" />
                          </button>
                          <button type="button" aria-label="Not helpful" onClick={() => void feedback(m, "down")} className={cn("rounded-md p-1 hover:bg-muted hover:text-destructive", m.feedback === "down" && "text-destructive")}>
                            <ThumbsDown className="h-3.5 w-3.5" />
                          </button>
                          {m.done.safe_mode ? <span className="ms-1 text-[10px]">· {lang === "ar" ? "وضع آمن" : "safe mode"}</span> : null}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
          </div>

          {/* composer */}
          <div className="border-t border-border/70 bg-background px-3 pb-[calc(0.75rem_+_env(safe-area-inset-bottom))] pt-3 sm:pb-3">
            {pending.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-2" data-testid="pending-attachments">
                {pending.map((p) => (
                  <div key={p.key} className={cn("relative", p.kind === "file" && "max-w-[200px]")}>
                    {p.kind === "image" ? (
                      <img
                        src={p.src}
                        alt={p.name}
                        className={cn(
                          "h-16 w-16 rounded-xl border object-cover",
                          p.state === "error" ? "border-destructive/60 opacity-60" : "border-border",
                        )}
                      />
                    ) : (
                      <div
                        className={cn(
                          "flex h-16 items-center gap-2 rounded-xl border bg-card px-3 pr-5 text-xs",
                          p.state === "error" ? "border-destructive/60 opacity-60" : "border-border",
                        )}
                      >
                        <FileText className="h-5 w-5 shrink-0 text-primary" />
                        <span className="min-w-0">
                          <span className="block truncate font-medium text-foreground">{p.name}</span>
                          <span className="block text-[10.5px] text-muted-foreground">{fileSize(p.size)}</span>
                        </span>
                      </div>
                    )}
                    {p.state === "uploading" && (
                      <span className="absolute inset-0 flex items-center justify-center rounded-xl bg-background/60">
                        <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      </span>
                    )}
                    <button
                      type="button"
                      aria-label={`Remove ${p.name}`}
                      onClick={() => removeAttachment(p.key)}
                      className="absolute -right-1.5 -top-1.5 rounded-full border border-border bg-background p-0.5 text-muted-foreground shadow-sm hover:text-foreground"
                    >
                      <X className="h-3 w-3" />
                    </button>
                    {p.state === "error" && (
                      <div className={cn("mt-0.5 text-[9.5px] leading-tight text-destructive", p.kind === "image" ? "w-16" : "w-full")}>
                        {p.error}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            <div className="flex items-end gap-2 rounded-2xl border border-border bg-card p-1.5 pl-3 shadow-sm transition focus-within:border-primary/50 focus-within:shadow-[0_0_0_4px_hsl(var(--primary)/0.12)]">
              {attach && (
                <>
                  <input
                    ref={fileRef}
                    type="file"
                    accept={ACCEPT}
                    multiple
                    hidden
                    data-testid="attachment-input"
                    onChange={(e) => {
                      void addAttachments(Array.from(e.target.files ?? []));
                      e.target.value = ""; // the same file can be picked again
                    }}
                  />
                  <button
                    type="button"
                    aria-label="Attach a file or picture"
                    title={
                      lang === "ar"
                        ? "أرفق صورة أو ملف (PDF، Word، Excel…)"
                        : "Attach a picture or a file (PDF, Word, Excel, PowerPoint, CSV, text)"
                    }
                    onClick={() => fileRef.current?.click()}
                    disabled={needsConsent || blocked || busy || pending.length >= attach.per_message}
                    className="-ml-1.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-muted-foreground transition hover:bg-muted hover:text-primary disabled:opacity-40"
                  >
                    <Paperclip className="h-4 w-4" />
                  </button>
                </>
              )}
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                onPaste={onPaste}
                rows={1}
                dir="auto"
                disabled={needsConsent || blocked}
                placeholder={lang === "ar" ? "اكتب رسالتك…" : "Type your message…"}
                className="max-h-[140px] min-h-[36px] flex-1 resize-none bg-transparent py-2 text-sm outline-none placeholder:text-muted-foreground/80 disabled:opacity-50"
              />
              {busy ? (
                <button
                  type="button"
                  aria-label="Stop generating"
                  onClick={stop}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-foreground text-background transition hover:opacity-90"
                >
                  <Square className="h-3.5 w-3.5 fill-current" />
                </button>
              ) : (
                <button
                  type="button"
                  aria-label="Send message"
                  onClick={() => void send()}
                  disabled={
                    (!input.trim() && !pending.some((p) => p.state === "ready")) ||
                    pending.some((p) => p.state === "uploading") ||
                    needsConsent ||
                    blocked
                  }
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[linear-gradient(135deg,hsl(152_69%_26%),hsl(158_62%_38%))] text-white shadow-sm transition hover:brightness-110 disabled:opacity-40"
                >
                  <ArrowUp className="h-4 w-4" />
                </button>
              )}
            </div>
            <div className="mt-2 flex items-center justify-center gap-1 text-[10.5px] text-muted-foreground">
              <Lock className="h-3 w-3" />
              {lang === "ar"
                ? "مساعد ذكاء اصطناعي — راجع التفاصيل المهمة قبل أي قرار"
                : "AI assistant — double-check important details before you decide."}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default AssistantWidget;
