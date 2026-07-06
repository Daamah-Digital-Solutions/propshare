import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/contexts/AuthContext";
import { returnsApi, propertyApi } from "@/lib/api";
import { Wallet, Clock, TrendingUp, Download, Send, CheckCircle } from "lucide-react";

/** Owner Financials tab — distinct from the Wallet tab. All figures are REAL (server-
 *  authoritative): balance/pending/total from the caller's wallet, payout history from the
 *  live distributions the owner received. No mock numbers. */
const usd = (s: string | number | undefined | null) =>
  Number(s ?? 0).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });

export function OwnerFinancials({ onWithdraw }: { onWithdraw?: () => void }) {
  const { user } = useAuth();
  const wallet = user?.wallet;

  const { data: returns } = useQuery({ queryKey: ["owner-returns"], queryFn: returnsApi.getMine });
  // Property titles for the payout rows (best-effort; falls back to a generic label).
  const { data: props } = useQuery({ queryKey: ["owner-fin-props"], queryFn: () => propertyApi.list() });

  const titleById = useMemo(() => {
    const m = new Map<string, string>();
    (props?.items ?? []).forEach((p) => m.set(p.id, p.title));
    return m;
  }, [props]);

  const items = returns?.items ?? [];

  const exportCsv = () => {
    const rows: string[][] = [["Property", "Type", "Period", "Net Amount"]];
    items.forEach((i) =>
      rows.push([titleById.get(i.property_id) ?? i.property_id, i.kind, i.period_end, i.net_amount]),
    );
    const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "payout-history.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="bg-gradient-to-br from-amber-400 to-amber-500 text-white border-0">
          <CardContent className="p-6">
            <Wallet className="h-5 w-5 mb-3 opacity-90" />
            <p className="text-sm opacity-90">Available Balance</p>
            <p className="text-3xl font-bold mt-1">{usd(wallet?.balance)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6">
            <Clock className="h-5 w-5 mb-3 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Pending Payouts</p>
            <p className="text-3xl font-bold mt-1">{usd(wallet?.pending_balance)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6">
            <TrendingUp className="h-5 w-5 mb-3 text-green-600" />
            <p className="text-sm text-muted-foreground">Total Distributed</p>
            <p className="text-3xl font-bold mt-1">{usd(wallet?.total_returns)}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Payout History</CardTitle>
          <Button variant="outline" size="sm" onClick={exportCsv} disabled={items.length === 0}>
            <Download className="h-4 w-4 mr-2" /> Export
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {items.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No payouts yet. Distributions on your properties will appear here.
            </p>
          ) : (
            items.map((i, idx) => (
              <div
                key={`${i.distribution_id}-${idx}`}
                className="flex items-center justify-between border-b border-border pb-3 last:border-0 last:pb-0"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-green-500/10">
                    <CheckCircle className="h-4 w-4 text-green-600" />
                  </div>
                  <div>
                    <p className="font-medium text-foreground">
                      {titleById.get(i.property_id) ?? "Property"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {i.kind} · {i.period_end}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-green-600">+{usd(i.net_amount)}</p>
                  <Badge variant="secondary" className="text-[10px]">
                    completed
                  </Badge>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-3">
        <Button onClick={onWithdraw}>
          <Send className="h-4 w-4 mr-2" /> Withdraw Funds
        </Button>
        <Button variant="outline" onClick={exportCsv} disabled={items.length === 0}>
          <Download className="h-4 w-4 mr-2" /> Download Statement
        </Button>
      </div>
    </div>
  );
}
