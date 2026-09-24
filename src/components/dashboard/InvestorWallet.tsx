import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Wallet,
  ArrowUpRight,
  ArrowDownLeft,
  Plus,
  CreditCard,
  Building2,
  Landmark,
  Bitcoin,
  Clock,
  CheckCircle2,
  AlertCircle,
  RefreshCcw,
  Sparkles,
  Trash2,
  Star,
} from "lucide-react";
import { ExitButton } from "@/components/exit/ExitButton";
import { AccountStatementCard } from "@/components/dashboard/AccountStatementCard";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  walletApi,
  withdrawApi,
  paymentMethodsApi,
  bankAccountsApi,
  cryptoWalletsApi,
  bankDepositApi,
  payoutConfigApi,
  connectApi,
  ApiError,
  type TransactionItem,
  type WithdrawMethod,
} from "@/lib/api";
import { toast } from "sonner";

// Ledger types that represent money LEAVING the wallet (shown negative).
const NEGATIVE_TYPES = new Set(["withdrawal", "investment", "fee"]);

const tail = (s: string | null | undefined) => (s ? s.slice(-4) : "");

// Query parameters of a deposit / withdrawal the assistant prepared (see WalletPrefill below).
const PREFILL_KEYS = ["action", "amount", "method", "speed"];

/** Shown inside a form the assistant filled in: the last step stays the user's own click. */
function PreparedBanner({ what }: { what: "deposit" | "withdrawal" }) {
  return (
    <div
      data-testid="assistant-prefill-banner"
      className="rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-sm"
    >
      <div className="font-semibold text-primary">Prepared by PropShare AI</div>
      <div className="text-xs text-muted-foreground">
        Check the details below, then press the button yourself. Nothing{" "}
        {what === "deposit" ? "is charged" : "is sent"} before that.
      </div>
    </div>
  );
}

export const InvestorWallet = () => {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [depositOpen, setDepositOpen] = useState(false);
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [prefilled, setPrefilled] = useState<"deposit" | "withdrawal" | null>(null);

  // Deposit state
  const [depositAmount, setDepositAmount] = useState("");
  const [depositMethod, setDepositMethod] = useState<"card" | "crypto" | "bank">("card");
  const [depositing, setDepositing] = useState(false);
  const [bankDepositAccountId, setBankDepositAccountId] = useState("");
  const [bankDepositRef, setBankDepositRef] = useState("");

  // Withdraw state
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [withdrawMethod, setWithdrawMethod] = useState<WithdrawMethod>("bank");
  const [withdrawing, setWithdrawing] = useState(false);
  const [selectedBankId, setSelectedBankId] = useState("");
  const [selectedWalletId, setSelectedWalletId] = useState("");

  const { data: wallet } = useQuery({ queryKey: ["wallet"], queryFn: walletApi.getMe });
  const { data: txnData } = useQuery({
    queryKey: ["wallet-transactions"],
    queryFn: () => walletApi.transactions(),
  });
  const { data: savedMethods } = useQuery({
    queryKey: ["payment-methods"],
    queryFn: paymentMethodsApi.list,
  });
  const { data: bankAccounts } = useQuery({
    queryKey: ["bank-accounts"],
    queryFn: bankAccountsApi.list,
  });
  const { data: cryptoWallets } = useQuery({
    queryKey: ["crypto-wallets"],
    queryFn: cryptoWalletsApi.list,
  });
  const { data: platformAccounts } = useQuery({
    queryKey: ["deposit-bank-accounts"],
    queryFn: bankDepositApi.platformAccounts,
  });
  const { data: depositMethods } = useQuery({
    queryKey: ["deposit-methods"],
    queryFn: walletApi.depositMethods,
  });
  // How withdrawals settle right now. Manual = an admin pays by hand against a saved
  // account; auto = the provider pays out (bank -> Stripe Connect, no saved IBAN used).
  const { data: payoutConfig } = useQuery({
    queryKey: ["payout-config"],
    queryFn: payoutConfigApi.get,
  });
  const bankIsAuto = payoutConfig?.methods?.bank?.connect_required ?? false;
  const { data: connectStatus } = useQuery({
    queryKey: ["connect-status"],
    queryFn: connectApi.status,
    enabled: bankIsAuto, // only meaningful once bank payouts run through Stripe
  });
  const [linkingBank, setLinkingBank] = useState(false);
  const bankLinked = Boolean(connectStatus?.payouts_enabled);
  // Instant payouts: minutes to an eligible debit card, for a fee. Offered only when the
  // server says this account can actually take one.
  const [instant, setInstant] = useState(false);
  const instantInfo = payoutConfig?.instant;
  const instantOffered = withdrawMethod === "bank" && bankIsAuto && Boolean(instantInfo?.available);
  const instantFeePct = Number(instantInfo?.fee_pct ?? 0);
  const instantMax = Number(instantInfo?.max_amount ?? 0);
  const requested = Number(withdrawAmount) || 0;
  const instantFee = instant ? Math.ceil(requested * instantFeePct) / 100 : 0;
  const overInstantMax = instant && requested > instantMax;

  // WalletPrefill: the assistant prepares a deposit or withdrawal as
  // ?tab=wallet&action=deposit|withdraw&amount=N&method=M(&speed=instant). Fill the form, open
  // it, and consume the parameters so a refresh or Back does not reopen it. Pressing Deposit /
  // Withdraw stays the user's own click; the server re-checks everything then.
  useEffect(() => {
    const action = searchParams.get("action");
    if (action !== "deposit" && action !== "withdraw") return;
    const amount = Number(searchParams.get("amount"));
    const method = searchParams.get("method");
    if (Number.isFinite(amount) && amount > 0) {
      (action === "deposit" ? setDepositAmount : setWithdrawAmount)(String(amount));
    }
    if (action === "deposit") {
      if (method === "card" || method === "crypto" || method === "bank") setDepositMethod(method);
      setDepositOpen(true);
      setPrefilled("deposit");
    } else {
      if (method === "bank" || method === "crypto") setWithdrawMethod(method);
      setInstant(searchParams.get("speed") === "instant");
      setWithdrawOpen(true);
      setPrefilled("withdrawal");
    }
    const rest = new URLSearchParams(searchParams);
    PREFILL_KEYS.forEach((k) => rest.delete(k));
    setSearchParams(rest, { replace: true });
  }, [searchParams, setSearchParams]);

  const methods = savedMethods ?? [];
  const banks = bankAccounts ?? [];
  const wallets = cryptoWallets ?? [];
  // the server's pick when none is chosen: the default saved destination, else the first one
  const defaultBankId = (banks.find((b) => b.is_default) ?? banks[0])?.id;
  const defaultWalletId = (wallets.find((w) => w.is_default) ?? wallets[0])?.id;
  const platforms = platformAccounts ?? [];
  // Which deposit rails are live. Until the query resolves, assume card/crypto are
  // available (optimistic) so the control isn't disabled on a slow network; the server
  // still 503s honestly if a rail isn't configured.
  const cardLive = depositMethods?.card ?? true;
  const cryptoLive = depositMethods?.crypto ?? true;
  const selectedRailLive =
    depositMethod === "card" ? cardLive : depositMethod === "crypto" ? cryptoLive : true;

  const available = Number(wallet?.balance ?? 0);
  const pending = Number(wallet?.pending_balance ?? 0);
  const total = available + pending;

  const transactions = (txnData?.items ?? []).map((t: TransactionItem) => ({
    id: t.id,
    type: t.type,
    amount: (NEGATIVE_TYPES.has(t.type) ? -1 : 1) * Number(t.amount),
    method: t.payment_method ?? undefined,
    date: new Date(t.created_at).toLocaleDateString(),
    reference: t.reference_id ? t.reference_id.slice(0, 8) : "",
    status: t.status,
  }));

  const invalidateWallet = () => {
    queryClient.invalidateQueries({ queryKey: ["wallet"] });
    queryClient.invalidateQueries({ queryKey: ["wallet-transactions"] });
  };

  // ---- Saved cards ----
  // Cards are entered on Stripe's hosted checkout at payment time. There is no card-entry form
  // here, so there is no "add card": it could only start a setup nobody can finish.
  const removeMethod = useMutation({
    mutationFn: (id: string) => paymentMethodsApi.remove(id),
    onSuccess: () => {
      toast.success("Card removed");
      queryClient.invalidateQueries({ queryKey: ["payment-methods"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not remove the card"),
  });
  const makeDefaultCard = useMutation({
    mutationFn: (id: string) => paymentMethodsApi.setDefault(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["payment-methods"] }),
  });

  // ---- Bank account + crypto wallet management ----
  const [bankDialogOpen, setBankDialogOpen] = useState(false);
  const [bankForm, setBankForm] = useState({
    account_holder: "",
    bank_name: "",
    iban: "",
    account_number: "",
    swift_bic: "",
    country: "",
  });
  const addBank = useMutation({
    mutationFn: () => bankAccountsApi.add(bankForm),
    onSuccess: () => {
      toast.success("Bank account saved");
      setBankDialogOpen(false);
      setBankForm({ account_holder: "", bank_name: "", iban: "", account_number: "", swift_bic: "", country: "" });
      queryClient.invalidateQueries({ queryKey: ["bank-accounts"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not save the account"),
  });
  const removeBank = useMutation({
    mutationFn: (id: string) => bankAccountsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["bank-accounts"] }),
  });
  const defaultBank = useMutation({
    mutationFn: (id: string) => bankAccountsApi.setDefault(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["bank-accounts"] }),
  });

  const [walletDialogOpen, setWalletDialogOpen] = useState(false);
  const [walletForm, setWalletForm] = useState({ network: "USDT-TRC20", address: "", label: "" });
  const addWallet = useMutation({
    mutationFn: () => cryptoWalletsApi.add(walletForm),
    onSuccess: () => {
      toast.success("Crypto wallet saved");
      setWalletDialogOpen(false);
      setWalletForm({ network: "USDT-TRC20", address: "", label: "" });
      queryClient.invalidateQueries({ queryKey: ["crypto-wallets"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not save the wallet"),
  });
  const removeWallet = useMutation({
    mutationFn: (id: string) => cryptoWalletsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["crypto-wallets"] }),
  });
  const defaultWallet = useMutation({
    mutationFn: (id: string) => cryptoWalletsApi.setDefault(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["crypto-wallets"] }),
  });

  // ---- Deposit ----
  const handleDeposit = async () => {
    const amt = Number(depositAmount);
    if (!amt || amt <= 0) {
      toast.error("Enter a valid amount");
      return;
    }
    setDepositing(true);
    try {
      if (depositMethod === "bank") {
        const accountId = bankDepositAccountId || platforms[0]?.id;
        await bankDepositApi.submitClaim(
          { amount: amt, platform_account_id: accountId, reference: bankDepositRef.trim() || undefined },
          crypto.randomUUID(),
        );
        toast.success("Bank transfer recorded", {
          description: "We'll credit your wallet once our team confirms the transfer arrived.",
        });
        setDepositAmount("");
        setBankDepositRef("");
        invalidateWallet();
      } else {
        const res = await walletApi.deposit({ amount: amt, method: depositMethod }, crypto.randomUUID());
        if (res.checkout_url) {
          window.location.href = res.checkout_url; // hosted checkout; credit on webhook
        } else {
          toast.info("Deposit created", { description: "Awaiting payment confirmation." });
        }
      }
    } catch (error) {
      const code = error instanceof ApiError ? error.code : "";
      if (code === "KYC_REQUIRED") {
        toast.error("Verify your identity first", {
          description: "Complete KYC verification before depositing.",
        });
      } else if (code === "PAYMENTS_NOT_CONFIGURED") {
        toast.info("Card / crypto deposits are coming online soon", {
          description: "You can still deposit by bank transfer.",
        });
      } else {
        toast.error(error instanceof ApiError ? error.message : "Could not start the deposit.");
      }
    } finally {
      setDepositing(false);
    }
  };

  // ---- Stripe bank linking (automatic payouts only) ----
  const handleLinkBank = async () => {
    setLinkingBank(true);
    try {
      const { onboarding_url } = await connectApi.onboard();
      window.location.href = onboarding_url; // Stripe-hosted; it collects the bank details
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Could not start bank linking. Try again.",
      );
      setLinkingBank(false);
    }
  };

  // ---- Withdraw ----
  const handleWithdraw = async () => {
    const amt = Number(withdrawAmount);
    if (!amt || amt <= 0) {
      toast.error("Enter a valid amount");
      return;
    }
    if (amt > available) {
      toast.error("Amount exceeds your available balance");
      return;
    }
    // Automatic bank payouts go to the user's Stripe-linked account: there is no saved
    // destination to pick, only the completed onboarding.
    const autoBank = withdrawMethod === "bank" && bankIsAuto;
    if (autoBank && !bankLinked) {
      toast.error("Link your bank account first to withdraw automatically.");
      return;
    }
    const payoutId = autoBank
      ? undefined
      : withdrawMethod === "bank"
        ? selectedBankId || defaultBankId
        : selectedWalletId || defaultWalletId;
    if (!autoBank && !payoutId) {
      toast.error(
        withdrawMethod === "bank" ? "Add a bank account first" : "Add a crypto wallet first",
      );
      return;
    }
    setWithdrawing(true);
    try {
      const useInstant = instantOffered && instant;
      const created = await withdrawApi.create(
        {
          amount: amt,
          method: withdrawMethod,
          ...(payoutId ? { payout_method_id: payoutId } : {}),
          ...(useInstant ? { speed: "instant" as const } : {}),
        },
        crypto.randomUUID(),
      );
      // "approved" = sent to the provider straight away; anything else waits for a human.
      const sentInstantly = created.status === "approved" && created.speed === "instant";
      toast.success(
        created.status === "approved" ? "Withdrawal sent" : "Withdrawal requested",
        {
          description: sentInstantly
            ? `$${created.net_amount} is on its way to your card and usually arrives within 30 minutes.`
            : created.status === "approved"
              ? "It is on its way to your linked bank. Banks usually post it within 1-2 business days."
              : "Your request has been sent to our team and will be processed shortly.",
        },
      );
      setWithdrawAmount("");
      invalidateWallet();
    } catch (error) {
      const code = error instanceof ApiError ? error.code : "";
      const map: Record<string, string> = {
        KYC_REQUIRED: "Complete identity verification before withdrawing.",
        NO_PAYOUT_METHOD: "Add a payout destination first.",
        CONNECT_NOT_READY: "Finish linking your bank with Stripe before withdrawing.",
        INSTANT_NOT_AVAILABLE: "Instant payout is not available on this account right now.",
        INSTANT_LIMIT_EXCEEDED: "That is above the instant payout limit. Use the standard speed.",
        PAYOUTS_NOT_CONFIGURED: "Automatic payouts are not available right now.",
        INSUFFICIENT_FUNDS: "Amount exceeds your available balance.",
      };
      toast.error(map[code] ?? (error instanceof ApiError ? error.message : "Withdrawal failed."));
    } finally {
      setWithdrawing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Wallet Balance Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="bg-gradient-to-br from-primary to-primary/80 text-primary-foreground">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm opacity-90">Available Balance</p>
                <p className="text-3xl font-bold mt-1">${available.toLocaleString()}</p>
              </div>
              <Wallet className="h-10 w-10 opacity-80" />
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Pending</p>
                <p className="text-3xl font-bold text-foreground mt-1">${pending.toLocaleString()}</p>
              </div>
              <Clock className="h-10 w-10 text-accent" />
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total Value</p>
                <p className="text-3xl font-bold text-foreground mt-1">${total.toLocaleString()}</p>
              </div>
              <ArrowUpRight className="h-10 w-10 text-primary" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <div className="flex flex-wrap gap-4">
        {/* Deposit */}
        <Dialog
          open={depositOpen}
          onOpenChange={(o) => {
            setDepositOpen(o);
            if (!o) setPrefilled(null);
          }}
        >
          <DialogTrigger asChild>
            <Button className="gap-2">
              <Plus className="h-4 w-4" />
              Add Funds
            </Button>
          </DialogTrigger>
          <DialogContent className="max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Add Funds to Wallet</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              {prefilled === "deposit" && <PreparedBanner what="deposit" />}
              <div className="space-y-2">
                <Label>Amount (USD)</Label>
                <Input
                  type="number"
                  placeholder="Enter amount"
                  value={depositAmount}
                  onChange={(e) => setDepositAmount(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label>Payment Method</Label>
                <Select
                  value={depositMethod}
                  onValueChange={(v) => setDepositMethod(v as "card" | "crypto" | "bank")}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select payment method" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="card" disabled={!cardLive}>
                      Card (Visa / Mastercard / Apple Pay / Google Pay)
                      {!cardLive && " — Coming soon"}
                    </SelectItem>
                    <SelectItem value="crypto" disabled={!cryptoLive}>
                      Cryptocurrency{!cryptoLive && " — Coming soon"}
                    </SelectItem>
                    <SelectItem value="bank">Bank Transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {(depositMethod === "card" || depositMethod === "crypto") && !selectedRailLive && (
                <p className="text-sm text-muted-foreground rounded-lg border border-border p-3 bg-muted/30">
                  {depositMethod === "card" ? "Card" : "Crypto"} deposits are coming online soon.
                  You can deposit by bank transfer in the meantime.
                </p>
              )}

              {depositMethod === "bank" && (
                <div className="space-y-3 rounded-lg border border-border p-3 bg-muted/30">
                  {platforms.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      Bank transfer isn't available right now — no receiving account is set up yet.
                      Please use card or crypto, or check back soon.
                    </p>
                  ) : (
                    <>
                      <p className="text-sm font-medium text-foreground">
                        1. Transfer the amount to one of our accounts:
                      </p>
                      {platforms.map((p) => (
                        <label
                          key={p.id}
                          className="block rounded-md border border-border p-3 bg-background cursor-pointer text-xs space-y-0.5"
                        >
                          <div className="flex items-center gap-2">
                            <input
                              type="radio"
                              name="platform-account"
                              checked={(bankDepositAccountId || platforms[0]?.id) === p.id}
                              onChange={() => setBankDepositAccountId(p.id)}
                            />
                            <span className="font-semibold text-sm text-foreground">
                              {p.bank_name} · {p.currency}
                            </span>
                          </div>
                          <div className="pl-6 text-muted-foreground">
                            <div>Account holder: <span className="text-foreground">{p.account_holder}</span></div>
                            {p.iban && <div>IBAN: <span className="text-foreground">{p.iban}</span></div>}
                            {p.account_number && <div>Account #: <span className="text-foreground">{p.account_number}</span></div>}
                            {p.swift_bic && <div>SWIFT/BIC: <span className="text-foreground">{p.swift_bic}</span></div>}
                            {p.instructions && <div className="italic mt-1">{p.instructions}</div>}
                          </div>
                        </label>
                      ))}
                      <p className="text-sm font-medium text-foreground pt-1">
                        2. Enter your transfer reference (optional):
                      </p>
                      <Input
                        placeholder="e.g. your name / transfer ID"
                        value={bankDepositRef}
                        onChange={(e) => setBankDepositRef(e.target.value)}
                      />
                      <p className="text-xs text-muted-foreground">
                        Your wallet is credited once our team confirms the transfer arrived.
                      </p>
                    </>
                  )}
                </div>
              )}

              <Button
                className="w-full"
                onClick={handleDeposit}
                disabled={
                  depositing ||
                  (depositMethod === "bank" && platforms.length === 0) ||
                  !selectedRailLive
                }
              >
                {depositing
                  ? "Submitting…"
                  : depositMethod === "bank"
                    ? `Record transfer of $${depositAmount || "0"}`
                    : `Deposit $${depositAmount || "0"}`}
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {/* Withdraw */}
        <Dialog
          open={withdrawOpen}
          onOpenChange={(o) => {
            setWithdrawOpen(o);
            if (!o) setPrefilled(null);
          }}
        >
          <DialogTrigger asChild>
            <Button variant="outline" className="gap-2">
              <ArrowDownLeft className="h-4 w-4" />
              Withdraw
            </Button>
          </DialogTrigger>
          <DialogContent className="max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Withdraw Funds</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              {prefilled === "withdrawal" && <PreparedBanner what="withdrawal" />}
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-sm text-muted-foreground">Available Balance</p>
                <p className="text-xl font-bold">${available.toLocaleString()}</p>
              </div>
              <div className="space-y-2">
                <Label>Amount (USD)</Label>
                <Input
                  type="number"
                  placeholder="Enter amount"
                  value={withdrawAmount}
                  onChange={(e) => setWithdrawAmount(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label>Withdraw To</Label>
                <Select
                  value={withdrawMethod}
                  onValueChange={(v) => setWithdrawMethod(v as WithdrawMethod)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select destination type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="bank">Bank Account</SelectItem>
                    <SelectItem value="crypto">Crypto Wallet</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {withdrawMethod === "bank" && bankIsAuto && (
                <div className="space-y-2 rounded-lg bg-muted/50 p-3" data-testid="connect-bank">
                  {bankLinked ? (
                    <p className="text-sm">
                      Paid automatically to your linked bank account
                      {connectStatus?.stripe_account_id ? " (secured by Stripe)" : ""}. No waiting
                      for our team.
                    </p>
                  ) : (
                    <>
                      <p className="text-sm text-muted-foreground">
                        Bank withdrawals are paid out automatically. Link your bank account once —
                        your details are held by Stripe, not by us.
                      </p>
                      <Button
                        variant="outline"
                        className="w-full"
                        onClick={handleLinkBank}
                        disabled={linkingBank}
                      >
                        {linkingBank ? "Opening Stripe…" : "Link bank account"}
                      </Button>
                    </>
                  )}
                </div>
              )}

              {withdrawMethod === "bank" && !bankIsAuto &&
                (banks.length === 0 ? (
                  <p className="text-sm text-muted-foreground rounded-lg bg-muted/50 p-3">
                    You have no saved bank account. Add one in <b>Payment Methods</b> below first.
                  </p>
                ) : (
                  <div className="space-y-2">
                    <Label>Destination account</Label>
                    <Select
                      value={selectedBankId || defaultBankId || ""}
                      onValueChange={setSelectedBankId}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {banks.map((b) => (
                          <SelectItem key={b.id} value={b.id}>
                            {b.bank_name} ···· {tail(b.iban ?? b.account_number)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ))}

              {withdrawMethod === "crypto" &&
                (wallets.length === 0 ? (
                  <p className="text-sm text-muted-foreground rounded-lg bg-muted/50 p-3">
                    You have no saved crypto wallet. Add one in <b>Payment Methods</b> below first.
                  </p>
                ) : (
                  <div className="space-y-2">
                    <Label>Destination wallet</Label>
                    <Select
                      value={selectedWalletId || defaultWalletId || ""}
                      onValueChange={setSelectedWalletId}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {wallets.map((w) => (
                          <SelectItem key={w.id} value={w.id}>
                            {w.network} ···· {tail(w.address)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ))}

              {instantOffered && (
                <div className="rounded-lg border p-3 space-y-2" data-testid="instant-option">
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={instant}
                      onChange={(e) => setInstant(e.target.checked)}
                      aria-label="Get it in minutes"
                    />
                    <span className="text-sm">
                      <b>Get it in minutes</b> — paid straight to your debit card, any day or
                      time, for a {instantFeePct}% fee. Without it, your bank posts the money in
                      1–2 business days for free.
                    </span>
                  </label>
                  {instant && requested > 0 && !overInstantMax && (
                    <p className="text-sm text-muted-foreground" data-testid="instant-breakdown">
                      Fee ${instantFee.toFixed(2)} · you receive $
                      {(requested - instantFee).toFixed(2)}
                    </p>
                  )}
                  {overInstantMax && (
                    <p className="text-sm text-destructive">
                      Instant payouts are capped at ${instantMax.toLocaleString()} per request.
                      Lower the amount or use the standard speed.
                    </p>
                  )}
                </div>
              )}

              <Button
                className="w-full"
                onClick={handleWithdraw}
                disabled={withdrawing || overInstantMax}
              >
                {withdrawing ? "Submitting…" : `Withdraw $${withdrawAmount || "0"}`}
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                {withdrawMethod === "bank" && bankIsAuto
                  ? `Sent automatically up to $${Number(payoutConfig?.auto_approve_limit ?? 0).toLocaleString()} per request; larger amounts are reviewed by our team first.`
                  : "Withdrawals are reviewed and paid out by our team, usually within 1–2 business days."}
              </p>
            </div>
          </DialogContent>
        </Dialog>

        <ExitButton variant="outline" label="Exit Position" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Transaction History */}
        <Card className="lg:col-span-2 bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">Transaction History</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {transactions.length === 0 && (
                <p className="text-sm text-muted-foreground py-6 text-center">
                  No transactions yet. Add funds to get started.
                </p>
              )}
              {transactions.map((transaction) => (
                <div
                  key={transaction.id}
                  className="flex items-center justify-between p-4 rounded-lg bg-muted/30 border border-border/50"
                >
                  <div className="flex items-center gap-4">
                    <div
                      className={`h-10 w-10 rounded-full flex items-center justify-center ${
                        transaction.type === "deposit" || transaction.type === "dividend"
                          ? "bg-primary/10"
                          : "bg-muted"
                      }`}
                    >
                      {transaction.type === "deposit" ? (
                        <ArrowDownLeft className="h-5 w-5 text-primary" />
                      ) : transaction.type === "dividend" ? (
                        <ArrowUpRight className="h-5 w-5 text-primary" />
                      ) : transaction.type === "withdrawal" ? (
                        <ArrowUpRight className="h-5 w-5 text-muted-foreground" />
                      ) : (
                        <Building2 className="h-5 w-5 text-accent" />
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-medium capitalize">
                        {transaction.type}
                        {transaction.method && ` via ${transaction.method}`}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {transaction.date} • {transaction.reference}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={`text-sm font-semibold ${
                        transaction.amount > 0 ? "text-primary" : "text-foreground"
                      }`}
                    >
                      {transaction.amount > 0 ? "+" : ""}${Math.abs(transaction.amount).toLocaleString()}
                    </span>
                    {transaction.status === "completed" ? (
                      <CheckCircle2 className="h-4 w-4 text-primary" />
                    ) : (
                      <Clock className="h-4 w-4 text-accent" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Payment Methods & Payout Destinations */}
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">Payment Methods</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Saved cards */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <CreditCard className="h-4 w-4" /> Cards
                </p>
              </div>
              {methods.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  You enter your card on Stripe's secure payment page each time you pay. We never
                  see or store your card number.
                </p>
              ) : (
                <div className="space-y-2">
                  {methods.map((m) => (
                    <div
                      key={m.id}
                      className="flex items-center justify-between rounded-lg border border-border p-2.5"
                    >
                      <div>
                        <div className="text-sm font-medium text-foreground capitalize">
                          {m.brand ?? m.type} •••• {m.last4 ?? "????"}
                          {m.is_default && (
                            <Badge variant="secondary" className="ml-2 text-xs">Default</Badge>
                          )}
                        </div>
                        {m.exp_month && m.exp_year && (
                          <p className="text-xs text-muted-foreground">
                            Expires {String(m.exp_month).padStart(2, "0")}/{m.exp_year}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-1">
                        {!m.is_default && (
                          <Button variant="ghost" size="icon" aria-label="Set default card"
                            onClick={() => makeDefaultCard.mutate(m.id)}>
                            <Star className="h-4 w-4" />
                          </Button>
                        )}
                        <Button variant="ghost" size="icon" aria-label="Remove card"
                          onClick={() => removeMethod.mutate(m.id)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Bank accounts (payout destinations) */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <Landmark className="h-4 w-4" /> Bank Accounts
                </p>
                <Dialog open={bankDialogOpen} onOpenChange={setBankDialogOpen}>
                  <DialogTrigger asChild>
                    <Button variant="outline" size="sm" aria-label="Add bank account">
                      <Plus className="h-4 w-4" />
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                      <DialogTitle>Add Bank Account</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-3 py-2">
                      <div className="space-y-1.5">
                        <Label>Account holder name</Label>
                        <Input value={bankForm.account_holder}
                          onChange={(e) => setBankForm({ ...bankForm, account_holder: e.target.value })} />
                      </div>
                      <div className="space-y-1.5">
                        <Label>Bank name</Label>
                        <Input value={bankForm.bank_name}
                          onChange={(e) => setBankForm({ ...bankForm, bank_name: e.target.value })} />
                      </div>
                      <div className="space-y-1.5">
                        <Label>IBAN</Label>
                        <Input value={bankForm.iban}
                          onChange={(e) => setBankForm({ ...bankForm, iban: e.target.value })} />
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                          <Label>Account number</Label>
                          <Input value={bankForm.account_number}
                            onChange={(e) => setBankForm({ ...bankForm, account_number: e.target.value })} />
                        </div>
                        <div className="space-y-1.5">
                          <Label>SWIFT / BIC</Label>
                          <Input value={bankForm.swift_bic}
                            onChange={(e) => setBankForm({ ...bankForm, swift_bic: e.target.value })} />
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <Label>Country</Label>
                        <Input value={bankForm.country}
                          onChange={(e) => setBankForm({ ...bankForm, country: e.target.value })} />
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Provide an IBAN or an account number. This is where your bank withdrawals
                        will be sent.
                      </p>
                      <Button className="w-full" disabled={addBank.isPending} onClick={() => addBank.mutate()}>
                        {addBank.isPending ? "Saving…" : "Save bank account"}
                      </Button>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>
              {banks.length === 0 ? (
                <p className="text-xs text-muted-foreground">No saved bank account.</p>
              ) : (
                <div className="space-y-2">
                  {banks.map((b) => (
                    <div key={b.id}
                      className="flex items-center justify-between rounded-lg border border-border p-2.5">
                      <div>
                        <div className="text-sm font-medium text-foreground">
                          {b.bank_name} ···· {tail(b.iban ?? b.account_number)}
                          {b.is_default && (
                            <Badge variant="secondary" className="ml-2 text-xs">Default</Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">{b.account_holder}</p>
                      </div>
                      <div className="flex items-center gap-1">
                        {!b.is_default && (
                          <Button variant="ghost" size="icon" aria-label="Set default bank"
                            onClick={() => defaultBank.mutate(b.id)}>
                            <Star className="h-4 w-4" />
                          </Button>
                        )}
                        <Button variant="ghost" size="icon" aria-label="Remove bank"
                          onClick={() => removeBank.mutate(b.id)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Crypto wallets (payout destinations) */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <Bitcoin className="h-4 w-4" /> Crypto Wallets
                </p>
                <Dialog open={walletDialogOpen} onOpenChange={setWalletDialogOpen}>
                  <DialogTrigger asChild>
                    <Button variant="outline" size="sm" aria-label="Add crypto wallet">
                      <Plus className="h-4 w-4" />
                    </Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Add Crypto Wallet</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-3 py-2">
                      <div className="space-y-1.5">
                        <Label>Network</Label>
                        <Select value={walletForm.network}
                          onValueChange={(v) => setWalletForm({ ...walletForm, network: v })}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="USDT-TRC20">USDT · TRC20 (Tron)</SelectItem>
                            <SelectItem value="USDT-ERC20">USDT · ERC20 (Ethereum)</SelectItem>
                            <SelectItem value="USDC-ERC20">USDC · ERC20 (Ethereum)</SelectItem>
                            <SelectItem value="BTC">Bitcoin (BTC)</SelectItem>
                            <SelectItem value="ETH">Ethereum (ETH)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label>Wallet address</Label>
                        <Input value={walletForm.address}
                          onChange={(e) => setWalletForm({ ...walletForm, address: e.target.value })} />
                      </div>
                      <div className="space-y-1.5">
                        <Label>Label (optional)</Label>
                        <Input value={walletForm.label} placeholder="e.g. My Binance USDT"
                          onChange={(e) => setWalletForm({ ...walletForm, label: e.target.value })} />
                      </div>
                      <Button className="w-full" disabled={addWallet.isPending} onClick={() => addWallet.mutate()}>
                        {addWallet.isPending ? "Saving…" : "Save crypto wallet"}
                      </Button>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>
              {wallets.length === 0 ? (
                <p className="text-xs text-muted-foreground">No saved crypto wallet.</p>
              ) : (
                <div className="space-y-2">
                  {wallets.map((w) => (
                    <div key={w.id}
                      className="flex items-center justify-between rounded-lg border border-border p-2.5">
                      <div>
                        <div className="text-sm font-medium text-foreground">
                          {w.network} ···· {tail(w.address)}
                          {w.is_default && (
                            <Badge variant="secondary" className="ml-2 text-xs">Default</Badge>
                          )}
                        </div>
                        {w.label && <p className="text-xs text-muted-foreground">{w.label}</p>}
                      </div>
                      <div className="flex items-center gap-1">
                        {!w.is_default && (
                          <Button variant="ghost" size="icon" aria-label="Set default wallet"
                            onClick={() => defaultWallet.mutate(w.id)}>
                            <Star className="h-4 w-4" />
                          </Button>
                        )}
                        <Button variant="ghost" size="icon" aria-label="Remove wallet"
                          onClick={() => removeWallet.mutate(w.id)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Pronova benefit */}
            <div className="p-4 rounded-lg bg-accent/10 border border-accent/20">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-accent flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-foreground">Pay with Pronova</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Choose <span className="font-medium text-foreground">Pronova</span> at investment
                    checkout for an automatic discount — settled securely by card.
                  </p>
                </div>
              </div>
            </div>

            {/* Reinvest benefit */}
            <div className="p-4 rounded-lg bg-primary/10 border border-primary/20">
              <div className="flex items-start gap-3">
                <RefreshCcw className="h-5 w-5 text-primary flex-shrink-0" />
                <div>
                  <div className="text-sm font-medium text-foreground flex items-center gap-2">
                    Reinvest Returns
                    <Badge className="bg-primary/20 text-primary border-0 text-xs">
                      <Sparkles className="h-3 w-3 mr-1" /> 5% OFF
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Reinvest your distributed returns and receive a 5% instant discount on your next
                    investment!
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <AccountStatementCard />
    </div>
  );
};
