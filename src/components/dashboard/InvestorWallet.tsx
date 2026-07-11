import { useState } from "react";
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
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  walletApi,
  withdrawApi,
  paymentMethodsApi,
  bankAccountsApi,
  cryptoWalletsApi,
  bankDepositApi,
  ApiError,
  type TransactionItem,
  type WithdrawMethod,
} from "@/lib/api";
import { toast } from "sonner";

// Ledger types that represent money LEAVING the wallet (shown negative).
const NEGATIVE_TYPES = new Set(["withdrawal", "investment", "fee"]);

const tail = (s: string | null | undefined) => (s ? s.slice(-4) : "");

export const InvestorWallet = () => {
  const queryClient = useQueryClient();

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

  const methods = savedMethods ?? [];
  const banks = bankAccounts ?? [];
  const wallets = cryptoWallets ?? [];
  const platforms = platformAccounts ?? [];

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

  // ---- Card tokenization (existing PCI-safe flow) ----
  const [addingCard, setAddingCard] = useState(false);
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
  const handleAddCard = async () => {
    setAddingCard(true);
    try {
      await paymentMethodsApi.setupIntent();
      toast.info("Secure card entry ready", {
        description: "Complete your card details in the Stripe secure form to save it.",
      });
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        toast.info("Saving cards isn't available yet", {
          description: "Card storage turns on once card payments are configured.",
        });
      } else {
        toast.error(e instanceof ApiError ? e.message : "Could not start card setup.");
      }
    } finally {
      setAddingCard(false);
    }
  };

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
    const payoutId = withdrawMethod === "bank" ? selectedBankId || banks.find((b) => b.is_default)?.id
                                              : selectedWalletId || wallets.find((w) => w.is_default)?.id;
    if (!payoutId) {
      toast.error(
        withdrawMethod === "bank" ? "Add a bank account first" : "Add a crypto wallet first",
      );
      return;
    }
    setWithdrawing(true);
    try {
      await withdrawApi.create(
        { amount: amt, method: withdrawMethod, payout_method_id: payoutId },
        crypto.randomUUID(),
      );
      toast.success("Withdrawal requested", {
        description: "Your request has been sent to our team and will be processed shortly.",
      });
      setWithdrawAmount("");
      invalidateWallet();
    } catch (error) {
      const code = error instanceof ApiError ? error.code : "";
      const map: Record<string, string> = {
        KYC_REQUIRED: "Complete identity verification before withdrawing.",
        NO_PAYOUT_METHOD: "Add a payout destination first.",
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
        <Dialog>
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
                    <SelectItem value="card">Card (Visa / Mastercard / Apple Pay / Google Pay)</SelectItem>
                    <SelectItem value="crypto">Cryptocurrency</SelectItem>
                    <SelectItem value="bank">Bank Transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>

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
                disabled={depositing || (depositMethod === "bank" && platforms.length === 0)}
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
        <Dialog>
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

              {withdrawMethod === "bank" &&
                (banks.length === 0 ? (
                  <p className="text-sm text-muted-foreground rounded-lg bg-muted/50 p-3">
                    You have no saved bank account. Add one in <b>Payment Methods</b> below first.
                  </p>
                ) : (
                  <div className="space-y-2">
                    <Label>Destination account</Label>
                    <Select
                      value={selectedBankId || banks.find((b) => b.is_default)?.id || ""}
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
                      value={selectedWalletId || wallets.find((w) => w.is_default)?.id || ""}
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

              <Button className="w-full" onClick={handleWithdraw} disabled={withdrawing}>
                {withdrawing ? "Submitting…" : `Withdraw $${withdrawAmount || "0"}`}
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                Withdrawals are reviewed and paid out by our team, usually within 1–2 business days.
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
                <Button
                  variant="outline"
                  size="sm"
                  aria-label="Add card"
                  disabled={addingCard}
                  onClick={handleAddCard}
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
              {methods.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No saved cards. Stored securely by our payment processor — we never see your card
                  number.
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
    </div>
  );
};
