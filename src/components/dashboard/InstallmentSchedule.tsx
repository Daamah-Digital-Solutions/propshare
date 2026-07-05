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
import { Calendar, CheckCircle2, Clock, AlertCircle } from "lucide-react";
import { format } from "date-fns";
import { toast } from "sonner";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { installmentsApi, ApiError, type InstallmentPayment } from "@/lib/api";

/**
 * Installment plans (Group 6) — REAL progressive-vesting schedules. Each plan reserves its
 * allocation and vests ownership into the ledger per PAID payment; installments auto-charge
 * from the wallet on their due dates (a cron), and a due/overdue one can be paid early here.
 */

const statusMeta: Record<string, { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
  scheduled: { label: "Scheduled", variant: "secondary" },
  paid: { label: "Paid", variant: "default" },
  overdue: { label: "Overdue", variant: "destructive" },
};

export const InstallmentSchedule = () => {
  const queryClient = useQueryClient();
  const { data: plans, isLoading } = useQuery({
    queryKey: ["installments"],
    queryFn: installmentsApi.list,
  });

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

  const list = plans ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Calendar className="h-5 w-5 text-primary" />
        <h2 className="text-2xl font-bold">Installment Plans</h2>
      </div>

      {isLoading ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">Loading…</CardContent>
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
        list.map((plan) => {
          const vestedPct = plan.units_total
            ? Math.round((plan.vested_units / plan.units_total) * 100)
            : 0;
          return (
            <Card key={plan.id}>
              <CardContent className="p-5 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm text-muted-foreground">
                      {plan.units_total} units · ${plan.unit_price}/unit · {plan.duration_months} months
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      {plan.status === "completed" ? (
                        <Badge className="gap-1">
                          <CheckCircle2 size={12} /> Handover complete
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="gap-1">
                          <Clock size={12} /> Vesting ({plan.vested_units}/{plan.units_total} units)
                        </Badge>
                      )}
                      <span className="text-xs text-muted-foreground">Fee {plan.fee_rate}% per payment</span>
                    </div>
                  </div>
                  <div className="w-40">
                    <div className="text-xs text-muted-foreground mb-1">Ownership vested</div>
                    <Progress value={vestedPct} />
                  </div>
                </div>

                {plan.status !== "completed" && (
                  <div className="flex items-start gap-2 rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">
                    <AlertCircle size={14} className="mt-0.5 shrink-0" />
                    <span>
                      Rental income begins at handover (final payment). Vested units appreciate with
                      the property NAV but are held until the plan completes.
                    </span>
                  </div>
                )}

                <div className="border rounded-lg overflow-hidden">
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
                        const st = statusMeta[p.status] ?? { label: p.status, variant: "secondary" as const };
                        const payable = (p.status === "scheduled" || p.status === "overdue") && p.seq > 0;
                        return (
                          <TableRow key={p.id}>
                            <TableCell className="font-medium">
                              {p.kind === "downpayment" ? "Down payment" : `Month ${p.seq}`}
                            </TableCell>
                            <TableCell>{format(new Date(p.due_date), "MMM dd, yyyy")}</TableCell>
                            <TableCell className="text-right text-muted-foreground">${p.base_amount}</TableCell>
                            <TableCell className="text-right text-muted-foreground">${p.fee_amount}</TableCell>
                            <TableCell className="text-right font-semibold">${p.total_amount}</TableCell>
                            <TableCell>
                              <Badge variant={st.variant} className="text-[10px]">{st.label}</Badge>
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
            </Card>
          );
        })
      )}
    </div>
  );
};

export default InstallmentSchedule;
