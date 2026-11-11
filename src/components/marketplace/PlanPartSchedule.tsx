import type { PlanPartPayment } from "@/lib/api";
import { money, shortDate } from "@/lib/money";

const installmentLabel = (kind: string, seq: number) =>
  kind === "final" ? `Final (month ${seq})` : kind === "downpayment" ? "Down payment" : `Month ${seq}`;

/**
 * The installments that come with an installment position, or with part of one, at the amounts
 * the new holder pays (the server's figures: for part of a plan, its share of every payment).
 */
export default function PlanPartSchedule({
  schedule,
  testId = "plan-part-schedule",
}: {
  schedule: PlanPartPayment[];
  testId?: string;
}) {
  const total = schedule.reduce((sum, row) => sum + Number(row.total_amount), 0);
  return (
    <div className="rounded-lg border border-border overflow-hidden" data-testid={testId}>
      <table className="w-full text-xs">
        <thead className="bg-muted/50 text-muted-foreground">
          <tr>
            <th className="text-start font-medium p-2">Payment</th>
            <th className="text-start font-medium p-2">Due</th>
            <th className="text-end font-medium p-2">Amount (incl. fee)</th>
          </tr>
        </thead>
        <tbody>
          {schedule.map((row) => (
            <tr key={row.seq} className="border-t border-border/60">
              <td className="p-2">{installmentLabel(row.kind, row.seq)}</td>
              <td className="p-2">{shortDate(row.due_date)}</td>
              <td className="p-2 text-end font-medium">{money(row.total_amount)}</td>
            </tr>
          ))}
          <tr className="border-t border-border bg-muted/30 font-semibold">
            <td className="p-2" colSpan={2}>
              Total still to pay
            </td>
            <td className="p-2 text-end">{money(total)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
