import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { Bitcoin, ExternalLink, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { coinLabel, useCryptoCoins } from "@/lib/cryptoCoins";
import { cryptoApi, type CryptoCoin, type OpenCryptoPayment } from "@/lib/api";

/**
 * Crypto payments the member started that have not settled yet (client, 2026-10-06: after
 * sending a transfer and leaving the payment page, nothing on the platform said it was on its
 * way). Each row says the coin chosen, how far it is and where to finish it; the list is read
 * again every half minute, and a payment leaving it refreshes the balance and the movements.
 * Nothing shows when there is none.
 */

const WHAT: Record<string, string> = {
  deposit: "Crypto deposit",
  investment: "Crypto purchase",
  installment: "Crypto down payment",
};

// everything on the wallet page a settled payment changes
const AFFECTED = [["wallet"], ["wallet-transactions"], ["notifications"]];

function Row({ payment, coins }: { payment: OpenCryptoPayment; coins: CryptoCoin[] }) {
  const confirming = payment.stage === "confirming";
  // the coin as the member chose it ("USDT · Tether USD (Tron)"); its code when the list is not in
  const listed = coins.find((c) => c.code === payment.coin?.toLowerCase());
  const coin = listed ? coinLabel(listed) : (payment.coin?.toUpperCase() ?? null);
  return (
    <li className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="font-medium text-foreground">
          {WHAT[payment.purpose] ?? "Crypto payment"}
          {payment.title ? ` · ${payment.title}` : ""}
        </p>
        <p className="text-sm text-muted-foreground">
          ${Number(payment.amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}
          {coin ? ` · in ${coin}` : ""} · started{" "}
          {formatDistanceToNow(new Date(payment.created_at), { addSuffix: true })}
        </p>
        <p className="mt-1 flex items-center gap-1.5 text-sm">
          {confirming ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
              <span className="text-foreground">
                Seen on the network, confirming. Nothing more to do.
              </span>
            </>
          ) : (
            <span className="text-foreground">Waiting for your transfer.</span>
          )}
        </p>
      </div>
      {!confirming && payment.checkout_url && (
        <Button asChild variant="outline" size="sm" className="shrink-0 self-start sm:self-center">
          <a href={payment.checkout_url} target="_blank" rel="noopener noreferrer">
            Open payment page <ExternalLink className="ml-1 h-3.5 w-3.5" />
          </a>
        </Button>
      )}
    </li>
  );
}

export function OpenCryptoPayments() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["crypto-open"],
    queryFn: cryptoApi.open,
    // keep asking only while something is on its way
    refetchInterval: (query) => (query.state.data?.length ? 30_000 : false),
  });
  const rows = data ?? [];
  // only to name the coins, so only when there is a row to name
  const coins = useCryptoCoins(rows.length > 0).data?.items ?? [];

  // a payment that left the list has settled (or was closed): show what it changed
  const known = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!data) return;
    const now = new Set(data.map((p) => p.id));
    const gone = [...known.current].some((id) => !now.has(id));
    known.current = now;
    if (gone) AFFECTED.forEach((queryKey) => queryClient.invalidateQueries({ queryKey }));
  }, [data, queryClient]);

  if (rows.length === 0) return null;
  return (
    <Card className="border-primary/30" data-testid="open-crypto-payments">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Bitcoin className="h-4 w-4 text-primary" /> Crypto payments on their way
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-border">
          {rows.map((p) => (
            <Row key={p.id} payment={p} coins={coins} />
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted-foreground">
          A transfer is credited automatically once the network confirms it; you are notified
          here, and by email unless you turned those emails off. If you sent another coin or
          network than the one chosen, it is credited at the value that arrives. A payment you
          did not send simply drops off this list.
        </p>
      </CardContent>
    </Card>
  );
}

export default OpenCryptoPayments;
