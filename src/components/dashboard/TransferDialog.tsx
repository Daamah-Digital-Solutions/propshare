import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Clock, Loader2, Mail, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  transfersApi,
  type TransferInput,
  type TransferOccasion,
  type TransferQuote,
  type TransferRow,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Send property units or wallet balance to another person by email (client, 2026-10-28, as on
 * Capimax BRX), in three steps: fill it in, review and confirm (the server prices it: the
 * fee and what leaves the wallet now), and the outcome (delivered, waiting for the recipient,
 * or scheduled), with its TR- number. Nothing is sent before Confirm.
 */

const money = (v: string | number) =>
  Number(v).toLocaleString("en-US", { style: "currency", currency: "USD" });
const today = () => new Date().toISOString().slice(0, 10);
const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });
const newKey = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const OCCASIONS: { id: TransferOccasion; label: string }[] = [
  { id: "birthday", label: "Birthday" },
  { id: "graduation", label: "Graduation" },
  { id: "wedding", label: "Wedding" },
  { id: "new_baby", label: "New baby" },
  { id: "holiday", label: "Holiday" },
  { id: "other", label: "Other" },
];
const NO_OCCASION = "none";

type Step = "form" | "review" | "done";

export function TransferDialog({
  open,
  onOpenChange,
  initialAsset = "units",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialAsset?: "units" | "balance";
}) {
  const qc = useQueryClient();
  const [step, setStep] = useState<Step>("form");
  const [asset, setAsset] = useState<"units" | "balance">(initialAsset);
  const [propertyId, setPropertyId] = useState("");
  const [units, setUnits] = useState("");
  const [amount, setAmount] = useState("");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [date, setDate] = useState(today());
  const [message, setMessage] = useState("");
  const [occasion, setOccasion] = useState<string>(NO_OCCASION);
  const [quote, setQuote] = useState<TransferQuote | null>(null);
  const [result, setResult] = useState<TransferRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [key, setKey] = useState(newKey);

  const opts = useQuery({
    queryKey: ["transfer-options"],
    queryFn: () => transfersApi.options(),
    enabled: open,
  });
  const positions = useMemo(
    () => (opts.data?.positions ?? []).filter((p) => p.free_units > 0),
    [opts.data],
  );

  // a fresh form each time it opens
  useEffect(() => {
    if (!open) return;
    setStep("form");
    setAsset(initialAsset);
    setUnits("");
    setAmount("");
    setEmail("");
    setName("");
    setDate(today());
    setMessage("");
    setOccasion(NO_OCCASION);
    setQuote(null);
    setResult(null);
    setError(null);
  }, [open, initialAsset]);
  useEffect(() => {
    if (!propertyId && positions.length) setPropertyId(positions[0].property_id);
  }, [positions, propertyId]);

  const pos = positions.find((p) => p.property_id === propertyId);
  const n = Math.floor(Number(units) || 0);
  const amt = Number(amount) || 0;
  const maxDate = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() + (opts.data?.max_days_ahead ?? 365));
    return d.toISOString().slice(0, 10);
  }, [opts.data]);
  const valid =
    /^\S+@\S+\.\S+$/.test(email.trim()) &&
    date >= today() &&
    (asset === "units" ? !!pos && n >= 1 && n <= pos.free_units : amt > 0);

  const payload = (): TransferInput => ({
    asset,
    recipient_email: email.trim(),
    recipient_name: name.trim() || undefined,
    ...(asset === "units" ? { property_id: propertyId, units: n } : { amount: amt.toFixed(2) }),
    deliver_on: date,
    message: message.trim() || undefined,
    occasion: occasion === NO_OCCASION ? undefined : (occasion as TransferOccasion),
  });

  const review = async () => {
    setBusy(true);
    setError(null);
    try {
      setQuote(await transfersApi.quote(payload()));
      setKey(newKey()); // one key per confirmation
      setStep("review");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not check the transfer. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await transfersApi.send({ ...payload(), expected_charged: quote?.charged }, key));
      setStep("done");
      // the wallet, holdings, portfolio and certificates all change: read everything again
      qc.invalidateQueries();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not send the transfer. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const claimDays = opts.data?.claim_days ?? 30;
  const feePct = Number(opts.data?.fee_pct ?? 0);

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg" data-testid="transfer-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Send className="h-5 w-5 text-primary" />
            {step === "review" ? "Review your transfer" : step === "done" ? "Transfer sent" : "New transfer"}
          </DialogTitle>
          {step === "form" && (
            <DialogDescription>
              What you send is held at once. It reaches the recipient right away (or on the date you
              choose) if their email is confirmed and identity verified; otherwise we invite them,
              and if they do not verify within {claimDays} days it comes back to you.
            </DialogDescription>
          )}
        </DialogHeader>

        {step === "form" && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="What to send">
              {(["units", "balance"] as const).map((a) => (
                <button
                  key={a}
                  type="button"
                  role="radio"
                  aria-checked={asset === a}
                  disabled={a === "units" && !positions.length}
                  onClick={() => setAsset(a)}
                  className={cn(
                    "rounded-lg border p-2.5 text-sm transition-colors disabled:opacity-50",
                    asset === a ? "border-primary bg-primary/5 font-medium" : "border-border hover:border-primary/40",
                  )}
                >
                  {a === "units" ? "Transfer units" : "Transfer balance"}
                </button>
              ))}
            </div>
            {asset === "units" && !opts.isLoading && !positions.length && (
              <p className="text-sm text-muted-foreground">
                You have no free units to send right now (units listed for sale, reserved or on a
                running plan cannot be sent).
              </p>
            )}

            {asset === "units" ? (
              positions.length > 0 && (
                <div className="grid grid-cols-3 gap-3">
                  <div className="col-span-2 space-y-1.5">
                    <Label htmlFor="transfer-property">Property</Label>
                    <Select value={propertyId} onValueChange={setPropertyId}>
                      <SelectTrigger id="transfer-property" aria-label="Property">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {positions.map((p) => (
                          <SelectItem key={p.property_id} value={p.property_id}>
                            {p.property_title} ({p.free_units} free)
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="transfer-units">Units</Label>
                    <Input
                      id="transfer-units"
                      type="number"
                      min={1}
                      max={pos?.free_units}
                      step={1}
                      value={units}
                      onChange={(e) => setUnits(e.target.value)}
                    />
                  </div>
                  {pos && (
                    <p className="col-span-3 text-xs text-muted-foreground">
                      {pos.free_units} of your {pos.units} units can be sent · {money(pos.unit_price)} a unit
                      {n > 0 && ` · worth ${money(n * Number(pos.unit_price))}`}
                    </p>
                  )}
                </div>
              )
            ) : (
              <div className="space-y-1.5">
                <Label htmlFor="transfer-amount">Amount (USD)</Label>
                <Input
                  id="transfer-amount"
                  type="number"
                  min={0}
                  step="0.01"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Wallet balance: {money(opts.data?.balance ?? 0)}
                  {feePct > 0 && ` · transfer fee ${feePct}%`}
                </p>
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="transfer-email">Recipient email</Label>
                <Input
                  id="transfer-email"
                  type="email"
                  dir="ltr"
                  autoComplete="off"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="transfer-name">Recipient name (optional)</Label>
                <Input id="transfer-name" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="transfer-date">Delivery date</Label>
                <Input
                  id="transfer-date"
                  type="date"
                  min={today()}
                  max={maxDate}
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="transfer-occasion">Occasion (optional)</Label>
                <Select value={occasion} onValueChange={setOccasion}>
                  <SelectTrigger id="transfer-occasion" aria-label="Occasion (optional)">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_OCCASION}>No occasion</SelectItem>
                    {OCCASIONS.map((o) => (
                      <SelectItem key={o.id} value={o.id}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="transfer-message">Message (optional)</Label>
              <Textarea
                id="transfer-message"
                rows={2}
                maxLength={500}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </div>
          </div>
        )}

        {step === "review" && quote && (
          <div className="space-y-4" data-testid="transfer-review">
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 rounded-lg border border-border p-4 text-sm">
              <dt className="text-muted-foreground">To</dt>
              <dd className="break-all font-medium">
                {quote.recipient_name ? `${quote.recipient_name} · ` : ""}
                {quote.recipient_email}
              </dd>
              <dt className="text-muted-foreground">Sending</dt>
              <dd className="font-medium">
                {quote.asset === "units"
                  ? `${quote.units} unit${quote.units === 1 ? "" : "s"} of ${quote.property_title}`
                  : money(quote.amount)}
              </dd>
              {quote.asset === "units" && (
                <>
                  <dt className="text-muted-foreground">Value</dt>
                  <dd>
                    {money(quote.amount)} ({money(quote.unit_price ?? 0)} a unit)
                  </dd>
                </>
              )}
              <dt className="text-muted-foreground">Fee</dt>
              <dd>{Number(quote.fee) > 0 ? `${money(quote.fee)} (${Number(quote.fee_pct)}%)` : "None"}</dd>
              <dt className="text-muted-foreground">From your wallet now</dt>
              <dd className="font-semibold">{money(quote.charged)}</dd>
              <dt className="text-muted-foreground">Delivery</dt>
              <dd>{quote.deliver_on === today() ? "Today" : day(quote.deliver_on)}</dd>
              {quote.occasion && (
                <>
                  <dt className="text-muted-foreground">Occasion</dt>
                  <dd>{OCCASIONS.find((o) => o.id === quote.occasion)?.label}</dd>
                </>
              )}
              {quote.message && (
                <>
                  <dt className="text-muted-foreground">Message</dt>
                  <dd className="break-words">“{quote.message}”</dd>
                </>
              )}
            </dl>
            <ul className="space-y-1.5 text-xs text-muted-foreground">
              <li>
                {quote.asset === "units"
                  ? "The units are held from now: they cannot be sold or sent again."
                  : "The amount leaves your wallet now and is held for the recipient."}
              </li>
              <li>
                If the recipient has not confirmed their email and verified their identity, we invite
                them; if they do not within {quote.claim_days} days, everything comes back to you,
                fee included.
              </li>
              <li>You can cancel it on the Transfers tab until it is delivered.</li>
            </ul>
          </div>
        )}

        {step === "done" && result && (
          <div className="space-y-3 text-center" data-testid="transfer-result">
            {result.status === "delivered" ? (
              <CheckCircle2 className="mx-auto h-12 w-12 text-primary" />
            ) : result.status === "waiting" ? (
              <Mail className="mx-auto h-12 w-12 text-amber-500" />
            ) : (
              <Clock className="mx-auto h-12 w-12 text-primary" />
            )}
            <p className="font-semibold text-foreground">
              {result.status === "delivered"
                ? `Delivered to ${result.counterparty}`
                : result.status === "waiting"
                  ? `Waiting for ${result.counterparty}`
                  : result.status === "scheduled"
                    ? `Scheduled for ${day(result.deliver_on)}`
                    : result.status_label}
            </p>
            <p className="text-sm text-muted-foreground">
              {result.status === "waiting"
                ? "We emailed them an invitation. It reaches them as soon as they confirm their email and verify their identity."
                : result.status === "scheduled"
                  ? "It is held for them and goes out on that date. You can cancel it before then."
                  : result.status === "delivered"
                    ? "Both of you were notified."
                    : result.closed_reason}
            </p>
            <p className="font-mono text-sm" data-testid="transfer-reference">
              {result.reference}
            </p>
          </div>
        )}

        {error && (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          {step === "form" && (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
                Cancel
              </Button>
              <Button onClick={review} disabled={busy || !valid} className="gap-2">
                {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                Review transfer
              </Button>
            </>
          )}
          {step === "review" && (
            <>
              <Button variant="outline" onClick={() => setStep("form")} disabled={busy} className="gap-2">
                <ArrowLeft className="h-4 w-4" /> Change it
              </Button>
              <Button onClick={confirm} disabled={busy} className="gap-2">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Confirm and send
              </Button>
            </>
          )}
          {step === "done" && <Button onClick={() => onOpenChange(false)}>Done</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
