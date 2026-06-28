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
  Building,
  Clock,
  CheckCircle2,
  AlertCircle,
  RefreshCcw,
  Sparkles
} from "lucide-react";
import { ReinvestReturns } from "./ReinvestReturns";
import { ExitButton } from "@/components/exit/ExitButton";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  walletApi,
  withdrawApi,
  connectApi,
  ApiError,
  type TransactionItem,
  type WithdrawMethod,
} from "@/lib/api";
import { toast } from "sonner";

// Ledger types that represent money LEAVING the wallet (shown negative).
const NEGATIVE_TYPES = new Set(["withdrawal", "investment", "fee"]);

export const InvestorWallet = () => {
  const [depositAmount, setDepositAmount] = useState("");
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [depositMethod, setDepositMethod] = useState<"card" | "crypto">("card");
  const [depositing, setDepositing] = useState(false);
  const [withdrawMethod, setWithdrawMethod] = useState<WithdrawMethod>("crypto");
  const [cryptoAddress, setCryptoAddress] = useState("");
  const [withdrawing, setWithdrawing] = useState(false);
  const queryClient = useQueryClient();

  const { data: wallet } = useQuery({ queryKey: ["wallet"], queryFn: walletApi.getMe });
  const { data: txnData } = useQuery({
    queryKey: ["wallet-transactions"],
    queryFn: () => walletApi.transactions(),
  });
  const { data: connect } = useQuery({ queryKey: ["connect"], queryFn: connectApi.status });

  const available = Number(wallet?.balance ?? 0);
  const pending = Number(wallet?.pending_balance ?? 0);
  const total = available + pending;

  const walletBalance = { available, pending, total };
  const transactions = (txnData?.items ?? []).map((t: TransactionItem) => ({
    id: t.id,
    type: t.type,
    amount: (NEGATIVE_TYPES.has(t.type) ? -1 : 1) * Number(t.amount),
    method: t.payment_method ?? undefined,
    property: undefined as string | undefined,
    date: new Date(t.created_at).toLocaleDateString(),
    reference: t.reference_id ? t.reference_id.slice(0, 8) : "",
    status: t.status,
  }));

  const handleDeposit = async () => {
    const amt = Number(depositAmount);
    if (!amt || amt <= 0) {
      toast.error("Enter a valid amount");
      return;
    }
    setDepositing(true);
    try {
      const res = await walletApi.deposit({ amount: amt, method: depositMethod }, crypto.randomUUID());
      if (res.checkout_url) {
        window.location.href = res.checkout_url; // hosted checkout; credit happens on the webhook
      } else {
        toast.info("Deposit created", { description: "Awaiting payment confirmation." });
      }
    } catch (error) {
      const code = error instanceof ApiError ? error.code : "";
      if (code === "KYC_REQUIRED") {
        toast.error("Verify your identity first", {
          description: "Complete KYC verification before depositing.",
        });
      } else if (code === "PAYMENTS_NOT_CONFIGURED") {
        toast.info("Deposits are coming online soon", {
          description: "The payment provider is being connected.",
        });
      } else {
        toast.error(error instanceof ApiError ? error.message : "Could not start the deposit.");
      }
    } finally {
      setDepositing(false);
    }
  };

  const handleConnectOnboard = async () => {
    try {
      const res = await connectApi.onboard();
      window.location.href = res.onboarding_url; // hosted Stripe onboarding; returns to dashboard
    } catch (error) {
      const code = error instanceof ApiError ? error.code : "";
      if (code === "PAYOUTS_NOT_CONFIGURED") {
        toast.info("Bank withdrawals are coming online soon");
      } else {
        toast.error(error instanceof ApiError ? error.message : "Could not start bank onboarding.");
      }
    }
  };

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
    if (withdrawMethod === "crypto" && !cryptoAddress.trim()) {
      toast.error("Enter a payout address");
      return;
    }
    setWithdrawing(true);
    try {
      const res = await withdrawApi.create(
        {
          amount: amt,
          method: withdrawMethod,
          address: withdrawMethod === "crypto" ? cryptoAddress.trim() : undefined,
        },
        crypto.randomUUID(),
      );
      const msg =
        res.status === "pending_review"
          ? "Submitted for review (over the auto-approve limit)."
          : "Approved — your payout is being processed.";
      toast.success("Withdrawal requested", { description: msg });
      setWithdrawAmount("");
      setCryptoAddress("");
      queryClient.invalidateQueries({ queryKey: ["wallet"] });
      queryClient.invalidateQueries({ queryKey: ["wallet-transactions"] });
    } catch (error) {
      const code = error instanceof ApiError ? error.code : "";
      const map: Record<string, string> = {
        KYC_REQUIRED: "Complete identity verification before withdrawing.",
        PAYOUTS_NOT_CONFIGURED: "This withdrawal method is being connected — try again soon.",
        CONNECT_NOT_READY: "Link your bank (finish Stripe onboarding) before withdrawing to bank.",
        INSUFFICIENT_FUNDS: "Amount exceeds your available balance.",
        ADDRESS_REQUIRED: "Enter a payout address.",
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
                <p className="text-3xl font-bold mt-1">${walletBalance.available.toLocaleString()}</p>
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
                <p className="text-3xl font-bold text-foreground mt-1">
                  ${walletBalance.pending.toLocaleString()}
                </p>
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
                <p className="text-3xl font-bold text-foreground mt-1">
                  ${walletBalance.total.toLocaleString()}
                </p>
              </div>
              <ArrowUpRight className="h-10 w-10 text-primary" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <div className="flex flex-wrap gap-4">
        <Dialog>
          <DialogTrigger asChild>
            <Button className="gap-2">
              <Plus className="h-4 w-4" />
              Add Funds
            </Button>
          </DialogTrigger>
          <DialogContent>
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
                  onValueChange={(v) => setDepositMethod(v as "card" | "crypto")}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select payment method" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="card">Card (Visa / Mastercard / Apple Pay / Google Pay)</SelectItem>
                    <SelectItem value="crypto">Cryptocurrency</SelectItem>
                    <SelectItem value="bank" disabled>
                      Bank Transfer (coming soon)
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button className="w-full" onClick={handleDeposit} disabled={depositing}>
                {depositing ? "Starting…" : `Deposit $${depositAmount || "0"}`}
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        <Dialog>
          <DialogTrigger asChild>
            <Button variant="outline" className="gap-2">
              <ArrowDownLeft className="h-4 w-4" />
              Withdraw
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Withdraw Funds</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-sm text-muted-foreground">Available Balance</p>
                <p className="text-xl font-bold">${walletBalance.available.toLocaleString()}</p>
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
                    <SelectValue placeholder="Select withdrawal method" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="bank">Bank Account (via Stripe)</SelectItem>
                    <SelectItem value="crypto">Crypto Address</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {withdrawMethod === "crypto" && (
                <div className="space-y-2">
                  <Label>Payout Address</Label>
                  <Input
                    placeholder="Your crypto wallet address"
                    value={cryptoAddress}
                    onChange={(e) => setCryptoAddress(e.target.value)}
                  />
                </div>
              )}

              {withdrawMethod === "bank" && !connect?.payouts_enabled && (
                <div className="p-3 rounded-lg bg-muted/50 space-y-2">
                  <p className="text-sm text-muted-foreground">
                    Link your bank to enable bank withdrawals (one-time Stripe onboarding).
                  </p>
                  <Button variant="outline" className="w-full gap-2" onClick={handleConnectOnboard}>
                    <Building className="h-4 w-4" />
                    {connect?.status === "pending" ? "Continue bank setup" : "Link your bank"}
                  </Button>
                </div>
              )}

              <Button
                className="w-full"
                onClick={handleWithdraw}
                disabled={withdrawing || (withdrawMethod === "bank" && !connect?.payouts_enabled)}
              >
                {withdrawing ? "Submitting…" : `Withdraw $${withdrawAmount || "0"}`}
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                Withdrawals at or under the auto-approve limit process automatically; larger
                amounts are reviewed first.
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
                    <div className={`h-10 w-10 rounded-full flex items-center justify-center ${
                      transaction.type === "deposit" || transaction.type === "dividend"
                        ? "bg-primary/10"
                        : "bg-muted"
                    }`}>
                      {transaction.type === "deposit" ? (
                        <ArrowDownLeft className="h-5 w-5 text-primary" />
                      ) : transaction.type === "dividend" ? (
                        <ArrowUpRight className="h-5 w-5 text-primary" />
                      ) : transaction.type === "withdrawal" ? (
                        <ArrowUpRight className="h-5 w-5 text-muted-foreground" />
                      ) : (
                        <Building className="h-5 w-5 text-accent" />
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-medium capitalize">
                        {transaction.type}
                        {transaction.property && ` - ${transaction.property}`}
                        {transaction.method && ` via ${transaction.method}`}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {transaction.date} • {transaction.reference}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-sm font-semibold ${
                      transaction.amount > 0 ? "text-primary" : "text-foreground"
                    }`}>
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

        {/* Payment Methods — saved-method management is not built yet. Funding goes
            through the hosted-checkout flow (Add Funds) per transaction; we do NOT
            show fake saved cards/banks on the money page. Honest empty-state. */}
        <Card className="bg-card border-border">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-lg">Payment Methods</CardTitle>
            <Button variant="outline" size="sm" disabled aria-label="Add payment method">
              <Plus className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border border-dashed border-border/70 p-6 text-center">
              <CreditCard className="h-7 w-7 mx-auto text-muted-foreground mb-2" />
              <p className="text-sm font-medium text-foreground">No saved payment methods</p>
              <p className="text-xs text-muted-foreground mt-1">
                Saved methods are not available yet. Use “Add Funds” to deposit — you’ll
                choose card or crypto securely at checkout each time.
              </p>
            </div>

            <div className="mt-6 p-4 rounded-lg bg-accent/10 border border-accent/20">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-accent flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-foreground">
                    Pronova Token <span className="text-muted-foreground">(coming soon)</span>
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Paying with Pronova tokens is not yet enabled.
                  </p>
                  <Button variant="link" className="h-auto p-0 text-xs text-muted-foreground mt-2" disabled>
                    Not yet available
                  </Button>
                </div>
              </div>
            </div>

            {/* Reinvest Returns Benefit Note */}
            <div className="mt-4 p-4 rounded-lg bg-primary/10 border border-primary/20">
              <div className="flex items-start gap-3">
                <RefreshCcw className="h-5 w-5 text-primary flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-foreground flex items-center gap-2">
                    Reinvest Returns
                    <Badge className="bg-primary/20 text-primary border-0 text-xs">
                      <Sparkles className="h-3 w-3 mr-1" />
                      5% OFF
                    </Badge>
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Reinvest your distributed returns and receive a 5% instant discount on your next investment!
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
