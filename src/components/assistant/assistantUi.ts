import {
  ArrowDownToLine,
  BadgeCheck,
  BookOpen,
  Building2,
  Compass,
  FileText,
  HelpCircle,
  LayoutDashboard,
  LifeBuoy,
  LogIn,
  type LucideIcon,
  Receipt,
  ShieldCheck,
  TrendingUp,
  UserPlus,
  Wallet,
} from "lucide-react";

/**
 * Presentation helpers for the assistant widget: what a tool call is called while it runs
 * ("Checking your wallet…") and after ("Checked your wallet"), and which icon a page button
 * gets. Tool names stay a backend detail; the user sees plain language.
 */

type ToolLabel = { running: string; done: string };

const TOOL_LABELS: Record<string, ToolLabel> = {
  get_my_wallet: { running: "Checking your wallet", done: "Checked your wallet" },
  list_my_transactions: { running: "Reading your transactions", done: "Read your transactions" },
  list_my_withdrawals: { running: "Checking your withdrawals", done: "Checked your withdrawals" },
  get_payment_status: { running: "Checking the payment", done: "Checked the payment" },
  list_my_investments: { running: "Loading your investments", done: "Loaded your investments" },
  get_my_portfolio: { running: "Reviewing your portfolio", done: "Reviewed your portfolio" },
  list_my_returns: { running: "Loading your returns", done: "Loaded your returns" },
  list_my_installment_plans: { running: "Checking your installments", done: "Checked your installments" },
  get_my_holdings: { running: "Checking your holdings", done: "Checked your holdings" },
  get_my_account: { running: "Checking your account", done: "Checked your account" },
  get_my_kyc_status: { running: "Checking your verification", done: "Checked your verification" },
  list_my_notifications: { running: "Reading your notifications", done: "Read your notifications" },
  list_my_tickets: { running: "Checking your tickets", done: "Checked your tickets" },
  get_my_ticket: { running: "Opening your ticket", done: "Opened your ticket" },
  get_my_broker_dashboard: { running: "Loading your broker dashboard", done: "Loaded your broker dashboard" },
  get_my_family_group: { running: "Checking your family group", done: "Checked your family group" },
  search_properties: { running: "Searching properties", done: "Searched properties" },
  get_property: { running: "Opening the property", done: "Opened the property" },
  quote_investment: { running: "Calculating your quote", done: "Calculated your quote" },
  get_platform_settings: { running: "Checking live fees and terms", done: "Checked live fees and terms" },
  search_kb: { running: "Looking it up", done: "Looked it up" },
  search_reference: { running: "Reading company documents", done: "Read company documents" },
  search_documents: { running: "Searching property documents", done: "Searched property documents" },
  prepare_deep_link: { running: "Finding the right page", done: "Found the right page" },
  propose_action: { running: "Preparing a confirmation", done: "Prepared a confirmation" },
  report_knowledge_gap: { running: "Passing this to the team", done: "Passed this to the team" },
};

function humanize(name: string): string {
  const words = name.replace(/^(get|list|search)_/, "").replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function toolLabel(name: string, status: "running" | "ok" | "error"): string {
  const known = TOOL_LABELS[name];
  if (status === "running") return `${known?.running ?? humanize(name)}…`;
  if (status === "error") return `Couldn't check: ${(known?.done ?? humanize(name)).toLowerCase()}`;
  return known?.done ?? humanize(name);
}

/** Icon for a page button, from the allow-listed path the server sent. */
export function linkIcon(path: string): LucideIcon {
  if (path.startsWith("/auth?tab=register")) return UserPlus;
  if (path.startsWith("/auth")) return LogIn;
  if (path.startsWith("/dashboard?tab=wallet")) return Wallet;
  if (path.startsWith("/dashboard?tab=returns")) return TrendingUp;
  if (path.startsWith("/dashboard?tab=certificates") || path.startsWith("/dashboard?tab=verification"))
    return BadgeCheck;
  if (path.startsWith("/dashboard?tab=documents") || path.startsWith("/reports")) return FileText;
  if (path.startsWith("/dashboard?tab=installments")) return Receipt;
  if (path.startsWith("/dashboard")) return LayoutDashboard;
  if (path.startsWith("/property") || path.startsWith("/marketplace") || path.startsWith("/developers"))
    return Building2;
  if (path.startsWith("/kyc") || path.startsWith("/settings")) return ShieldCheck;
  if (path.startsWith("/support")) return LifeBuoy;
  if (path.startsWith("/fees")) return Receipt;
  if (path.startsWith("/faq")) return HelpCircle;
  if (path.startsWith("/how-it-works")) return BookOpen;
  if (path.startsWith("/exit") || path.startsWith("/secondary") || path.startsWith("/liquidity"))
    return ArrowDownToLine;
  return Compass;
}

export function greeting(firstName: string | null, now = new Date()): string {
  const h = now.getHours();
  const part = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  return firstName ? `${part}, ${firstName}` : "Welcome to Capimax PropShare";
}
