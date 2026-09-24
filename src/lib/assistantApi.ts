// Assistant v2 API client (plan Phase 1 §6). Talks to /api/v1/assistant + /api/v1/support.
//
// Identity: a signed-in user sends the in-memory bearer token (same as every other call);
// a visitor sends a browser-generated X-Visitor-Key (persisted in localStorage) — it groups
// their conversations and nothing else. The feature is off unless VITE_ASSISTANT_V2=true AND
// the backend reports `enabled` for this caller (kill switch, rollout, consent).

import { ApiError, apiRequest, apiUrl, getAccessToken, refreshAccessToken } from "@/lib/api";

export const ASSISTANT_V2_FLAG = String(import.meta.env.VITE_ASSISTANT_V2 ?? "") === "true";

const VISITOR_KEY = "capimax_assistant_visitor_key";

export function visitorKey(): string {
  try {
    const existing = localStorage.getItem(VISITOR_KEY);
    if (existing && /^[A-Za-z0-9_-]{16,128}$/.test(existing)) return existing;
    const fresh = `v-${crypto.randomUUID().replace(/-/g, "")}`;
    localStorage.setItem(VISITOR_KEY, fresh);
    return fresh;
  } catch {
    // no storage (private mode, blocked site data): still ONE key for this page session, or
    // every request would look like a new visitor and lose its own conversation
    memoryVisitorKey ??= `v-${Date.now().toString(16)}${Math.random().toString(16).slice(2, 14)}`;
    return memoryVisitorKey;
  }
}

let memoryVisitorKey: string | null = null;

function identityHeaders(): Record<string, string> {
  return getAccessToken() ? {} : { "X-Visitor-Key": visitorKey() };
}

// ---- types (mirrors app/schemas/assistant.py) ----
export interface AssistantStatus {
  enabled: boolean;
  reason: string | null;
  provider: string;
  model_configured: boolean;
  encryption: "ok" | "missing";
  policy_version: string;
  consent_required: boolean;
  consent_given: boolean;
  visitor_allowed: boolean;
  rollout: string;
  /** "en": the assistant answers in English only, so the widget stays English. */
  reply_language?: "auto" | "en";
  /** show a notice before the first message (platform setting assistant_consent_required) */
  privacy_notice?: boolean;
}

export interface Conversation {
  id: string;
  title: string | null;
  status: string;
  lang: string;
  message_count: number;
  created_at: string;
  last_message_at: string | null;
}

export type CardKind = AssistantCard["kind"];
export interface LinkCard {
  kind: "link";
  path: string;
  label: string;
}
export interface PropertyCard {
  kind: "property";
  slug: string;
  title: string | null;
  city?: string | null;
  image?: string | null;
  path: string;
}
export interface PropertiesCard {
  kind: "properties";
  items: {
    slug: string | null;
    title: string | null;
    city: string | null;
    status: string | null;
    unit_price: number | null;
    expected_yield: number | null;
    image?: string | null;
    path: string | null;
  }[];
}
export interface ConfirmActionCard {
  kind: "confirm_action";
  proposal_id: string;
  action: string;
  summary: string;
  token?: string;
  expires_at?: string;
}
/** An order prepared by the assistant: opens the property checkout pre-filled, stops at payment. */
export interface CheckoutCard {
  kind: "checkout";
  title: string | null;
  units: number;
  unit_price: string | null;
  subtotal: string | null;
  platform_fee: string | null;
  total_now: string | null;
  purchase_type: "direct" | "installment" | string | null;
  duration_months: number | null;
  notes: string[];
  ready: boolean;
  path: string;
}
/** A deposit prepared by the assistant: opens the wallet with amount + method filled in. */
export interface DepositCard {
  kind: "deposit";
  amount: string;
  currency: string;
  method: "card" | "crypto" | "bank";
  method_label: string;
  notes: string[];
  ready: boolean;
  path: string;
}
/** A withdrawal prepared by the assistant: fee and net worked out, opens the wallet filled in. */
export interface WithdrawalCard {
  kind: "withdrawal";
  amount: string;
  currency: string;
  method: "bank" | "crypto";
  speed: "standard" | "instant";
  fee: string;
  net_amount: string;
  destination: string | null;
  timing: string | null;
  notes: string[];
  ready: boolean;
  path: string;
}
/** An account statement for a period: the card downloads the PDF / Excel file directly. */
export interface StatementCard {
  kind: "statement";
  start: string;
  end: string;
  format: "pdf" | "xlsx";
  movements: number;
  currency: string;
  opening_balance: string;
  closing_balance: string;
  money_in: string;
  money_out: string;
  path: string;
}
/** A secondary-market sale prepared by the assistant: opens the Sell form filled in. */
export interface SaleCard {
  kind: "sale";
  property_title: string;
  units: number;
  price_per_unit: string;
  reference_price: string;
  vs_reference_pct: string;
  you_receive: string;
  resale_fee_pct: string;
  buyer_fee: string;
  buyer_pays: string;
  notes: string[];
  ready: boolean;
  path: string;
}
/** The next installment, prepared: opens that payment's confirmation in the plan. */
export interface InstallmentCard {
  kind: "installment";
  property_title: string;
  label: string;
  due_date: string;
  status: "scheduled" | "overdue" | string;
  base_amount: string;
  fee_amount: string;
  total_amount: string;
  vest_units: number;
  unpaid_after: number;
  wallet_balance: string;
  notes: string[];
  ready: boolean;
  path: string;
}
/** Properties side by side (public figures + the listings' own risk and exit data). */
export interface ComparisonCard {
  kind: "comparison";
  platform_fee_pct: string;
  items: {
    title: string;
    city: string | null;
    country: string | null;
    model_label: string | null;
    purchase: "direct" | "installment" | string;
    unit_price: number | null;
    minimum_investment: number | null;
    expected_yield: number | null;
    total_return: number | null;
    funding_progress: number | null;
    available_units: number | null;
    expected_completion: string | null;
    exit_options: string[];
    exit_fee_pct: number | null;
    highest_risk: "low" | "medium" | "high" | null;
    image: string | null;
    path: string | null;
  }[];
}
export type AssistantCard =
  | LinkCard
  | PropertyCard
  | PropertiesCard
  | ConfirmActionCard
  | CheckoutCard
  | DepositCard
  | WithdrawalCard
  | StatementCard
  | SaleCard
  | InstallmentCard
  | ComparisonCard;

export interface AssistantMessage {
  id: string;
  role: "user" | "assistant";
  text: string | null;
  cards: AssistantCard[];
  confidence: string | null;
  feedback: string | null;
  created_at: string;
}

export interface TurnDone {
  message_id: string;
  confidence: string;
  flags: string[];
  usage: Record<string, unknown>;
  latency_ms: number;
  first_token_ms: number | null;
  safe_mode: string | null;
}

export type TurnEvent =
  | { event: "started"; data: { conversation_id: string; user_message_id: string } }
  | { event: "delta"; data: { text: string } }
  | { event: "reset"; data: Record<string, never> }
  | { event: "tool"; data: { name: string; status: "running" | "ok" | "error" } }
  | { event: "card"; data: AssistantCard }
  | { event: "done"; data: TurnDone }
  | { event: "error"; data: { code: string; message: string } };

export interface Proposal {
  id: string;
  action: string;
  status: string;
  summary: string | null;
  result: Record<string, unknown> | null;
  decided_at: string | null;
}

// ---- REST ----
export const assistantApi = {
  status: () =>
    apiRequest<AssistantStatus>("/api/v1/assistant/status", { headers: identityHeaders() }),
  consent: (policy_version: string) =>
    apiRequest<{ policy_version: string; accepted_at: string }>("/api/v1/assistant/consent", {
      method: "POST",
      body: { policy_version },
    }),
  createConversation: () =>
    apiRequest<Conversation>("/api/v1/assistant/conversations", {
      method: "POST",
      body: {},
      headers: identityHeaders(),
    }),
  listConversations: () => apiRequest<Conversation[]>("/api/v1/assistant/conversations"),
  messages: (conversationId: string) =>
    apiRequest<AssistantMessage[]>(`/api/v1/assistant/conversations/${conversationId}/messages`, {
      headers: identityHeaders(),
    }),
  confirm: (proposalId: string, token: string) =>
    apiRequest<Proposal>(`/api/v1/assistant/actions/${proposalId}/confirm`, {
      method: "POST",
      body: { token },
    }),
  cancel: (proposalId: string) =>
    apiRequest<Proposal>(`/api/v1/assistant/actions/${proposalId}/cancel`, {
      method: "POST",
      body: {},
    }),
  feedback: (messageId: string, feedback: "up" | "down") =>
    apiRequest<null>(`/api/v1/assistant/messages/${messageId}/feedback`, {
      method: "POST",
      body: { feedback },
      headers: identityHeaders(),
    }),
};

// ---- SSE ----
/** Parse one `event:`/`data:` block. Exported for tests. */
export function parseSseBlock(block: string): TurnEvent | null {
  let event = "";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!event) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n") || "{}") } as TurnEvent;
  } catch {
    return null;
  }
}

/**
 * Stream one turn. Yields events as they arrive. One transparent refresh on a 401. A non-2xx
 * response is raised as ApiError (the backend's envelope) before any event is yielded.
 * `page` is the path the user has open ("this property"); the server keeps it only when it is
 * one of our routes.
 */
export async function* sendMessage(
  conversationId: string,
  text: string,
  lang: "en" | "ar",
  signal?: AbortSignal,
  page?: string,
  _retried = false,
): AsyncGenerator<TurnEvent, void, void> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
    ...identityHeaders(),
  };
  const token = getAccessToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(apiUrl(`/api/v1/assistant/conversations/${conversationId}/messages`), {
    method: "POST",
    headers,
    credentials: "include",
    body: JSON.stringify(page ? { text, lang, page: page.slice(0, 300) } : { text, lang }),
    signal,
  });
  if (resp.status === 401 && token && !_retried && (await refreshAccessToken())) {
    yield* sendMessage(conversationId, text, lang, signal, page, true);
    return;
  }
  if (!resp.ok) {
    let env: { error?: { code?: string; message?: string; details?: unknown } } | null = null;
    try {
      env = await resp.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(
      env?.error?.code ?? "HTTP_ERROR",
      env?.error?.message ?? `Request failed (${resp.status})`,
      resp.status,
      env?.error?.details,
    );
  }
  if (!resp.body) throw new ApiError("NO_BODY", "Empty response", 500);
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const ev = parseSseBlock(block);
      if (ev) yield ev;
    }
  }
  const tail = parseSseBlock(buffer);
  if (tail) yield tail;
}

// ---- support tickets ----
export interface TicketMessage {
  id: string;
  author_type: "user" | "staff" | "system";
  body: string;
  created_at: string;
}
export interface Ticket {
  id: string;
  ticket_no: string;
  category: string | null;
  priority: string;
  status: string;
  subject: string | null;
  source: string;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  csat: number | null;
  messages: TicketMessage[];
}

export const TICKET_CATEGORIES = [
  "payments",
  "withdrawals",
  "kyc",
  "investment",
  "installments",
  "secondary_market",
  "liquidity",
  "account",
  "listing",
  "other",
] as const;

export const ticketsApi = {
  create: (body: {
    category: string;
    subject: string;
    body: string;
    priority?: "normal" | "high";
    contact_email?: string;
  }) => apiRequest<Ticket>("/api/v1/support/tickets", { method: "POST", body }),
  list: () => apiRequest<Ticket[]>("/api/v1/support/tickets"),
  get: (id: string) => apiRequest<Ticket>(`/api/v1/support/tickets/${id}`),
  reply: (id: string, body: string) =>
    apiRequest<Ticket>(`/api/v1/support/tickets/${id}/messages`, { method: "POST", body: { body } }),
  rate: (id: string, score: number) =>
    apiRequest<Ticket>(`/api/v1/support/tickets/${id}/csat`, { method: "POST", body: { score } }),
};
