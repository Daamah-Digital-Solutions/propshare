import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Building2, Check, Loader2, MapPin, ShieldCheck, X } from "lucide-react";
import type { AssistantCard, ConfirmActionCard, LinkCard, Proposal } from "@/lib/assistantApi";
import { assistantApi } from "@/lib/assistantApi";
import { ApiError, assetUrl } from "@/lib/api";
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
  return null;
}
