import { useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  ArrowDownToLine,
  ArrowRight,
  Building2,
  Check,
  FileSpreadsheet,
  FileText,
  Loader2,
  MapPin,
  Receipt,
  ShieldCheck,
  Wallet,
  X,
  type LucideIcon,
} from "lucide-react";
import type {
  AssistantCard,
  CheckoutCard,
  ConfirmActionCard,
  DepositCard,
  LinkCard,
  Proposal,
  StatementCard,
  WithdrawalCard,
} from "@/lib/assistantApi";
import { assistantApi } from "@/lib/assistantApi";
import { ApiError, assetUrl, walletApi, type StatementFormat } from "@/lib/api";
import { saveBlob } from "@/lib/certificates";
import { cn } from "@/lib/utils";
import { linkIcon } from "@/components/assistant/assistantUi";

/**
 * Cards are built by the SERVER from tool results (never by the model): platform links,
 * property previews and the confirm/cancel card for a proposed action. The confirmation
 * token arrives only here (in the browser) — the model never sees it.
 */

function fmtMoney(v: number | null | undefined): string {
  if (v === null || v === undefined) return "";
  return `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export function ConfirmCard({
  card,
  onDecided,
}: {
  card: ConfirmActionCard;
  onDecided?: (proposal: Proposal) => void;
}) {
  const [state, setState] = useState<"idle" | "busy" | "executed" | "failed" | "cancelled">(
    "idle",
  );
  const [note, setNote] = useState<string>("");

  const decide = async (confirm: boolean) => {
    setState("busy");
    try {
      const p = confirm
        ? await assistantApi.confirm(card.proposal_id, card.token ?? "")
        : await assistantApi.cancel(card.proposal_id);
      const ok = p.status === "executed";
      setState(confirm ? (ok ? "executed" : "failed") : "cancelled");
      const result = (p.result ?? {}) as { message?: string; ticket_no?: string };
      setNote(
        confirm
          ? ok
            ? result.ticket_no
              ? `Done — ticket ${result.ticket_no} opened.`
              : "Done."
            : result.message || "Could not complete this action."
          : "Cancelled.",
      );
      onDecided?.(p);
    } catch (err) {
      setState("failed");
      setNote(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  };

  return (
    <div
      className="mt-2 overflow-hidden rounded-2xl border border-accent/40 bg-card shadow-sm"
      data-testid="confirm-card"
    >
      <div className="flex items-center gap-2 border-b border-accent/20 bg-accent/10 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-accent-foreground/90">
        <ShieldCheck className="h-3.5 w-3.5 text-accent" />
        <span className="text-foreground/80">Needs your confirmation</span>
      </div>
      <div className="p-3 text-sm">
        <div className="font-medium text-foreground">{card.summary}</div>
        {state === "idle" || state === "busy" ? (
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              disabled={state === "busy" || !card.token}
              onClick={() => void decide(true)}
              className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground shadow-sm transition hover:brightness-110 disabled:opacity-50"
            >
              {state === "busy" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Check className="h-3.5 w-3.5" />
              )}
              Confirm
            </button>
            <button
              type="button"
              disabled={state === "busy"}
              onClick={() => void decide(false)}
              className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-border bg-background px-3 py-2 text-xs font-medium transition hover:bg-muted disabled:opacity-50"
            >
              <X className="h-3.5 w-3.5" />
              Cancel
            </button>
          </div>
        ) : (
          <div
            className={cn(
              "mt-2 flex items-center gap-1.5 text-xs",
              state === "executed" ? "font-medium text-primary" : "text-muted-foreground",
            )}
          >
            {state === "executed" ? <Check className="h-3.5 w-3.5" /> : null}
            {note}
          </div>
        )}
        {!card.token && state === "idle" && (
          <div className="mt-1 text-[11px] text-muted-foreground">
            This confirmation has expired. Ask again to get a new one.
          </div>
        )}
      </div>
    </div>
  );
}

function money(v: string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n)
    ? `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : v;
}

/** The order the assistant prepared. The button opens the checkout pre-filled; paying is the
 * user's own click on that page (the assistant never charges anything). */
export function CheckoutOrderCard({ card, onClose }: { card: CheckoutCard; onClose?: () => void }) {
  const installment = card.purchase_type === "installment";
  const rows: [string, string][] = [
    ["Property", card.title ?? "—"],
    ["Units", String(card.units)],
    ["Unit price", money(card.unit_price)],
    ["Subtotal", money(card.subtotal)],
    installment
      ? ["Plan", `${card.duration_months ?? 12} months, down payment today`]
      : ["Platform fee", money(card.platform_fee)],
  ];
  return (
    <div className="mt-2 overflow-hidden rounded-2xl border border-primary/30 bg-card shadow-sm" data-testid="checkout-card">
      <div className="flex items-center gap-2 border-b border-primary/15 bg-primary/5 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-primary">
        <Receipt className="h-3.5 w-3.5" />
        Your order is ready
      </div>
      <div className="space-y-1.5 px-3 pt-3 text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-baseline justify-between gap-3">
            <span className="text-muted-foreground">{k}</span>
            <span className="text-right font-medium text-foreground">{v}</span>
          </div>
        ))}
        <div className="mt-1 flex items-baseline justify-between gap-3 border-t border-border pt-2">
          <span className="font-semibold text-foreground">{installment ? "Due today" : "Total to pay"}</span>
          <span className="text-base font-bold text-foreground">{money(card.total_now)}</span>
        </div>
      </div>
      {card.notes.length > 0 && (
        <ul className="mx-3 mt-2 space-y-1 rounded-xl bg-accent/10 px-3 py-2 text-[11px] text-foreground/80">
          {card.notes.map((n) => (
            <li key={n} className="flex gap-1.5">
              <AlertCircle className="mt-0.5 h-3 w-3 shrink-0 text-accent" />
              {n}
            </li>
          ))}
        </ul>
      )}
      <div className="p-3">
        <Link
          to={card.path}
          onClick={onClose}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-3 py-2.5 text-xs font-semibold text-primary-foreground shadow-[0_6px_16px_-8px_hsl(var(--primary)/0.8)] transition hover:brightness-110"
        >
          {card.ready ? "Continue to payment" : "Review order"}
          <ArrowRight className="h-3.5 w-3.5 rtl:rotate-180" />
        </Link>
        <div className="mt-1.5 text-center text-[10.5px] text-muted-foreground">
          Opens the checkout pre-filled. Nothing is charged until you confirm payment.
        </div>
      </div>
    </div>
  );
}

type Row = [label: string, value: string];

/** The frame every prepared card shares: what was prepared, the figures, what still needs
 * doing, and the one next step. The step itself always happens on the platform's own page. */
function PreparedShell({
  testId,
  icon: Icon,
  title,
  rows,
  total,
  notes,
  children,
  footnote,
}: {
  testId: string;
  icon: LucideIcon;
  title: string;
  rows: Row[];
  total?: Row;
  notes: string[];
  children: React.ReactNode;
  footnote: string;
}) {
  return (
    <div className="mt-2 overflow-hidden rounded-2xl border border-primary/30 bg-card shadow-sm" data-testid={testId}>
      <div className="flex items-center gap-2 border-b border-primary/15 bg-primary/5 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-primary">
        <Icon className="h-3.5 w-3.5" />
        {title}
      </div>
      <div className="space-y-1.5 px-3 pt-3 text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-baseline justify-between gap-3">
            <span className="shrink-0 text-muted-foreground">{k}</span>
            <span className="text-right font-medium text-foreground">{v}</span>
          </div>
        ))}
        {total && (
          <div className="mt-1 flex items-baseline justify-between gap-3 border-t border-border pt-2">
            <span className="font-semibold text-foreground">{total[0]}</span>
            <span className="text-base font-bold text-foreground">{total[1]}</span>
          </div>
        )}
      </div>
      {notes.length > 0 && (
        <ul className="mx-3 mt-2 space-y-1 rounded-xl bg-accent/10 px-3 py-2 text-[11px] text-foreground/80">
          {notes.map((n) => (
            <li key={n} className="flex gap-1.5">
              <AlertCircle className="mt-0.5 h-3 w-3 shrink-0 text-accent" />
              {n}
            </li>
          ))}
        </ul>
      )}
      <div className="p-3">
        {children}
        <div className="mt-1.5 text-center text-[10.5px] text-muted-foreground">{footnote}</div>
      </div>
    </div>
  );
}

const CTA =
  "flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-3 py-2.5 text-xs font-semibold text-primary-foreground shadow-[0_6px_16px_-8px_hsl(var(--primary)/0.8)] transition hover:brightness-110 disabled:opacity-60";

function CtaLink({ to, label, onClose }: { to: string; label: string; onClose?: () => void }) {
  return (
    <Link to={to} onClick={onClose} className={CTA}>
      {label}
      <ArrowRight className="h-3.5 w-3.5 rtl:rotate-180" />
    </Link>
  );
}

/** A deposit the assistant prepared: the wallet opens with it filled in, the user deposits. */
export function DepositPreparedCard({ card, onClose }: { card: DepositCard; onClose?: () => void }) {
  const bank = card.method === "bank";
  return (
    <PreparedShell
      testId="deposit-card"
      icon={Wallet}
      title={card.ready ? "Your deposit is ready" : "Deposit prepared: one step first"}
      rows={[
        ["Method", card.method_label],
        ["Credited to", "Your PropShare wallet"],
      ]}
      total={["You add", money(card.amount)]}
      notes={card.notes}
      footnote={
        bank
          ? "Opens your wallet with the transfer details. Nothing moves until you send it."
          : "Opens your wallet with this deposit filled in. Nothing is charged until you confirm."
      }
    >
      <CtaLink
        to={card.path}
        onClose={onClose}
        label={!card.ready ? "Open wallet" : bank ? "Continue to bank transfer" : "Continue to payment"}
      />
    </PreparedShell>
  );
}

/** A withdrawal the assistant prepared, fee and net worked out; the user presses Withdraw. */
export function WithdrawalPreparedCard({ card, onClose }: { card: WithdrawalCard; onClose?: () => void }) {
  const instant = card.speed === "instant";
  const rows: Row[] = [
    ["Amount", money(card.amount)],
    ["Speed", instant ? "Instant (minutes)" : "Standard"],
    ["Fee", Number(card.fee) > 0 ? money(card.fee) : "Free"],
  ];
  if (card.destination) rows.push(["To", card.destination]);
  if (card.timing) rows.push(["Arrives", card.timing]);
  return (
    <PreparedShell
      testId="withdrawal-card"
      icon={ArrowDownToLine}
      title={card.ready ? "Your withdrawal is ready" : "Withdrawal prepared: one step first"}
      rows={rows}
      total={["You receive", money(card.net_amount)]}
      notes={card.notes}
      footnote="Opens your wallet with this withdrawal filled in. Nothing is sent until you confirm."
    >
      <CtaLink to={card.path} onClose={onClose} label={card.ready ? "Review & withdraw" : "Open wallet"} />
    </PreparedShell>
  );
}

const day = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });

/** An account statement for a period: downloads straight from the chat. */
export function StatementPreparedCard({ card }: { card: StatementCard }) {
  const [busy, setBusy] = useState<StatementFormat | null>(null);
  const [problem, setProblem] = useState("");
  const download = async (format: StatementFormat) => {
    setBusy(format);
    setProblem("");
    try {
      const blob = await walletApi.downloadStatement(card.start, card.end, format);
      saveBlob(blob, `capimax-statement-${card.start}-to-${card.end}.${format}`);
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : "Could not create the statement. Please try again.");
    } finally {
      setBusy(null);
    }
  };
  const order: StatementFormat[] = card.format === "xlsx" ? ["xlsx", "pdf"] : ["pdf", "xlsx"];
  return (
    <PreparedShell
      testId="statement-card"
      icon={FileText}
      title="Your statement is ready"
      rows={[
        ["Period", `${day(card.start)} – ${day(card.end)}`],
        ["Movements", String(card.movements)],
        ["Opening balance", money(card.opening_balance)],
        ["Money in", money(card.money_in)],
        ["Money out", money(card.money_out)],
      ]}
      total={["Closing balance", money(card.closing_balance)]}
      notes={problem ? [problem] : []}
      footnote="Downloads straight to your device. Dates are UTC, both days included."
    >
      <div className="flex gap-2">
        {order.map((f, i) => {
          const Icon = f === "pdf" ? FileText : FileSpreadsheet;
          return (
            <button
              key={f}
              type="button"
              disabled={busy !== null}
              onClick={() => void download(f)}
              className={cn(
                i === 0
                  ? CTA
                  : "flex w-full items-center justify-center gap-2 rounded-xl border border-border bg-background px-3 py-2.5 text-xs font-semibold text-foreground transition hover:border-primary/40 hover:bg-primary/5 disabled:opacity-60",
              )}
            >
              {busy === f ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Icon className="h-3.5 w-3.5" />}
              {f === "pdf" ? "Download PDF" : "Download Excel"}
            </button>
          );
        })}
      </div>
    </PreparedShell>
  );
}

/** A page button. The first button of a reply is the primary call to action. */
export function LinkButton({
  card,
  primary,
  onClose,
}: {
  card: LinkCard;
  primary?: boolean;
  onClose?: () => void;
}) {
  const Icon = linkIcon(card.path);
  return (
    <Link
      to={card.path}
      onClick={onClose}
      className={cn(
        "group inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition",
        primary
          ? "bg-primary text-primary-foreground shadow-[0_6px_16px_-8px_hsl(var(--primary)/0.8)] hover:brightness-110"
          : "border border-border bg-card text-foreground hover:border-primary/40 hover:bg-primary/5",
      )}
    >
      <Icon className={cn("h-3.5 w-3.5", primary ? "" : "text-primary")} />
      {card.label}
      <ArrowRight className="h-3.5 w-3.5 opacity-60 transition group-hover:translate-x-0.5 group-hover:opacity-100 rtl:rotate-180" />
    </Link>
  );
}

function PropertyTile({
  item,
  onClose,
}: {
  item: {
    slug?: string | null;
    title: string | null;
    city?: string | null;
    unit_price?: number | null;
    expected_yield?: number | null;
    image?: string | null;
    path: string;
  };
  onClose?: () => void;
}) {
  return (
    <Link
      to={item.path}
      onClick={onClose}
      className="group w-44 shrink-0 snap-start overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
    >
      <div className="relative h-24 w-full overflow-hidden bg-gradient-to-br from-primary/25 via-primary/10 to-accent/20">
        {item.image ? (
          <img
            src={assetUrl(item.image)}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
          />
        ) : (
          <Building2 className="absolute inset-0 m-auto h-8 w-8 text-primary/60" />
        )}
        {item.expected_yield !== null && item.expected_yield !== undefined ? (
          <span className="absolute left-2 top-2 rounded-full bg-background/90 px-2 py-0.5 text-[10px] font-semibold text-primary shadow-sm backdrop-blur">
            {item.expected_yield}% est. yield
          </span>
        ) : null}
      </div>
      <div className="space-y-0.5 p-2.5">
        <div className="line-clamp-2 text-xs font-semibold leading-snug text-foreground">
          {item.title ?? item.slug}
        </div>
        {item.city ? (
          <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <MapPin className="h-3 w-3" />
            {item.city}
          </div>
        ) : null}
        {item.unit_price !== null && item.unit_price !== undefined ? (
          <div className="pt-0.5 text-[11px] text-muted-foreground">
            <span className="font-semibold text-foreground">{fmtMoney(item.unit_price)}</span> / unit
          </div>
        ) : null}
      </div>
    </Link>
  );
}

export function AssistantCardView({
  card,
  onClose,
  onDecided,
}: {
  card: AssistantCard;
  onClose?: () => void;
  onDecided?: (proposal: Proposal) => void;
}) {
  if (card.kind === "link") {
    return (
      <div className="mt-2">
        <LinkButton card={card} onClose={onClose} />
      </div>
    );
  }
  if (card.kind === "property") {
    return (
      <div className="mt-2 flex">
        <PropertyTile item={card} onClose={onClose} />
      </div>
    );
  }
  if (card.kind === "properties") {
    const items = card.items.filter((p): p is typeof p & { path: string } => !!p.path).slice(0, 6);
    return (
      <div className="-mx-1 mt-2 flex snap-x gap-2 overflow-x-auto px-1 pb-1 [scrollbar-width:thin]">
        {items.map((p, i) => (
          <PropertyTile key={`${p.slug ?? i}`} item={p} onClose={onClose} />
        ))}
      </div>
    );
  }
  if (card.kind === "confirm_action") return <ConfirmCard card={card} onDecided={onDecided} />;
  if (card.kind === "checkout") return <CheckoutOrderCard card={card} onClose={onClose} />;
  if (card.kind === "deposit") return <DepositPreparedCard card={card} onClose={onClose} />;
  if (card.kind === "withdrawal") return <WithdrawalPreparedCard card={card} onClose={onClose} />;
  if (card.kind === "statement") return <StatementPreparedCard card={card} />;
  return null;
}
