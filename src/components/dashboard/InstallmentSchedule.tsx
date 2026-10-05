import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
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
import { Wallet, ArrowRight } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Calendar,
  CheckCircle2,
  Clock,
  AlertCircle,
  Download,
  Eye,
  ChevronDown,
  MapPin,
  Building2,
  Landmark,
  Loader2,
  Tag,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { format } from "date-fns";
import { shortDate } from "@/lib/money";
import { PaymentReturnStatus } from "@/components/dashboard/PaymentReturnStatus";
import { toast } from "sonner";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  installmentsApi,
  walletApi,
  ApiError,
  type InstallmentPayment,
  type InstallmentPlan,
} from "@/lib/api";

/**
 * Installment plans (Group 6 / Task 6) — REAL progressive-vesting schedules, presented
 * PER PROPERTY. Each plan card shows the property it belongs to (image, title, location, SPV),
 * a full summary (contract value, paid to date, remaining, next payment, ownership vested), a
 * "View schedule" toggle that reveals the complete payment table, and a "Download" button that
 * fetches a branded PDF (official design + logo). A due/overdue installment can be paid early.
 *
 * A running plan is also a POSITION with a value: all its units at the property's current
 * unit price, less what is still to pay. The card shows it and offers to sell the whole
 * position on the secondary market (the buyer takes the plan over).
 */

const statusMeta: Record<
  string,
  { label: string; variant: "default" | "secondary" | "outline" | "destructive" }
> = {
  scheduled: { label: "Scheduled", variant: "secondary" },
  paid: { label: "Paid", variant: "default" },
  overdue: { label: "Overdue", variant: "destructive" },
  cancelled: { label: "Cancelled", variant: "outline" },
};

// A plan that has not started, or never did: what it waits for / why it ended.
const PLAN_STATE: Record<string, { label: string; hint: string }> = {
  pending_payment: {
    label: "Waiting for the down payment",
    hint: "Its units are held for you while the down payment is being paid.",
  },
  pending_review: {
    label: "Nova certificate under review",
    hint: "Our team is reviewing your Nova Sukuk certificate; the units are held for you meanwhile. The plan starts once it is approved.",
  },
  cancelled: {
    label: "Not started",
    hint: "The down payment was not completed, so the units held for this plan went back on sale.",
  },
  expired: {
    label: "Not started",
    hint: "The down payment was not made in time, so the units held for this plan went back on sale.",
  },
};

const num = (s: string) => Number(s) || 0;
// Whole dollars stay short ($2,688); an amount with cents shows them ($85.09), so what the
// Pay button says is exactly what the wallet is charged.
const fmtUSD = (n: number) => {
  const digits = Math.round(n * 100) % 100 === 0 ? 0 : 2;
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
};

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

function Stat({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-lg border bg-muted/30 p-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={`text-base font-bold ${accent ? "text-primary" : "text-foreground"}`}>
        {value}
      </div>
      {sub && <div className="text-[11px] text-muted-foreground mt-0.5">{sub}</div>}
    </div>
  );
}

function PlanCard({
  plan,
  prepareId = null,
  onPrepared,
}: {
  plan: InstallmentPlan;
  /** A payment the assistant prepared (?pay=<id>): open its confirmation. */
  prepareId?: string | null;
  onPrepared?: () => void;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [downloading, setDownloading] = useState(false);
  // The installment the user tapped "Pay now" on — drives the confirmation dialog. The charge
  // is a REAL wallet debit, so we confirm the amount + source before it goes through.
  const [confirming, setConfirming] = useState<InstallmentPayment | null>(null);
  const [prepared, setPrepared] = useState(false);
  useEffect(() => {
    const payment = prepareId ? plan.payments.find((p) => p.id === prepareId) : undefined;
    if (!payment) return;
    // only a payment the user could pay here themselves; paying stays their own click
    if (
      plan.status === "active" &&
      (payment.status === "scheduled" || payment.status === "overdue") &&
      payment.seq > 0
    ) {
      setConfirming(payment);
      setPrepared(true);
      setOpen(true);
    }
    onPrepared?.();
  }, [prepareId, plan.payments, plan.status, onPrepared]);

  // Wallet balance, so the confirmation can show what's available and flag a shortfall up front.
  const { data: wallet } = useQuery({ queryKey: ["wallet"], queryFn: walletApi.getMe });
  const walletBalance = num(wallet?.balance ?? "0");

  const payMutation = useMutation({
    mutationFn: (paymentId: string) => installmentsApi.pay(paymentId),
    onSuccess: () => {
      setConfirming(null);
      queryClient.invalidateQueries({ queryKey: ["installments"] });
      queryClient.invalidateQueries({ queryKey: ["wallet"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
      toast.success("Installment paid", { description: "Your ownership has vested further." });
    },
    onError: (err: unknown) => {
      const code = err instanceof ApiError ? err.code : undefined;
      toast.error("Could not pay installment", {
        description:
          code === "INSUFFICIENT_FUNDS"
            ? "Your wallet balance is too low. Add funds and try again."
            : err instanceof Error
              ? err.message
              : "Please try again.",
      });
    },
  });

  const total = plan.payments.reduce((a, p) => a + num(p.total_amount), 0);
  const paidPayments = plan.payments.filter((p) => p.status === "paid");
  const paid = paidPayments.reduce((a, p) => a + num(p.total_amount), 0);
  const remaining = total - paid;
  const nextDue = plan.payments
    .filter((p) => p.status !== "paid")
    .sort((a, b) => +new Date(a.due_date) - +new Date(b.due_date))[0];
  const vestedPct = plan.units_total
    ? Math.round((plan.vested_units / plan.units_total) * 100)
    : 0;
  const location = plan.property_location ?? plan.property_city;

  const download = async () => {
    setDownloading(true);
    try {
      const blob = await installmentsApi.downloadSchedule(plan.id);
      saveBlob(blob, `installment-schedule-${plan.property_slug ?? plan.property_id}.pdf`);
      toast.success("Schedule downloaded");
    } catch {
      toast.error("Could not download the schedule", { description: "Please try again." });
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col sm:flex-row">
        {/* Property image — so it's clear which property is under installment */}
        <div className="sm:w-44 h-32 sm:h-auto bg-muted shrink-0 flex items-center justify-center">
          {plan.property_image ? (
            <img
              src={plan.property_image}
              alt={plan.property_title}
              className="h-full w-full object-cover"
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
            />
          ) : (
            <Building2 className="h-8 w-8 text-muted-foreground" />
          )}
        </div>

        <div className="flex-1 p-5 space-y-3 min-w-0">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-lg font-bold leading-tight truncate">{plan.property_title}</h3>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                {location && (
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="h-3 w-3" /> {location}
                  </span>
                )}
                {plan.property_spv && (
                  <span className="inline-flex items-center gap-1">
                    <Landmark className="h-3 w-3" /> {plan.property_spv}
                  </span>
                )}
              </div>
            </div>
            {plan.status === "completed" ? (
              <Badge className="gap-1 shrink-0">
                <CheckCircle2 size={12} /> Handover complete
              </Badge>
            ) : PLAN_STATE[plan.status] ? (
              <Badge variant="outline" className="gap-1 shrink-0">
                <Clock size={12} /> {PLAN_STATE[plan.status].label}
              </Badge>
            ) : (
              <Badge variant="secondary" className="gap-1 shrink-0">
                <Clock size={12} /> Active
              </Badge>
            )}
          </div>

          {PLAN_STATE[plan.status] && (
            <div
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground"
              data-testid="plan-state"
            >
              <span>
                {plan.failure_reason === "units_unavailable_refunded"
                  ? "Its units were taken before your down payment confirmed, so the payment was refunded to your wallet."
                  : PLAN_STATE[plan.status].hint}
                {plan.failure_reason === "sukuk_rejected" &&
                  " Your Nova certificate was not accepted — the reason is in your notifications."}
              </span>
              {plan.status === "pending_payment" && plan.checkout_url && (
                <Button asChild size="sm" variant="outline">
                  <a href={plan.checkout_url}>Complete the payment</a>
                </Button>
              )}
            </div>
          )}

          <div className="text-sm text-muted-foreground">
            {plan.units_total} units · ${plan.unit_price}/unit · {plan.duration_months} months ·{" "}
            {plan.down_payment_pct}% down · {plan.fee_rate}% fee/payment
          </div>

          {/* Full summary — the "complete details" the schedule was missing */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Contract value" value={fmtUSD(total)} />
            <Stat
              label="Paid to date"
              value={fmtUSD(paid)}
              sub={`${paidPayments.length}/${plan.payments.length} payments`}
            />
            <Stat label="Remaining" value={fmtUSD(remaining)} accent />
            <Stat
              label="Next payment"
              value={nextDue ? fmtUSD(num(nextDue.total_amount)) : "—"}
              sub={
                nextDue
                  ? format(new Date(nextDue.due_date), "MMM dd, yyyy")
                  : plan.status === "completed"
                    ? "Completed"
                    : "—"
              }
            />
          </div>

          <div>
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>Ownership vested</span>
              <span>
                {plan.vested_units}/{plan.units_total} units ({vestedPct}%)
              </span>
            </div>
            <Progress value={vestedPct} />
          </div>

          {plan.status === "active" && plan.position && (
            <div
              className="rounded-lg border border-primary/20 bg-primary/5 p-3 space-y-2"
              data-testid="plan-position"
            >
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <Stat
                  label="Unit price now"
                  value={fmtUSD(num(plan.position.price))}
                  sub={
                    plan.acquired_at
                      ? `you bought at ${fmtUSD(num(plan.position.entry_price))}`
                      : `you locked ${fmtUSD(num(plan.unit_price))}`
                  }
                />
                <Stat
                  label="Position value now"
                  value={fmtUSD(num(plan.position.value))}
                  sub={`${plan.units_total} units`}
                />
                <Stat
                  label="Your part of it"
                  value={fmtUSD(Math.max(0, num(plan.position.equity)))}
                  sub={`${fmtUSD(num(plan.position.cost))} you put in ${
                    num(plan.position.gain) < 0 ? "−" : "+"
                  } ${fmtUSD(Math.abs(num(plan.position.gain)))}`}
                  accent
                />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <span
                  className={`inline-flex items-center gap-1 ${
                    num(plan.position.gain) < 0 ? "text-destructive" : "text-primary"
                  }`}
                >
                  {num(plan.position.gain) < 0 ? <TrendingDown size={13} /> : <TrendingUp size={13} />}
                  {num(plan.position.gain) === 0
                    ? `The unit price has not changed since you ${plan.acquired_at ? "bought this position" : "started"}.`
                    : `${num(plan.position.gain) > 0 ? "+" : "−"}${fmtUSD(Math.abs(num(plan.position.gain)))} since you ${
                        plan.acquired_at ? "bought this position" : "started"
                      }, on all ${plan.units_total} units.`}
                </span>
                {plan.listing_id ? (
                  <Button asChild size="sm" variant="outline" className="gap-1.5">
                    <Link to="/secondary-market?tab=activity">
                      <Tag className="h-4 w-4" /> Listed for sale · manage
                    </Link>
                  </Button>
                ) : plan.position.blocked === "pledged" ||
                  plan.position.blocked === "lockup" ||
                  num(plan.position.equity) <= 0 ? null : (
                  <Button asChild size="sm" className="gap-1.5">
                    <Link to={`/secondary-market?tab=sell&plan=${plan.id}`}>
                      <Tag className="h-4 w-4" /> Sell this position
                    </Link>
                  </Button>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground" data-testid="plan-position-note">
                {plan.listing_id
                  ? "This position is listed for sale. Until it sells, its installments are still charged from your wallet, and what a buyer pays you grows by the principal of each one you pay (installment fees are not returned)."
                  : plan.position.blocked === "pledged"
                    ? "This plan was started with a Nova Sukuk certificate: its units are pledged to Nova Finance, so the position cannot be sold until the pledge is released."
                    : plan.position.blocked === "lockup"
                      ? `This position is in a lock-up until ${shortDate(plan.position.lockup_until ?? null)}: it can be listed for sale after that.`
                      : num(plan.position.equity) <= 0
                        ? "At today's unit price the position is worth less than what is still to pay on it, so it cannot be sold for now. Nothing more is owed because of that: installments are paid as before."
                        : "You can list the whole position for sale: a buyer pays you your part (the principal you paid plus the price change; installment fees are not returned) and carries on with the remaining installments."}
                {plan.acquired_at &&
                  ` You took this plan over on ${format(new Date(plan.acquired_at), "MMM dd, yyyy")}; payments before that were made by the previous holder.`}
              </p>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              onClick={() => setOpen((o) => !o)}
            >
              <Eye className="h-4 w-4" /> {open ? "Hide schedule" : "View schedule"}
              <ChevronDown
                className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`}
              />
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              onClick={download}
              disabled={downloading}
            >
              {downloading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              Download
            </Button>
          </div>
        </div>
      </div>

      {open && (
        <CardContent className="p-5 pt-0 space-y-3">
          {plan.status !== "completed" && (
            <div className="flex items-start gap-2 rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span>
                Rental income begins at handover (final payment). The units of this plan are sold
                together with it: you can sell the whole position at any time, and the buyer carries on
                with the remaining installments.
              </span>
            </div>
          )}

          <div className="border rounded-lg overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Payment</TableHead>
                  <TableHead>Due</TableHead>
                  <TableHead className="text-right">Base</TableHead>
                  <TableHead className="text-right">Fee</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {plan.payments.map((p: InstallmentPayment) => {
                  const st = statusMeta[p.status] ?? {
                    label: p.status,
                    variant: "secondary" as const,
                  };
                  // only a running plan is paid (one waiting for its down payment or a Nova
                  // review, or one that never started, is not)
                  const payable =
                    plan.status === "active" &&
                    (p.status === "scheduled" || p.status === "overdue") &&
                    p.seq > 0;
                  return (
                    <TableRow key={p.id}>
                      <TableCell className="font-medium">
                        {p.kind === "downpayment" ? "Down payment" : `Month ${p.seq}`}
                      </TableCell>
                      <TableCell>{format(new Date(p.due_date), "MMM dd, yyyy")}</TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        ${p.base_amount}
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        ${p.fee_amount}
                      </TableCell>
                      <TableCell className="text-right font-semibold">${p.total_amount}</TableCell>
                      <TableCell>
                        <Badge variant={st.variant} className="text-[10px]">
                          {st.label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        {payable && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={payMutation.isPending}
                            onClick={() => setConfirming(p)}
                          >
                            Pay now
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      )}

      {/* Payment confirmation — makes the charge a deliberate, clearly wallet-funded step
          (not an instant "fake" click). Shows the amount, the wallet source + balance, what
          it vests, and blocks when the balance is short. */}
      <AlertDialog
        open={!!confirming}
        onOpenChange={(o) => {
          if (!o) {
            setConfirming(null);
            setPrepared(false);
          }
        }}
      >
        <AlertDialogContent>
          {confirming &&
            (() => {
              const amount = num(confirming.total_amount);
              const short = walletBalance < amount;
              const label =
                confirming.kind === "downpayment"
                  ? "down payment"
                  : `installment (Month ${confirming.seq})`;
              return (
                <>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Confirm installment payment</AlertDialogTitle>
                    <AlertDialogDescription asChild>
                      <div className="space-y-3 pt-1">
                        {prepared && (
                          <div
                            data-testid="assistant-installment-banner"
                            className="rounded-lg border border-primary/30 bg-primary/5 px-3 py-2"
                          >
                            <span className="font-semibold text-primary">Prepared by PropShare AI.</span>{" "}
                            Nothing is charged until you press Pay.
                          </div>
                        )}
                        <p>
                          You're about to pay the {label} for{" "}
                          <span className="font-medium text-foreground">{plan.property_title}</span>.
                          This is charged now from your{" "}
                          <span className="font-medium text-foreground">wallet balance</span>.
                        </p>
                        <div className="rounded-lg border bg-muted/40 p-3 space-y-2 text-sm">
                          <div className="flex items-center justify-between">
                            <span className="text-muted-foreground">Amount (base + fee)</span>
                            <span className="font-semibold text-foreground">
                              ${confirming.base_amount} + ${confirming.fee_amount} ={" "}
                              {fmtUSD(amount)}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-muted-foreground inline-flex items-center gap-1.5">
                              <Wallet className="h-3.5 w-3.5" /> Wallet balance
                            </span>
                            <span
                              className={`font-semibold ${short ? "text-destructive" : "text-foreground"}`}
                            >
                              {fmtUSD(walletBalance)}
                            </span>
                          </div>
                          {confirming.vest_units > 0 && (
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground inline-flex items-center gap-1.5">
                                <ArrowRight className="h-3.5 w-3.5" /> Ownership this payment
                              </span>
                              <span className="font-semibold text-primary">
                                +{confirming.vest_units} unit(s) vested
                              </span>
                            </div>
                          )}
                        </div>
                        {short && (
                          <p className="text-destructive text-sm">
                            Your wallet balance is too low. Add funds, then try again.
                          </p>
                        )}
                      </div>
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel disabled={payMutation.isPending}>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      disabled={short || payMutation.isPending}
                      onClick={(e) => {
                        e.preventDefault(); // keep the dialog open until the mutation resolves
                        payMutation.mutate(confirming.id);
                      }}
                    >
                      {payMutation.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <>Pay {fmtUSD(amount)} from wallet</>
                      )}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </>
              );
            })()}
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

export const InstallmentSchedule = () => {
  // ?pay=<payment id>: a payment the assistant prepared. Remember it, consume the link.
  const [searchParams, setSearchParams] = useSearchParams();
  const [payId, setPayId] = useState<string | null>(null);
  const clearPayId = useCallback(() => setPayId(null), []);
  useEffect(() => {
    const id = searchParams.get("pay");
    if (!id) return;
    setPayId(id);
    const rest = new URLSearchParams(searchParams);
    rest.delete("pay");
    setSearchParams(rest, { replace: true });
  }, [searchParams, setSearchParams]);
  const { data: plans, isLoading } = useQuery({
    queryKey: ["installments"],
    queryFn: installmentsApi.list,
  });

  const list = plans ?? [];

  return (
    <div className="space-y-6">
      {/* Back from a down-payment checkout: follow it until the plan starts */}
      <PaymentReturnStatus kind="plan" />
      <div className="flex items-center gap-2">
        <Calendar className="h-5 w-5 text-primary" />
        <h2 className="text-2xl font-bold">Installment Plans</h2>
      </div>

      {isLoading ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            Loading…
          </CardContent>
        </Card>
      ) : list.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="py-12 flex flex-col items-center text-center gap-3">
            <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
              <Calendar className="h-6 w-6 text-muted-foreground" />
            </div>
            <h3 className="text-lg font-semibold">No installment plans yet</h3>
            <p className="text-sm text-muted-foreground max-w-md">
              Buy an under-construction property in scheduled installments from its page — your
              ownership vests with each payment, and the schedule appears here.
            </p>
          </CardContent>
        </Card>
      ) : (
        list.map((plan) => (
          <PlanCard key={plan.id} plan={plan} prepareId={payId} onPrepared={clearPayId} />
        ))
      )}
    </div>
  );
};

export default InstallmentSchedule;
