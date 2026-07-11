import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
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
} from "lucide-react";
import { format } from "date-fns";
import { toast } from "sonner";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  installmentsApi,
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
 */

const statusMeta: Record<
  string,
  { label: string; variant: "default" | "secondary" | "outline" | "destructive" }
> = {
  scheduled: { label: "Scheduled", variant: "secondary" },
  paid: { label: "Paid", variant: "default" },
  overdue: { label: "Overdue", variant: "destructive" },
};

const num = (s: string) => Number(s) || 0;
const fmtUSD = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

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

function PlanCard({ plan }: { plan: InstallmentPlan }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const payMutation = useMutation({
    mutationFn: (paymentId: string) => installmentsApi.pay(paymentId),
    onSuccess: () => {
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
            ) : (
              <Badge variant="secondary" className="gap-1 shrink-0">
                <Clock size={12} /> Active
              </Badge>
            )}
          </div>

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
                Rental income begins at handover (final payment). Vested units appreciate with the
                property NAV but are held until the plan completes.
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
                  const payable = (p.status === "scheduled" || p.status === "overdue") && p.seq > 0;
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
                            onClick={() => payMutation.mutate(p.id)}
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
    </Card>
  );
}

export const InstallmentSchedule = () => {
  const { data: plans, isLoading } = useQuery({
    queryKey: ["installments"],
    queryFn: installmentsApi.list,
  });

  const list = plans ?? [];

  return (
    <div className="space-y-6">
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
        list.map((plan) => <PlanCard key={plan.id} plan={plan} />)
      )}
    </div>
  );
};

export default InstallmentSchedule;
