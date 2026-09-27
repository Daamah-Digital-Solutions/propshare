/**
 * The page a member lands on when the hosted checkout sends them back.
 *
 * The provider redirects to `?deposit=success&payment=<id>` (wallet tab) or
 * `?invest=success&payment=<id>` (investments tab). Nothing is credited from that redirect —
 * the server settles the payment from the provider's webhook or its own lookup — so this
 * follows the payment by polling `GET /payments/{id}` (each poll also lets the server ask the
 * provider directly) until it is settled, then refreshes the balance / holdings on screen.
 * The parameters are consumed so a refresh or Back does not restart it.
 */
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { paymentApi } from "@/lib/api";
import { toast } from "sonner";

export type PaymentReturnKind = "deposit" | "invest";

// sessionStorage fallback for a provider that drops the query string on the way back
const PENDING_PAYMENT_KEY = "capimax.pending_payment";
const RETURN_KEYS = ["deposit", "invest", "payment"];

export function rememberPendingPayment(paymentId: string) {
  try {
    sessionStorage.setItem(PENDING_PAYMENT_KEY, paymentId);
  } catch {
    /* private mode / blocked storage: the URL still carries the id */
  }
}

function takeRememberedPayment(): string | null {
  try {
    const id = sessionStorage.getItem(PENDING_PAYMENT_KEY);
    sessionStorage.removeItem(PENDING_PAYMENT_KEY);
    return id;
  } catch {
    return null;
  }
}

// everything on screen that a settled deposit or purchase changes
const AFFECTED_QUERIES = [
  ["wallet"],
  ["wallet-transactions"],
  ["holdings"],
  ["investments"],
  ["portfolio"],
  ["property"],
  ["notifications"],
];

const COPY = {
  deposit: {
    pending: "Payment received — crediting your wallet…",
    pendingHint: "This usually takes a few seconds.",
    done: "Deposit credited",
    doneHint: "Your wallet balance is up to date.",
    failed: "The deposit was not completed",
    failedHint: "Nothing was credited. You can try again or use another method.",
    slow: "Still confirming your deposit",
    slowHint:
      "The payment provider has not confirmed it yet. You will get a notification and an email the moment it is credited — no need to pay again.",
    cancelled: "Deposit cancelled — nothing was charged.",
  },
  invest: {
    pending: "Payment received — confirming your units…",
    pendingHint: "Your units are reserved. This usually takes a few seconds.",
    done: "Investment confirmed",
    doneHint: "The units are yours; they now show in your portfolio.",
    failed: "The purchase was not completed",
    failedHint: "Nothing was charged and the reserved units are released.",
    slow: "Still confirming your purchase",
    slowHint:
      "The payment provider has not confirmed it yet. You will get a notification and an email the moment your units are confirmed — no need to pay again.",
    cancelled: "Purchase cancelled — the units held for you are released within a few minutes.",
  },
} as const;

interface Props {
  kind: PaymentReturnKind;
  /** how often to ask while pending (tests shorten it) */
  pollMs?: number;
  /** after this, stop asking and tell the member we will notify them */
  timeoutMs?: number;
}

export function PaymentReturnStatus({ kind, pollMs = 3000, timeoutMs = 120_000 }: Props) {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  // read the return once, then consume the parameters
  const [ret] = useState<{ outcome: string | null; paymentId: string | null }>(() => {
    const outcome = searchParams.get(kind);
    if (!outcome) return { outcome: null, paymentId: null };
    return { outcome, paymentId: searchParams.get("payment") ?? takeRememberedPayment() };
  });
  const consumed = useRef(false);
  useEffect(() => {
    if (!ret.outcome || consumed.current) return;
    consumed.current = true;
    const rest = new URLSearchParams(searchParams);
    RETURN_KEYS.forEach((k) => rest.delete(k));
    setSearchParams(rest, { replace: true });
    if (ret.outcome === "cancelled") toast.info(COPY[kind].cancelled);
  }, [ret, kind, searchParams, setSearchParams]);

  const [timedOut, setTimedOut] = useState(false);
  const startedAt = useRef(Date.now());
  const following = ret.outcome === "success" && Boolean(ret.paymentId);
  const { data } = useQuery({
    queryKey: ["payment", ret.paymentId],
    queryFn: () => paymentApi.get(ret.paymentId as string),
    enabled: following,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && status !== "pending") return false;
      if (Date.now() - startedAt.current > timeoutMs) {
        setTimedOut(true);
        return false;
      }
      return pollMs;
    },
    retry: false,
  });

  const settled = useRef<string | null>(null);
  useEffect(() => {
    if (!data || data.status === "pending" || settled.current === data.id) return;
    settled.current = data.id;
    if (data.status === "succeeded") {
      toast.success(COPY[kind].done, { description: COPY[kind].doneHint });
      AFFECTED_QUERIES.forEach((queryKey) => queryClient.invalidateQueries({ queryKey }));
    } else {
      toast.error(COPY[kind].failed);
    }
  }, [data, kind, queryClient]);

  if (!following) return null;
  const copy = COPY[kind];
  const status = data?.status ?? "pending";

  if (status === "succeeded") {
    return (
      <Alert data-testid="payment-return" className="border-success/40 bg-success/10">
        <CheckCircle2 className="h-4 w-4 text-success" />
        <AlertTitle>{copy.done}</AlertTitle>
        <AlertDescription>{copy.doneHint}</AlertDescription>
      </Alert>
    );
  }
  if (status !== "pending") {
    return (
      <Alert data-testid="payment-return" variant="destructive">
        <XCircle className="h-4 w-4" />
        <AlertTitle>{copy.failed}</AlertTitle>
        <AlertDescription>{copy.failedHint}</AlertDescription>
      </Alert>
    );
  }
  if (timedOut) {
    return (
      <Alert data-testid="payment-return" className="border-warning/40 bg-warning/10">
        <AlertCircle className="h-4 w-4 text-warning" />
        <AlertTitle>{copy.slow}</AlertTitle>
        <AlertDescription>{copy.slowHint}</AlertDescription>
      </Alert>
    );
  }
  return (
    <Alert data-testid="payment-return" className="border-primary/30 bg-primary/5">
      <Loader2 className="h-4 w-4 animate-spin text-primary" />
      <AlertTitle>{copy.pending}</AlertTitle>
      <AlertDescription>{copy.pendingHint}</AlertDescription>
    </Alert>
  );
}
