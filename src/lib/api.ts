// CapiMax API client (Phase 1 cutover).
//
// Talks to the Python (FastAPI) backend. Security model (owner-mandated):
//   - the ACCESS token lives in MEMORY only (this module) — never localStorage;
//   - the REFRESH token is an httpOnly cookie set by the backend (credentials:
//     "include" sends it). On a 401 we transparently call /auth/refresh once.
// Supabase is gone — this is the only backend the SPA talks to.

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

let accessToken: string | null = null;

export const setAccessToken = (token: string | null) => {
  accessToken = token;
};
export const getAccessToken = () => accessToken;

export class ApiError extends Error {
  code: string;
  status: number;
  details: unknown;
  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Attach the bearer access token (default true). */
  auth?: boolean;
  /** Extra request headers (e.g. Idempotency-Key on money mutations). */
  headers?: Record<string, string>;
  /** internal: prevent infinite refresh recursion */
  _retried?: boolean;
}

async function parse(resp: Response): Promise<unknown> {
  if (resp.status === 204) return null;
  const text = await resp.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function refreshAccessToken(): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!resp.ok) return false;
    const data = (await parse(resp)) as { access_token?: string } | null;
    if (data?.access_token) {
      setAccessToken(data.access_token);
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

export async function apiRequest<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true, _retried = false } = opts;
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  // FormData (file uploads) must NOT set Content-Type — the browser adds the multipart
  // boundary — and must not be JSON-stringified.
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (auth && accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    credentials: "include",
    body: body !== undefined ? (isForm ? (body as FormData) : JSON.stringify(body)) : undefined,
  });

  // Transparent one-shot refresh on an expired/again-unauthenticated access token.
  if (resp.status === 401 && auth && !_retried && path !== "/api/v1/auth/refresh") {
    const ok = await refreshAccessToken();
    if (ok) return apiRequest<T>(path, { ...opts, _retried: true });
  }

  const data = await parse(resp);
  if (!resp.ok) {
    const env = (data as { error?: { code?: string; message?: string; details?: unknown } })?.error;
    throw new ApiError(
      env?.code ?? "HTTP_ERROR",
      env?.message ?? `Request failed (${resp.status})`,
      resp.status,
      env?.details,
    );
  }
  return data as T;
}

/** Absolute URL for a backend-relative path (e.g. a public file/download link). */
export const apiUrl = (path: string): string => `${API_BASE}${path}`;

/** Authenticated binary fetch (e.g. a generated PDF certificate). One-shot refresh on 401. */
export async function fetchBlob(path: string, _retried = false): Promise<Blob> {
  const headers: Record<string, string> = {};
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  const resp = await fetch(`${API_BASE}${path}`, { headers, credentials: "include" });
  if (resp.status === 401 && !_retried) {
    const ok = await refreshAccessToken();
    if (ok) return fetchBlob(path, true);
  }
  if (!resp.ok) throw new ApiError("DOWNLOAD_FAILED", `Download failed (${resp.status})`, resp.status);
  return resp.blob();
}

// ---- Types mirrored from the backend (app/schemas/auth.py) ----
export interface WalletSummary {
  balance: string;
  pending_balance: string;
  total_invested: string;
  total_returns: string;
}
export interface MeResponse {
  id: string;
  email: string;
  full_name: string | null;
  phone: string | null;
  email_verified: boolean;
  roles: string[];
  active_role: string | null;
  kyc_status: string;
  wallet: WalletSummary;
}
interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// ---- Auth endpoints ----
export const authApi = {
  async register(input: {
    email: string;
    password: string;
    full_name?: string;
    phone?: string;
    referral_code?: string;
  }): Promise<MeResponse> {
    const tok = await apiRequest<TokenResponse>("/api/v1/auth/register", {
      method: "POST",
      body: input,
      auth: false,
    });
    setAccessToken(tok.access_token);
    return authApi.me();
  },

  async login(email: string, password: string): Promise<MeResponse> {
    const tok = await apiRequest<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    });
    setAccessToken(tok.access_token);
    return authApi.me();
  },

  async oauthLogin(provider: string, code: string, redirect_uri: string): Promise<MeResponse> {
    const tok = await apiRequest<TokenResponse>(`/api/v1/auth/oauth/${provider}`, {
      method: "POST",
      body: { code, redirect_uri },
      auth: false,
    });
    setAccessToken(tok.access_token);
    return authApi.me();
  },

  async logout(): Promise<void> {
    try {
      await apiRequest("/api/v1/auth/logout", { method: "POST" });
    } finally {
      setAccessToken(null);
    }
  },

  me(): Promise<MeResponse> {
    return apiRequest<MeResponse>("/api/v1/auth/me");
  },

  switchRole(role: string): Promise<MeResponse> {
    return apiRequest<MeResponse>("/api/v1/auth/switch-role", { method: "POST", body: { role } });
  },

  requestRole(role: string): Promise<{ status: string; role: string }> {
    return apiRequest("/api/v1/auth/roles/request", { method: "POST", body: { role } });
  },

  forgotPassword(email: string): Promise<void> {
    return apiRequest("/api/v1/auth/password/forgot", {
      method: "POST",
      body: { email },
      auth: false,
    }).then(() => undefined);
  },

  resetPassword(token: string, new_password: string): Promise<void> {
    return apiRequest("/api/v1/auth/password/reset", {
      method: "POST",
      body: { token, new_password },
      auth: false,
    }).then(() => undefined);
  },

  changePassword(current_password: string, new_password: string): Promise<void> {
    return apiRequest("/api/v1/auth/password/change", {
      method: "POST",
      body: { current_password, new_password },
    }).then(() => undefined);
  },

  verifyEmail(token: string): Promise<void> {
    return apiRequest("/api/v1/auth/verify-email", {
      method: "POST",
      body: { token },
      auth: false,
    }).then(() => undefined);
  },
};

// ---- Profile endpoints ----
export interface ProfileResponse {
  id: string;
  email: string | null;
  full_name: string | null;
  phone: string | null;
  avatar_url: string | null;
}
export const profileApi = {
  get(): Promise<ProfileResponse> {
    return apiRequest<ProfileResponse>("/api/v1/profiles/me");
  },
  update(input: { full_name?: string; phone?: string }): Promise<ProfileResponse> {
    return apiRequest<ProfileResponse>("/api/v1/profiles/me", { method: "PATCH", body: input });
  },
};

// ---- KYC endpoints (Phase 2) ----
export interface KycStatusResponse {
  status: "pending" | "submitted" | "verified" | "rejected";
  manual_review_required: boolean;
  provider: string | null;
  submitted_at: string | null;
  verified_at: string | null;
  rejection_reason: string | null;
}
export interface KycStartResponse {
  sdk_token: string;
  applicant_id: string | null;
  provider: string;
}
export const kycApi = {
  getMine(): Promise<KycStatusResponse> {
    return apiRequest<KycStatusResponse>("/api/v1/kyc/me");
  },
  start(): Promise<KycStartResponse> {
    return apiRequest<KycStartResponse>("/api/v1/kyc/me/start", { method: "POST" });
  },
};

// ---- Property catalog (Phase 3) ----
export interface PropertySummary {
  id: string;
  slug: string | null;
  title: string;
  subtitle: string | null;
  location: string;
  country: string | null;
  city: string | null;
  model: string;
  property_type: string;
  status: string;
  image: string | null;
  total_value: number;
  minimum_investment: number;
  unit_price: number;
  target_yield: number | null;
  expected_yield: number | null;
  capital_appreciation: number | null;
  total_return: number | null;
  funded_amount: number;
  funding_progress: number;
  total_units: number;
  available_units: number;
  investors_count: number;
  developer_name: string | null;
}

export interface PropertyMilestone {
  id: string;
  property_id: string;
  title: string;
  description: string | null;
  status: "planned" | "in_progress" | "completed";
  progress_pct: number | null;
  value_index: number | null; // NAV step (100 = entry); null for non-construction milestones
  target_date: string | null;
  completed_at: string | null;
  sort_index: number;
}

export interface PropertyDetail extends PropertySummary {
  description: string | null;
  images: string[];
  expected_completion: string | null;
  spv_name: string | null;
  spv_registration: string | null;
  legal_structure: string | null;
  fees: Record<string, unknown> | null;
  content: Record<string, unknown>;
  owner_id: string | null;
  created_at: string;
  updated_at: string;
  // Phase 15b — real milestones + the construction % computed from them.
  milestones: PropertyMilestone[];
  construction_progress: number;
}

export interface PropertyListResponse {
  items: PropertySummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface PropertyFilterParams {
  model?: string;
  property_type?: string;
  country?: string;
  city?: string;
  status?: string;
  min_yield?: number;
  min_price?: number;
  max_price?: number;
  search?: string;
  sort?: string;
  limit?: number;
  offset?: number;
}

export interface PropertyCreatePayload {
  title: string;
  property_type: string;
  location: string;
  description?: string;
  total_value: number;
  unit_price: number;
  total_units?: number;
  minimum_investment?: number;
  target_yield?: number | null;
  expected_completion?: string | null;
  spv_name?: string | null;
  spv_registration?: string | null;
  legal_structure?: string | null;
  model?: string;
  subtitle?: string | null;
  country?: string | null;
  city?: string | null;
  expected_yield?: number | null;
  capital_appreciation?: number | null;
  total_return?: number | null;
  images?: string[];
  content?: Record<string, unknown>;
}

function buildQuery(params: Record<string, unknown>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "" && v !== "all") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const propertyApi = {
  list(params: PropertyFilterParams = {}): Promise<PropertyListResponse> {
    return apiRequest<PropertyListResponse>(
      `/api/v1/properties${buildQuery(params as Record<string, unknown>)}`,
      { auth: false },
    );
  },
  get(idOrSlug: string): Promise<PropertyDetail> {
    return apiRequest<PropertyDetail>(`/api/v1/properties/${encodeURIComponent(idOrSlug)}`, {
      auth: false,
    });
  },
  create(payload: PropertyCreatePayload): Promise<PropertyDetail> {
    return apiRequest<PropertyDetail>("/api/v1/properties", { method: "POST", body: payload });
  },
  update(id: string, payload: Partial<PropertyCreatePayload>): Promise<PropertyDetail> {
    return apiRequest<PropertyDetail>(`/api/v1/properties/${id}`, { method: "PATCH", body: payload });
  },
  submit(id: string): Promise<PropertyDetail> {
    return apiRequest<PropertyDetail>(`/api/v1/properties/${id}/submit`, { method: "POST" });
  },
  listOwner(): Promise<PropertyDetail[]> {
    return apiRequest<PropertyDetail[]>("/api/v1/owner/properties");
  },
  adminList(status = "under_review"): Promise<PropertySummary[]> {
    return apiRequest<PropertySummary[]>(`/api/v1/admin/properties${buildQuery({ status })}`);
  },
  adminApprove(id: string): Promise<PropertyDetail> {
    return apiRequest<PropertyDetail>(`/api/v1/admin/properties/${id}/approve`, { method: "POST" });
  },
  adminReject(id: string, reason?: string): Promise<PropertyDetail> {
    return apiRequest<PropertyDetail>(`/api/v1/admin/properties/${id}/reject`, {
      method: "POST",
      body: { reason },
    });
  },
  adminClose(id: string, reason?: string): Promise<PropertyDetail> {
    return apiRequest<PropertyDetail>(`/api/v1/admin/properties/${id}/close`, {
      method: "POST",
      body: { reason },
    });
  },
};

// ---- Wallet & deposits (Phase 4) ----
export interface WalletResponse {
  balance: string;
  pending_balance: string;
  total_invested: string;
  total_returns: string;
  currency: string;
}
export interface TransactionItem {
  id: string;
  type: string;
  amount: string;
  status: string;
  description: string | null;
  payment_method: string | null;
  reference_id: string | null;
  created_at: string;
}
export interface TransactionListResponse {
  items: TransactionItem[];
  total: number;
  limit: number;
  offset: number;
}
export interface DepositResponse {
  payment_id: string;
  provider: string;
  status: string;
  checkout_url: string | null;
}
export interface PaymentStatus {
  id: string;
  provider: string;
  status: string;
  amount: string;
  amount_captured: string | null;
  created_at: string;
}

export const walletApi = {
  getMe(): Promise<WalletResponse> {
    return apiRequest<WalletResponse>("/api/v1/wallet/me");
  },
  transactions(limit = 50, offset = 0): Promise<TransactionListResponse> {
    return apiRequest<TransactionListResponse>(
      `/api/v1/wallet/transactions?limit=${limit}&offset=${offset}`,
    );
  },
  deposit(input: { amount: number; method: "card" | "crypto" }, idempotencyKey: string) {
    return apiRequest<DepositResponse>("/api/v1/wallet/deposit", {
      method: "POST",
      body: input,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
};

export const paymentApi = {
  get(id: string): Promise<PaymentStatus> {
    return apiRequest<PaymentStatus>(`/api/v1/payments/${id}`);
  },
};

// --- Investments (Phase 5) ------------------------------------------------- //
export type InvestMethod = "wallet" | "card" | "crypto";

export interface InvestCreateResponse {
  investment_id: string;
  property_id: string;
  status: string;
  units: number;
  amount: string;
  platform_fee: string;
  total_charged: string;
  management_fee_rate: string;
  checkout_url: string | null;
}

export interface InvestmentItem {
  id: string;
  property_id: string;
  status: string;
  units: number;
  amount: string;
  platform_fee: string;
  total_charged: string;
  confirmed_via: string | null;
  created_at: string;
  confirmed_at: string | null;
}

export interface InvestmentListResponse {
  items: InvestmentItem[];
  total: number;
}

export interface PortfolioSummary {
  invested: string;
  current_value: string;
  total_returns: string;
  properties: number;
  units: number;
}

export const investApi = {
  /** Buy units. The SERVER computes units/fees/charge — we only send amount + method. */
  create(
    input: { property_id: string; amount: number; method: InvestMethod },
    idempotencyKey: string,
  ): Promise<InvestCreateResponse> {
    return apiRequest<InvestCreateResponse>("/api/v1/investments", {
      method: "POST",
      body: input,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
  list(): Promise<InvestmentListResponse> {
    return apiRequest<InvestmentListResponse>("/api/v1/investments");
  },
  /** Server-authoritative portfolio summary (invested / value / returns / units). */
  portfolio(): Promise<PortfolioSummary> {
    return apiRequest<PortfolioSummary>("/api/v1/investments/portfolio");
  },
  /** The live, admin-configurable reinvest discount rate (server-authoritative). */
  reinvestSettings(): Promise<{ discount_pct: string }> {
    return apiRequest("/api/v1/investments/reinvest-settings");
  },
  /** Reinvest returns from the wallet at the server-applied discount. SERVER computes
   * the discounted units/price — the client only sends an amount. */
  reinvest(
    input: { property_id: string; amount: number },
    idempotencyKey: string,
  ): Promise<{
    property_id: string;
    amount: string;
    discount_pct?: string;
    effective_price?: string;
    units?: number;
    replayed?: boolean;
  }> {
    return apiRequest("/api/v1/investments/reinvest", {
      method: "POST",
      body: input,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
};

// --- Owner / Developer real stats (Phase 15) ------------------------------- //
export interface MonthlyPoint {
  month: string; // "YYYY-MM"
  amount: string;
}
export interface PerPropertyStat {
  property_id: string;
  revenue_generated: string;
  occupancy: number | null;
}
export interface OwnerPortfolioStats {
  total_portfolio_value: string;
  total_investors: number;
  occupancy: number | null; // null = honest empty (no occupancy domain yet)
  monthly_revenue_current: string;
  monthly_revenue_series: MonthlyPoint[];
  per_property: PerPropertyStat[];
}
export interface DeveloperFundingStats {
  monthly_funding_series: MonthlyPoint[];
  funding_this_month: string;
  repeat_investors: { repeat: number; total: number; pct: string };
  distinct_investors: number;
}
export const ownerStatsApi = {
  /** Owner overview cards + monthly-revenue series (server-authoritative aggregation). */
  portfolioStats(): Promise<OwnerPortfolioStats> {
    return apiRequest<OwnerPortfolioStats>("/api/v1/owner/portfolio-stats");
  },
  /** Developer funding series + this-month + repeat investors. */
  fundingStats(): Promise<DeveloperFundingStats> {
    return apiRequest<DeveloperFundingStats>("/api/v1/owner/funding-stats");
  },
};

// --- Property milestones (Phase 15b) --------------------------------------- //
export interface MilestonePayload {
  title: string;
  description?: string | null;
  status?: "planned" | "in_progress" | "completed";
  progress_pct?: number | null;
  value_index?: number | null;
  target_date?: string | null;
}

/** Owner/developer CRUD for a property's milestones (owner-scoped on the server). */
export const ownerMilestonesApi = {
  list(propId: string): Promise<PropertyMilestone[]> {
    return apiRequest<PropertyMilestone[]>(`/api/v1/owner/properties/${propId}/milestones`);
  },
  create(propId: string, payload: MilestonePayload): Promise<PropertyMilestone> {
    return apiRequest<PropertyMilestone>(`/api/v1/owner/properties/${propId}/milestones`, {
      method: "POST",
      body: payload,
    });
  },
  update(
    propId: string,
    milestoneId: string,
    payload: Partial<MilestonePayload>,
  ): Promise<PropertyMilestone> {
    return apiRequest<PropertyMilestone>(
      `/api/v1/owner/properties/${propId}/milestones/${milestoneId}`,
      { method: "PATCH", body: payload },
    );
  },
  remove(propId: string, milestoneId: string): Promise<void> {
    return apiRequest<void>(`/api/v1/owner/properties/${propId}/milestones/${milestoneId}`, {
      method: "DELETE",
    });
  },
  reorder(propId: string, orderedIds: string[]): Promise<PropertyMilestone[]> {
    return apiRequest<PropertyMilestone[]>(
      `/api/v1/owner/properties/${propId}/milestones/reorder`,
      { method: "POST", body: { ordered_ids: orderedIds } },
    );
  },
};

// --- Investor communications (Phase 15c) ----------------------------------- //
export interface DeveloperUpdate {
  id: string;
  property_id: string;
  subject: string;
  body: string;
  recipient_count: number; // snapshot at send (net-holders) — real
  read_count: number; // in-app reads (notifications.read) — real; no open/click tracking
  created_at: string;
}

/** Developer sends a per-property update (fans out to net-holders); reads sent history. */
export const ownerUpdatesApi = {
  send(propId: string, payload: { subject: string; body: string }): Promise<DeveloperUpdate> {
    return apiRequest<DeveloperUpdate>(`/api/v1/owner/properties/${propId}/updates`, {
      method: "POST",
      body: payload,
    });
  },
  list(propertyId?: string): Promise<DeveloperUpdate[]> {
    const q = propertyId ? `?property_id=${propertyId}` : "";
    return apiRequest<DeveloperUpdate[]>(`/api/v1/owner/updates${q}`);
  },
};

// --- Documents + certificates (Group 2: storage) --------------------------- //
export interface PropertyDocument {
  id: string;
  property_id: string | null;
  title: string;
  type: string;
  download_url: string; // backend-relative; use apiUrl() for an <a href>
  created_at: string;
}

export const documentsApi = {
  /** Public list of a property's documents. */
  listForProperty(idOrSlug: string): Promise<PropertyDocument[]> {
    return apiRequest<PropertyDocument[]>(
      `/api/v1/properties/${encodeURIComponent(idOrSlug)}/documents`,
      { auth: false },
    );
  },
  /** Owner uploads a property document (multipart). */
  upload(propId: string, file: File, title: string, docType = "document"): Promise<PropertyDocument> {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", title);
    fd.append("doc_type", docType);
    return apiRequest<PropertyDocument>(`/api/v1/properties/${propId}/documents`, {
      method: "POST",
      body: fd,
    });
  },
};

export const certificateApi = {
  /** Download a PDF certificate of the caller's current holding in a property. */
  download(propertyId: string): Promise<Blob> {
    return fetchBlob(`/api/v1/investments/certificate/${propertyId}`);
  },
};

// --- Saved payment methods (Group 3: PCI-safe tokenization) ---------------- //
export interface SavedPaymentMethod {
  id: string;
  type: string;
  brand: string | null;
  last4: string | null;
  exp_month: number | null;
  exp_year: number | null;
  is_default: boolean;
  created_at: string;
}
export interface SetupIntentInfo {
  client_secret: string;
  publishable_key: string;
}

export const paymentMethodsApi = {
  list(): Promise<SavedPaymentMethod[]> {
    return apiRequest<SavedPaymentMethod[]>("/api/v1/wallet/payment-methods");
  },
  /** Start card tokenization (Stripe SetupIntent client secret); confirmed via Stripe.js. */
  setupIntent(): Promise<SetupIntentInfo> {
    return apiRequest<SetupIntentInfo>("/api/v1/wallet/payment-methods/setup-intent", {
      method: "POST",
    });
  },
  add(paymentMethodId: string): Promise<SavedPaymentMethod> {
    return apiRequest<SavedPaymentMethod>("/api/v1/wallet/payment-methods", {
      method: "POST",
      body: { payment_method_id: paymentMethodId },
    });
  },
  remove(id: string): Promise<void> {
    return apiRequest<void>(`/api/v1/wallet/payment-methods/${id}`, { method: "DELETE" });
  },
  setDefault(id: string): Promise<SavedPaymentMethod> {
    return apiRequest<SavedPaymentMethod>(`/api/v1/wallet/payment-methods/${id}/default`, {
      method: "POST",
    });
  },
};

// --- Returns / distributions (Phase 6) ------------------------------------- //
export interface ReturnItem {
  distribution_id: string;
  property_id: string;
  kind: string;
  period_key: string;
  period_end: string;
  units: number;
  gross_amount: string;
  management_fee: string;
  net_amount: string;
}

export interface MyReturns {
  total_net: string;
  total_management_fee: string;
  count: number;
  monthly: { month: string; net: string }[];
  items: ReturnItem[];
}

export const returnsApi = {
  /** The caller's distributed returns: history + monthly aggregation for charts. */
  getMine(): Promise<MyReturns> {
    return apiRequest<MyReturns>("/api/v1/investments/returns");
  },
};

// --- Withdrawals + Stripe Connect (Phase 7) -------------------------------- //
export type WithdrawMethod = "bank" | "crypto";

export interface WithdrawalCreateResponse {
  withdrawal_id: string;
  amount: string;
  method: string;
  status: string;
  created_at: string | null;
}

export interface WithdrawalItem {
  id: string;
  amount: string;
  method: string;
  provider: string;
  status: string;
  failure_reason: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface ConnectStatus {
  status: string; // none | pending | verified | restricted
  payouts_enabled: boolean;
  details_submitted: boolean;
  stripe_account_id: string | null;
}

export const withdrawApi = {
  /** Request a payout. Funds are held on request; settlement is webhook-driven. */
  create(
    input: { amount: number; method: WithdrawMethod; address?: string },
    idempotencyKey: string,
  ): Promise<WithdrawalCreateResponse> {
    return apiRequest<WithdrawalCreateResponse>("/api/v1/wallet/withdrawals", {
      method: "POST",
      body: input,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
  list(): Promise<{ items: WithdrawalItem[]; total: number }> {
    return apiRequest("/api/v1/wallet/withdrawals");
  },
};

export const connectApi = {
  /** Stripe Connect onboarding status for bank withdrawals. */
  status(): Promise<ConnectStatus> {
    return apiRequest<ConnectStatus>("/api/v1/wallet/connect/status");
  },
  /** Start/continue onboarding; returns a hosted Stripe onboarding URL. */
  onboard(): Promise<{ onboarding_url: string; account_id: string; status: string }> {
    return apiRequest("/api/v1/wallet/connect/onboard", { method: "POST" });
  },
};

// --- Secondary market (Phase 8) -------------------------------------------- //
export interface SecondaryListing {
  listing_id: string;
  property_id: string | null;
  property_title: string | null;
  property_location: string | null;
  seller_id: string;
  units_for_sale: number;
  units_remaining: number;
  price_per_unit: string;
  unit_price_ref: string | null;
  status: string; // active | sold | cancelled
  created_at: string | null;
}

export interface SecondaryTrade {
  trade_id: string;
  listing_id: string;
  property_id: string;
  units: number;
  price_per_unit: string;
  gross: string;
  resale_fee: string;
  total_charged: string;
  created_at: string | null;
}

export interface SecondarySettings {
  resale_fee_pct: string;
  lockup_days: number;
  price_min_pct: string | null;
  price_max_pct: string | null;
}

export interface Holding {
  property_id: string;
  title: string | null;
  location: string | null;
  units: number;
  listed_units: number;
  sellable_units: number;
  unit_price: string;
}

export const secondaryApi = {
  /** Browse active listings (optionally filtered by property). */
  list(propertyId?: string): Promise<{ items: SecondaryListing[]; total: number }> {
    const q = propertyId ? `?property_id=${encodeURIComponent(propertyId)}` : "";
    return apiRequest(`/api/v1/secondary/listings${q}`);
  },
  /** The caller's own listings (any status). */
  mine(): Promise<{ items: SecondaryListing[]; total: number }> {
    return apiRequest("/api/v1/secondary/listings/mine");
  },
  /** List units you own. The SERVER validates ownership/lock-up/price bounds. */
  create(input: { property_id: string; units: number; price_per_unit: number }): Promise<SecondaryListing> {
    return apiRequest<SecondaryListing>("/api/v1/secondary/listings", {
      method: "POST",
      body: input,
    });
  },
  /** Buy units off a listing. Wallet-funded, atomic; the SERVER computes the fee/total. */
  buy(
    listingId: string,
    units: number,
    idempotencyKey: string,
  ): Promise<SecondaryTrade> {
    return apiRequest<SecondaryTrade>(`/api/v1/secondary/listings/${listingId}/buy`, {
      method: "POST",
      body: { units },
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
  cancel(listingId: string): Promise<{ listing_id: string; status: string }> {
    return apiRequest(`/api/v1/secondary/listings/${listingId}/cancel`, { method: "POST" });
  },
  /** Live resale-fee / lock-up / price-bound knobs (so the UI shows what the server charges). */
  settings(): Promise<SecondarySettings> {
    return apiRequest<SecondarySettings>("/api/v1/secondary/settings");
  },
};

export const holdingsApi = {
  /** The caller's net unit holdings per property (sellable units, from ownership_ledger). */
  mine(): Promise<{ items: Holding[]; total: number }> {
    return apiRequest("/api/v1/secondary/holdings");
  },
};

// --- Liquidity provider (Phase 9 — ACTIVE rail) ---------------------------- //
export interface LpExitRequest {
  request_id: string;
  property_id: string;
  property_title: string | null;
  property_location: string | null;
  seller_id: string;
  units: number;
  units_remaining: number;
  unit_price: string;
  discount_pct: string;
  fee_pct: string;
  gross: string;
  lp_price: string;
  liquidity_fee: string;
  seller_net: string;
  status: string; // open | filled | cancelled | expired
  created_at: string | null;
  expires_at: string | null;
}

export interface LpPosition {
  position_id: string;
  classification: string; // active | passive
  property_id: string | null;
  units_acquired: number | null;
  principal: string;
  spread_at_entry: string | null;
  status: string;
  created_at: string | null;
}

export interface LpPoolTier {
  period_months: number;
  apy_pct: string;
  min_amount: string;
}

export interface LiquiditySettings {
  discount_pct: string;
  fee_pct: string;
  ttl_minutes: number;
  band_pct: string;
  passive_enabled: boolean;
  tiers: LpPoolTier[];
}

export const liquidityApi = {
  /** Seller: list an instant-exit request (LP-funded buyout at the liquidity discount). */
  createExitRequest(input: { property_id: string; units: number }): Promise<LpExitRequest> {
    return apiRequest<LpExitRequest>("/api/v1/liquidity/exit-requests", {
      method: "POST",
      body: input,
    });
  },
  /** Browse the open exit-request order book (optionally by property). */
  listOpen(propertyId?: string): Promise<{ items: LpExitRequest[]; total: number }> {
    const q = propertyId ? `?property_id=${encodeURIComponent(propertyId)}` : "";
    return apiRequest(`/api/v1/liquidity/exit-requests${q}`);
  },
  myRequests(): Promise<{ items: LpExitRequest[]; total: number }> {
    return apiRequest("/api/v1/liquidity/exit-requests/mine");
  },
  cancelRequest(id: string): Promise<{ request_id: string; status: string }> {
    return apiRequest(`/api/v1/liquidity/exit-requests/${id}/cancel`, { method: "POST" });
  },
  /** LP: fund a request (atomic buyback). Requires the liquidity_provider role + KYC. */
  fund(requestId: string, units: number, idempotencyKey: string): Promise<LpPosition> {
    return apiRequest<LpPosition>(`/api/v1/liquidity/exit-requests/${requestId}/fund`, {
      method: "POST",
      body: { units },
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
  /** LP ACTIVE acquisition history (audit — NOT current holdings). */
  positions(): Promise<{ items: LpPosition[]; total: number }> {
    return apiRequest("/api/v1/liquidity/positions");
  },
  /** LP current holdings — source of truth is ownership_ledger. */
  holdings(): Promise<{ items: Holding[]; total: number }> {
    return apiRequest("/api/v1/liquidity/holdings");
  },
  settings(): Promise<LiquiditySettings> {
    return apiRequest<LiquiditySettings>("/api/v1/liquidity/settings");
  },
};

// --- Family groups & gifting (Phase 10) ------------------------------------ //
export interface FamilyMember {
  member_id: string;
  name: string;
  email: string | null;
  relationship: string;
  is_verified: boolean;
  is_user: boolean;
  pending_units: number;
  allocated_returns: string;
  real_units: number;
}

export interface FamilyGroup {
  group_id: string;
  name: string;
  total_returns: string;
  members: FamilyMember[];
}

export interface FamilyTransfer {
  transfer_id: string;
  from_member_id: string | null;
  to_member_id: string;
  property_id: string | null;
  units: number;
  transfer_fee: string;
  status: string; // completed | pending | cancelled
  created_at: string | null;
}

export interface FamilySettings {
  reinvest_discount_pct: string;
  transfer_fee_pct: string;
}

export const familyApi = {
  getGroup(): Promise<FamilyGroup | null> {
    return apiRequest<FamilyGroup | null>("/api/v1/family/groups/me");
  },
  createGroup(name: string): Promise<FamilyGroup> {
    return apiRequest<FamilyGroup>("/api/v1/family/groups", { method: "POST", body: { name } });
  },
  addMember(input: { name: string; email?: string; relationship: string }): Promise<FamilyMember> {
    return apiRequest<FamilyMember>("/api/v1/family/members", { method: "POST", body: input });
  },
  /** Allocate/transfer units member→member (real move when both are users; else pending). */
  transfer(
    input: { from_member_id: string; to_member_id: string; property_id: string; units: number },
    idempotencyKey: string,
  ): Promise<FamilyTransfer> {
    return apiRequest<FamilyTransfer>("/api/v1/family/transfers", {
      method: "POST",
      body: input,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
  cancelTransfer(id: string): Promise<FamilyTransfer> {
    return apiRequest(`/api/v1/family/transfers/${id}/cancel`, { method: "POST" });
  },
  allocateReturns(
    input: { member_id: string; amount: number },
    idempotencyKey: string,
  ): Promise<{ member_id: string; amount: string; real?: boolean }> {
    return apiRequest("/api/v1/family/allocations", {
      method: "POST",
      body: input,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
  /** Reinvest family returns at the family discount (effective price = unit_price×(1−d)). */
  reinvest(
    input: { property_id: string; amount: number },
    idempotencyKey: string,
  ): Promise<{ property_id: string; amount: string; effective_price?: string; units?: number }> {
    return apiRequest("/api/v1/family/reinvest", {
      method: "POST",
      body: input,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  },
  listTransfers(): Promise<{ items: FamilyTransfer[]; total: number }> {
    return apiRequest("/api/v1/family/transfers");
  },
  settings(): Promise<FamilySettings> {
    return apiRequest<FamilySettings>("/api/v1/family/settings");
  },
};

// ---- Broker (Phase 11) ----
export interface BrokerReferralCode {
  code: string;
  share_link: string;
}

export interface BrokerDashboard {
  commission_rate: string; // broker_commission_pct, live from platform_settings
  total_referrals: number;
  total_commission: string;
}

export interface BrokerReferralItem {
  referral_id: string;
  client_masked: string;
  created_at: string;
  commission_to_date: string;
}

export interface BrokerCommissionItem {
  id: string;
  revenue_event_type: string; // investment_platform_fee | distribution_mgmt_fee
  revenue_amount: string;
  commission_rate: string;
  commission_amount: string;
  created_at: string;
}

export const brokerApi = {
  referralCode(): Promise<BrokerReferralCode> {
    return apiRequest<BrokerReferralCode>("/api/v1/broker/referral-code");
  },
  dashboard(): Promise<BrokerDashboard> {
    return apiRequest<BrokerDashboard>("/api/v1/broker/dashboard");
  },
  referrals(): Promise<{ items: BrokerReferralItem[]; total: number }> {
    return apiRequest("/api/v1/broker/referrals");
  },
  commissions(): Promise<{ items: BrokerCommissionItem[]; total: number }> {
    return apiRequest("/api/v1/broker/commissions");
  },
};

// ---- Notifications (Phase 12) ----
export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  message: string;
  read: boolean;
  created_at: string;
}

export interface NotificationPreferences {
  email_investment_updates: boolean;
  email_returns: boolean;
  email_security_alerts: boolean;
  email_new_properties: boolean;
}

export const notificationApi = {
  list(unreadOnly = false): Promise<{ items: NotificationItem[]; total: number; unread_count: number }> {
    return apiRequest(`/api/v1/notifications?unread_only=${unreadOnly}`);
  },
  unreadCount(): Promise<{ count: number }> {
    return apiRequest("/api/v1/notifications/unread-count");
  },
  markRead(id: string): Promise<{ ok: boolean }> {
    return apiRequest(`/api/v1/notifications/${id}/read`, { method: "POST" });
  },
  markAllRead(): Promise<{ marked: number }> {
    return apiRequest("/api/v1/notifications/read-all", { method: "POST" });
  },
  getPreferences(): Promise<NotificationPreferences> {
    return apiRequest<NotificationPreferences>("/api/v1/notifications/preferences");
  },
  updatePreferences(prefs: Partial<NotificationPreferences>): Promise<NotificationPreferences> {
    return apiRequest<NotificationPreferences>("/api/v1/notifications/preferences", {
      method: "PUT",
      body: prefs,
    });
  },
};
