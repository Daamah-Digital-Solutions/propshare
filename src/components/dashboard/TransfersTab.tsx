import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Loader2,
  Lock,
  MailCheck,
  RotateCcw,
  Send,
  ShieldCheck,
  X,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { OCCASIONS, TransferDialog } from "@/components/dashboard/TransferDialog";
import { useAuth } from "@/contexts/AuthContext";
import { ApiError, transfersApi, type TransferRow, type TransferStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Transfers (client, 2026-10-28, as on Capimax BRX): send property units or wallet balance to
 * anyone by email, follow every transfer by its TR- number, and cancel one before it is
 * delivered. The wallet's Transfer button opens the same dialog (?tab=transfers&new=balance).
 */

const STATUS: Record<TransferStatus, { label: string; cls: string }> = {
  scheduled: { label: "Scheduled", cls: "border-blue-500/20 bg-blue-500/10 text-blue-600" },
  waiting: { label: "Waiting for the recipient", cls: "border-amber-500/20 bg-amber-500/10 text-amber-600" },
  delivered: { label: "Delivered", cls: "border-emerald-500/20 bg-emerald-500/10 text-emerald-600" },
  cancelled: { label: "Cancelled — returned", cls: "bg-muted text-muted-foreground" },
  expired: { label: "Expired — returned", cls: "bg-muted text-muted-foreground" },
  failed: { label: "Failed — returned", cls: "border-destructive/20 bg-destructive/10 text-destructive" },
};

const STEPS: { icon: LucideIcon; text: string }[] = [
  { icon: Lock, text: "What you send is held at once, so it can't be sold or sent twice." },
  {
    icon: ShieldCheck,
    text: "If the recipient's email is confirmed and identity verified, it reaches them right away or on the date you choose.",
  },
  {
    icon: MailCheck,
    text: "If not, they get an invitation and receive it automatically once they sign up and verify with that email.",
  },
  {
    icon: RotateCcw,
    text: "If it isn't received within 30 days it comes back to you; you can cancel it here before delivery.",
  },
];

type Filter = "all" | "sent" | "received" | "waiting";
const isOpen = (t: TransferRow) => t.status === "scheduled" || t.status === "waiting";
const money = (v: string) => Number(v).toLocaleString("en-US", { style: "currency", currency: "USD" });
const day = (iso?: string | null) =>
  iso
    ? new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString("en-US", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "";
const what = (t: TransferRow) =>
  t.asset === "units"
    ? `${(t.units ?? 0).toLocaleString()} unit${t.units === 1 ? "" : "s"} · ${t.property_title ?? "Property"}`
    : t.asset === "plan"
      ? `${(t.units ?? 0).toLocaleString()} unit(s) on an installment plan · ${t.property_title ?? "Property"}`
      : `${money(t.amount)} wallet balance`;

export function TransfersTab() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState(false);
  const [initialAsset, setInitialAsset] = useState<"units" | "plan" | "balance">("units");
  const [cancelling, setCancelling] = useState<TransferRow | null>(null);

  const verified = !!user?.email_verified && user?.kyc_status === "verified";
  const { data, isLoading } = useQuery({ queryKey: ["transfers"], queryFn: () => transfersApi.list() });
  const rows = useMemo(() => data?.items ?? [], [data]);

  // the wallet's Transfer button: /dashboard?tab=transfers&new=balance
  useEffect(() => {
    const wanted = params.get("new");
    if (wanted === "balance" || wanted === "units") {
      setInitialAsset(wanted);
      if (verified) setOpen(true);
      const next = new URLSearchParams(params);
      next.delete("new");
      setParams(next, { replace: true });
    }
  }, [params, setParams, verified]);

  const cancel = useMutation({
    mutationFn: (id: string) => transfersApi.cancel(id),
    onSuccess: (t) => {
      toast.success(`${t.reference} cancelled — everything was returned to you`);
      qc.invalidateQueries();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not cancel the transfer."),
    onSettled: () => setCancelling(null),
  });

  const counts = {
    sent: rows.filter((t) => t.direction === "sent").length,
    received: rows.filter((t) => t.direction === "received").length,
    waiting: rows.filter(isOpen).length,
    delivered: rows.filter((t) => t.status === "delivered").length,
  };
  const shown = rows.filter((t) =>
    filter === "all" ? true : filter === "waiting" ? isOpen(t) : t.direction === filter,
  );
  const newTransfer = (asset: "units" | "plan" | "balance") => {
    setInitialAsset(asset);
    setOpen(true);
  };

  return (
    <div className="space-y-6" data-testid="transfers-tab">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
            <Send className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-foreground">Transfers</h2>
            <p className="mt-1 text-muted-foreground">
              Send property units or wallet balance to anyone by email, follow every transfer and
              cancel it before delivery.
            </p>
          </div>
        </div>
        {verified && (
          <div className="flex gap-2">
            <Button variant="outline" className="gap-2" onClick={() => newTransfer("balance")}>
              Transfer balance
            </Button>
            <Button className="gap-2" onClick={() => newTransfer("units")}>
              <Send className="h-4 w-4" /> Transfer units
            </Button>
          </div>
        )}
      </div>

      {!verified && (
        <Card className="border-amber-500/30 bg-amber-500/5">
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-foreground">
              To send a transfer, confirm your email address and verify your identity first.
            </p>
            <Button asChild variant="outline" size="sm">
              <Link to="/kyc">Verify my identity</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((s) => (
          <Card key={s.text}>
            <CardContent className="flex gap-3 p-4">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                <s.icon className="h-4 w-4 text-primary" />
              </div>
              <p className="text-sm text-muted-foreground">{s.text}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          { label: "Sent", n: counts.sent, icon: ArrowUpRight, tone: "bg-primary/10 text-primary" },
          { label: "Received", n: counts.received, icon: ArrowDownLeft, tone: "bg-emerald-500/10 text-emerald-600" },
          { label: "Waiting", n: counts.waiting, icon: Clock, tone: "bg-amber-500/10 text-amber-600" },
          { label: "Delivered", n: counts.delivered, icon: CheckCircle2, tone: "bg-sky-500/10 text-sky-600" },
        ].map((s) => (
          <Card key={s.label}>
            <CardContent className="flex items-center gap-3 p-4">
              <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg", s.tone)}>
                <s.icon className="h-5 w-5" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground" data-testid={`count-${s.label.toLowerCase()}`}>
                  {isLoading ? "—" : s.n}
                </p>
                <p className="text-xs text-muted-foreground">{s.label}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Show">
        {(
          [
            ["all", "All", rows.length],
            ["sent", "Sent", counts.sent],
            ["received", "Received", counts.received],
            ["waiting", "Waiting", counts.waiting],
          ] as [Filter, string, number][]
        ).map(([id, label, n]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={filter === id}
            onClick={() => setFilter(id)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-sm transition-colors",
              filter === id ? "border-primary/40 bg-primary/10 text-primary" : "border-border hover:border-primary/30",
            )}
          >
            {label} <span className="text-muted-foreground">({n})</span>
          </button>
        ))}
      </div>

      <Card>
        <CardContent className="divide-y divide-border p-0" data-testid="transfer-list">
          {isLoading ? (
            <div className="flex justify-center p-10">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : shown.length === 0 ? (
            <div className="space-y-3 p-10 text-center">
              <p className="text-muted-foreground">
                {filter === "all" ? "You haven't sent or received a transfer yet." : "No transfers here."}
              </p>
              {filter === "all" && verified && (
                <Button variant="outline" onClick={() => newTransfer("units")}>
                  Send your first transfer
                </Button>
              )}
            </div>
          ) : (
            shown.map((t) => {
              const st = STATUS[t.status];
              const sent = t.direction === "sent";
              return (
                <div key={t.id} className="space-y-2 p-4" data-testid="transfer-row">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-3">
                      <div
                        className={cn(
                          "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                          sent ? "bg-primary/10 text-primary" : "bg-emerald-500/10 text-emerald-600",
                        )}
                      >
                        {sent ? <ArrowUpRight className="h-5 w-5" /> : <ArrowDownLeft className="h-5 w-5" />}
                      </div>
                      <div className="min-w-0">
                        <p className="font-medium text-foreground">
                          {sent ? "To " : "From "}
                          <span dir="auto" className="break-all">
                            {t.counterparty}
                          </span>
                        </p>
                        <p className="text-sm text-foreground/80">{what(t)}</p>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Badge variant="outline" className={st.cls}>
                        {st.label}
                      </Badge>
                      {t.can_cancel && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="gap-1.5 text-destructive"
                          aria-label={`Cancel ${t.reference}`}
                          disabled={cancel.isPending}
                          onClick={() => setCancelling(t)}
                        >
                          <X className="h-3.5 w-3.5" /> Cancel
                        </Button>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 ps-[52px] text-xs text-muted-foreground">
                    <span dir="ltr" className="font-mono">
                      {t.reference}
                    </span>
                    <span>Created {day(t.created_at)}</span>
                    {t.status === "scheduled" && <span>Delivers on {day(t.deliver_on)}</span>}
                    {t.status === "waiting" && t.expires_at && <span>Must be received by {day(t.expires_at)}</span>}
                    {t.status === "delivered" && t.delivered_at && <span>Delivered {day(t.delivered_at)}</span>}
                    {sent && t.recipient_email && <span dir="ltr">{t.recipient_email}</span>}
                    {sent && Number(t.fee) > 0 && <span>Fee {money(t.fee)}</span>}
                    {t.occasion && <span>{OCCASIONS.find((o) => o.id === t.occasion)?.label}</span>}
                  </div>
                  {t.status === "waiting" && sent && (
                    <p className="ps-[52px] text-xs text-amber-600">
                      We invited the recipient; it reaches them as soon as they confirm their email
                      and verify their identity.
                    </p>
                  )}
                  {t.message && (
                    <p className="ms-[52px] rounded-lg bg-muted/40 px-3 py-2 text-sm text-foreground/90" dir="auto">
                      “{t.message}”
                    </p>
                  )}
                  {t.closed_reason && t.status !== "delivered" && (
                    <p className="ps-[52px] text-xs text-muted-foreground">{t.closed_reason}</p>
                  )}
                </div>
              );
            })
          )}
        </CardContent>
      </Card>

      <TransferDialog open={open} onOpenChange={setOpen} initialAsset={initialAsset} />

      <AlertDialog open={!!cancelling} onOpenChange={(o) => !o && setCancelling(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel {cancelling?.reference}?</AlertDialogTitle>
            <AlertDialogDescription>
              {cancelling && what(cancelling)} to {cancelling?.counterparty} will not be sent.
              {cancelling?.asset === "units"
                ? " The units are released back to you"
                : " The amount goes back to your wallet"}
              {cancelling && Number(cancelling.fee) > 0 ? ", with the fee." : "."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => cancelling && cancel.mutate(cancelling.id)}
            >
              Cancel transfer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
