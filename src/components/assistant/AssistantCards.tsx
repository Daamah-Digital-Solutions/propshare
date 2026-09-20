import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Building2, Check, Loader2, X } from "lucide-react";
import type { AssistantCard, ConfirmActionCard, Proposal } from "@/lib/assistantApi";
import { assistantApi } from "@/lib/assistantApi";
import { ApiError } from "@/lib/api";

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
      className="mt-2 rounded-xl border border-primary/30 bg-primary/5 p-3 text-sm"
      data-testid="confirm-card"
    >
      <div className="font-medium text-foreground">{card.summary}</div>
      {state === "idle" || state === "busy" ? (
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            disabled={state === "busy" || !card.token}
            onClick={() => void decide(true)}
            className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-50"
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
            className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-xs font-medium disabled:opacity-50"
          >
            <X className="h-3.5 w-3.5" />
            Cancel
          </button>
        </div>
      ) : (
        <div
          className={
            state === "executed" ? "mt-2 text-xs text-primary" : "mt-2 text-xs text-muted-foreground"
          }
        >
          {note}
        </div>
      )}
      {!card.token && state === "idle" && (
        <div className="mt-1 text-[11px] text-muted-foreground">
          This confirmation has expired. Ask again to get a new one.
        </div>
      )}
    </div>
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
      <Link
        to={card.path}
        onClick={onClose}
        className="mt-2 inline-flex items-center gap-1 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-primary hover:bg-muted"
      >
        {card.label}
        <ArrowRight className="h-3.5 w-3.5" />
      </Link>
    );
  }
  if (card.kind === "property") {
    return (
      <Link
        to={card.path}
        onClick={onClose}
        className="mt-2 flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs hover:bg-muted"
      >
        <Building2 className="h-4 w-4 text-primary" />
        <span className="font-medium">{card.title ?? card.slug}</span>
        <ArrowRight className="ml-auto h-3.5 w-3.5" />
      </Link>
    );
  }
  if (card.kind === "properties") {
    return (
      <div className="mt-2 space-y-1">
        {card.items.slice(0, 5).map((p, i) =>
          p.path ? (
            <Link
              key={`${p.slug ?? i}`}
              to={p.path}
              onClick={onClose}
              className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs hover:bg-muted"
            >
              <Building2 className="h-4 w-4 shrink-0 text-primary" />
              <span className="min-w-0 flex-1 truncate">
                <span className="font-medium">{p.title}</span>
                {p.city ? <span className="text-muted-foreground"> · {p.city}</span> : null}
              </span>
              <span className="text-muted-foreground">
                {p.unit_price !== null && p.unit_price !== undefined
                  ? `${fmtMoney(p.unit_price)}/unit`
                  : ""}
              </span>
            </Link>
          ) : null,
        )}
      </div>
    );
  }
  if (card.kind === "confirm_action") return <ConfirmCard card={card} onDecided={onDecided} />;
  return null;
}
