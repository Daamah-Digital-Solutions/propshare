import { useState, useMemo } from "react";
import { INSTALLMENT_DURATIONS } from "@/lib/installments";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { 
  Users, 
  Clock, 
  TrendingUp, 
  ArrowRight,
  CheckCircle,
  Calendar,
  Download,
  FileText,
  AlertCircle,
  Calculator,
  Building2
} from "lucide-react";
import { format, addMonths } from "date-fns";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { installmentsApi, ApiError } from "@/lib/api";
import { rememberPendingPayment } from "@/components/dashboard/PaymentReturnStatus";
import { PaymentMethodList, usePaymentOptions } from "@/components/payments/PaymentMethodList";
import { CryptoCoinSelect } from "@/components/payments/CryptoCoinSelect";
import { coinLabel, useCryptoCoins } from "@/lib/cryptoCoins";
import {
  EMPTY_SUKUK_DRAFT,
  SukukCertificateFields,
  sukukReady,
  type SukukDraft,
} from "@/components/payments/SukukCertificateFields";
import { payMethod, type PayMethodId } from "@/lib/paymentMethods";
import { money as fmtMoney, unitPrice as fmtUnitPrice } from "@/lib/money";

interface PropertyData {
  propertyValue: number;
  unitPrice?: number; // price of one unit: a plan is for whole units only
  minInvestment: number;
  maxInvestment: number;
  expectedYield: number;
  totalReturn: number;
  fundingProgress: number;
  fundedAmount: number;
  investorsCount: number;
  // Optional: real listings carry no countdown, so the pill is hidden unless it is > 0.
  daysLeft?: number;
  expectedCompletion?: string;
  constructionProgress?: number;
  // Backend-supplied, admin-configurable installment fee rate (percent). The client
  // displays it; the SERVER applies the authoritative rate at plan creation.
  fees?: { installmentFee?: number };
}

interface InstallmentScheduleItem {
  period: number;
  dueDate: Date;
  baseAmount: number;
  fee: number;
  amount: number;
  type: "downpayment" | "installment" | "final";
  status: "pending" | "paid";
}

interface InstallmentCalculatorProps {
  propertyId: string;
  propertyData: PropertyData;
  investmentAmount: number;
  setInvestmentAmount: (amount: number) => void;
  propertyTitle: string;
  /** Plan length chosen upstream (the assistant's prepared order), e.g. "18". */
  initialDuration?: string;
}

// The down payment is paid with any method of the ONE list every property offers
// (src/lib/paymentMethods.ts): from the wallet at once, on a secure checkout (card, Apple /
// Google Pay, crypto, or Pronova with its discount off the down payment), or with a Nova Sukuk
// certificate our team reviews. The installments then come from the wallet on their dates.

// One table for the calculator and the property page (mirrors the backend).
const installmentDurations = INSTALLMENT_DURATIONS;

const InstallmentCalculator = ({
  propertyId,
  propertyData,
  investmentAmount,
  setInvestmentAmount,
  propertyTitle,
  initialDuration,
}: InstallmentCalculatorProps) => {
  const [selectedPayment, setSelectedPayment] = useState<PayMethodId>("wallet");
  const [sukuk, setSukuk] = useState<SukukDraft>(EMPTY_SUKUK_DRAFT);
  // crypto: the coin (and its network) the down payment is sent in, chosen here
  const [coin, setCoin] = useState<string | null>(null);
  const [duration, setDuration] = useState(() =>
    INSTALLMENT_DURATIONS.some((d) => d.value === initialDuration) ? initialDuration! : "12",
  );
  const [showSchedule, setShowSchedule] = useState(false);
  const [scheduleReviewed, setScheduleReviewed] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const queryClient = useQueryClient();

  const selectedMethod = payMethod(selectedPayment);
  const sukukSelected = selectedPayment === "sukuk";
  const pronovaSelected = selectedPayment === "pronova";
  const cryptoSelected = selectedPayment === "crypto";
  // the chosen coin as its list names it ("USDT · Tether USD (Tron)"), for the confirm step
  const chosenCoin = useCryptoCoins(cryptoSelected).data?.items.find((c) => c.code === coin);
  const { data: payOptions } = usePaymentOptions();
  const pronovaPct = Number(payOptions?.pronova_discount_pct ?? 0);
  const selectedDuration = installmentDurations.find(d => d.value === duration);
  const months = parseInt(duration);

  // Fee rate is server-authoritative + admin-configurable (installment_fee_pct), delivered
  // via the property's fees payload — NOT a hardcoded literal. Applied to the down payment
  // and to each installment; the SERVER recomputes the exact charge at plan creation.
  const FEE_RATE = (propertyData.fees?.installmentFee ?? 4) / 100;

  // The server turns the amount into whole units at the unit price and builds the plan on
  // what those cost, so every figure below is computed on that: what is shown is what is
  // charged.
  const unitPrice = Number(propertyData.unitPrice ?? 0);
  const wholeUnits = unitPrice > 0 ? Math.floor((investmentAmount + 1e-9) / unitPrice) : 0;
  const planAmount = unitPrice > 0 ? Math.round(wholeUnits * unitPrice * 100) / 100 : investmentAmount;
  const belowOneUnit = unitPrice > 0 && wholeUnits < 1;

  // Installment calculations (fees applied separately to each payment)
  const downPaymentPercent = selectedDuration?.downPaymentPercent || 25;
  const baseDownPayment = (planAmount * downPaymentPercent) / 100;
  const downPaymentFee = baseDownPayment * FEE_RATE;
  const downPayment = baseDownPayment + downPaymentFee;
  
  const baseRemainingAmount = planAmount - baseDownPayment;
  const numberOfInstallments = months - 1; // First month is down payment
  const baseInstallmentAmount = baseRemainingAmount / numberOfInstallments;
  const installmentFee = baseInstallmentAmount * FEE_RATE;
  const installmentAmount = baseInstallmentAmount + installmentFee;
  
  // Total calculations
  const totalFees = downPaymentFee + (installmentFee * numberOfInstallments);
  // Pronova: its discount comes off what is paid now — the down payment and its fee
  // (platform-funded; the server applies the real rate).
  const downPaymentDiscount = pronovaSelected ? Math.round(downPayment * pronovaPct) / 100 : 0;
  const dueNow = downPayment - downPaymentDiscount;
  const totalInvestment = planAmount + totalFees - downPaymentDiscount;

  // Generate installment schedule with fee breakdown
  const installmentSchedule = useMemo((): InstallmentScheduleItem[] => {
    const schedule: InstallmentScheduleItem[] = [];
    const startDate = new Date();

    // Down payment (Period 0)
    schedule.push({
      period: 0,
      dueDate: startDate,
      baseAmount: baseDownPayment,
      fee: downPaymentFee,
      amount: downPayment,
      type: "downpayment",
      status: "pending"
    });

    // Monthly installments
    for (let i = 1; i < months; i++) {
      const isLast = i === months - 1;
      schedule.push({
        period: i,
        dueDate: addMonths(startDate, i),
        baseAmount: baseInstallmentAmount,
        fee: installmentFee,
        amount: installmentAmount,
        type: isLast ? "final" : "installment",
        status: "pending"
      });
    }

    return schedule;
  }, [baseDownPayment, downPaymentFee, downPayment, baseInstallmentAmount, installmentFee, installmentAmount, months]);

  const expectedAnnualReturn = (planAmount * propertyData.expectedYield) / 100;
  const expectedTotalReturn = (planAmount * propertyData.totalReturn) / 100;

  const quickAmounts = [1000, 2500, 5000, 10000, 25000];

  const handleConfirmPayment = async () => {
    if (sukukSelected && !sukukReady(sukuk)) {
      toast.error("Attach your Nova certificate", {
        description: "Add the certificate (PDF) and accept the Nova Finance pledge first.",
      });
      return;
    }
    if (cryptoSelected && !coin) {
      toast.error("Choose the coin you will send", {
        description: "Pick it under Cryptocurrency: the payment page is made for that coin.",
      });
      return;
    }
    setIsSubmitting(true);
    try {
      if (sukukSelected) {
        // Nova Sukuk: the certificate covers the down payment; our team reviews it while the
        // plan's units are held, and the plan starts once it is approved.
        const r = await installmentsApi.createPlanWithSukuk(
          { property_id: propertyId, amount: planAmount, duration_months: months },
          {
            file: sukuk.file as File,
            certificate_no: sukuk.certificate_no,
            issuer: sukuk.issuer,
            certificate_value: sukuk.certificate_value,
            valid_until: sukuk.valid_until,
          },
        );
        toast.success("Certificate sent for review", {
          description: `The plan's units are held for you while our team reviews your certificate (it must cover $${r.amount_due}). The plan starts once it is approved.`,
        });
        setShowConfirmation(false);
        setShowSchedule(false);
        setSukuk(EMPTY_SUKUK_DRAFT);
        queryClient.invalidateQueries({ queryKey: ["property"] });
        queryClient.invalidateQueries({ queryKey: ["installments"] });
        queryClient.invalidateQueries({ queryKey: ["sukuk"] });
        return;
      }
      // Server-authoritative: it reserves the allocation, snapshots the fee and builds the
      // schedule; the wallet pays the down payment at once, any other method on a secure
      // checkout whose confirmation starts the plan.
      const plan = await installmentsApi.createPlan({
        property_id: propertyId,
        amount: planAmount,
        duration_months: months,
        method: selectedMethod.apiMethod as "wallet" | "card" | "crypto" | "pronova",
        // the price the plan would lock, as shown here: the server refuses if it has changed
        ...(unitPrice > 0 ? { expected_unit_price: unitPrice } : {}),
        ...(cryptoSelected && coin ? { pay_currency: coin } : {}),
      });
      if (plan.checkout_url) {
        if (plan.payment_id) rememberPendingPayment(plan.payment_id);
        window.location.href = plan.checkout_url;
        return;
      }
      const down = plan.payments.find((p) => p.seq === 0);
      toast.success("Installment plan created!", {
        description: `Down payment of $${down?.total_amount ?? ""} charged from your wallet. ${plan.payments.length} payments scheduled — track them in your dashboard.`,
      });
      setShowConfirmation(false);
      setShowSchedule(false);
      queryClient.invalidateQueries({ queryKey: ["property"] });
      queryClient.invalidateQueries({ queryKey: ["wallet"] });
      queryClient.invalidateQueries({ queryKey: ["installments"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
    } catch (err) {
      const code = err instanceof ApiError ? err.code : undefined;
      if (code === "PRICE_CHANGED") {
        // the unit price moved while this page was open: show the new schedule, ask again
        setShowConfirmation(false);
        setShowSchedule(false);
        setScheduleReviewed(false);
        queryClient.invalidateQueries({ queryKey: ["property"] });
        toast.error("The unit price changed", {
          description: "The plan was recalculated at the new price. Review the schedule and confirm again.",
        });
        return;
      }
      const message =
        code === "KYC_REQUIRED"
          ? "Please complete identity verification before starting an installment plan."
          : code === "INSUFFICIENT_FUNDS"
            ? "Your wallet balance is too low for the down payment. Add funds and try again."
            : code === "INSUFFICIENT_UNITS" || code === "PROPERTY_NOT_OPEN"
              ? "Those units are no longer available."
              : code === "AMOUNT_TOO_LOW"
                ? "Increase the amount — it must cover at least one unit."
                : code === "PAYMENTS_NOT_CONFIGURED"
                  ? "This payment method is not available right now. Please choose another."
                  : err instanceof Error
                    ? err.message
                    : "Something went wrong. Please try again.";
      toast.error(sukukSelected ? "Certificate not sent" : "Could not create installment plan", {
        description: message,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const downloadSchedulePDF = () => {
    // In production, this would generate a proper PDF
    const scheduleText = installmentSchedule.map(item => 
      `${item.type === 'downpayment' ? 'Down Payment' : `Installment ${item.period}`}:\n` +
      `  Base Amount: $${item.baseAmount.toFixed(2)}\n` +
      `  Fee (4%): $${item.fee.toFixed(2)}\n` +
      `  Total: $${item.amount.toFixed(2)}\n` +
      `  Due Date: ${format(item.dueDate, 'MMM dd, yyyy')}`
    ).join('\n\n');

    const blob = new Blob([
      `INSTALLMENT SCHEDULE\n`,
      `${'='.repeat(50)}\n\n`,
      `Property: ${propertyTitle}\n`,
      `Investment Amount: $${planAmount.toFixed(2)}\n`,
      `Duration: ${months} months\n\n`,
      `FEE STRUCTURE:\n`,
      `- Down Payment Fee: 4% ($${downPaymentFee.toFixed(2)})\n`,
      `- Installment Fee: 4% per payment ($${(installmentFee * numberOfInstallments).toFixed(2)} total)\n`,
      `- Total Fees: $${totalFees.toFixed(2)}\n`,
      `- Performance Fee: 10% of annual profit (calculated annually)\n\n`,
      `TOTAL INVESTMENT: $${totalInvestment.toFixed(2)}\n\n`,
      `${'='.repeat(50)}\n\n`,
      `PAYMENT SCHEDULE:\n\n${scheduleText}\n\n`,
      `${'='.repeat(50)}\n`,
      `Generated on: ${format(new Date(), 'MMM dd, yyyy')}\n`,
      `\nNote: Performance fee of 10% applies to annual realized profits and capital growth.`
    ], { type: 'text/plain' });
    
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `installment-schedule-${propertyTitle.replace(/\s+/g, '-').toLowerCase()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    
    toast.success("Schedule downloaded!");
  };

  return (
    <div className="bg-card rounded-2xl border border-border shadow-lg overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-br from-accent to-accent/80 p-6 text-accent-foreground">
        <div className="flex items-center gap-2 mb-3">
          <Building2 className="h-5 w-5" />
          <Badge variant="secondary" className="bg-background/20 text-accent-foreground">
            Under Construction
          </Badge>
        </div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="text-sm opacity-80">Property Value</div>
            <div className="text-2xl font-bold">${propertyData.propertyValue.toLocaleString()}</div>
          </div>
          <div className="text-right">
            <div className="text-sm opacity-80">Expected Return</div>
            <div className="text-2xl font-bold">{propertyData.totalReturn}%</div>
          </div>
        </div>

        {/* Construction Progress */}
        {(propertyData.constructionProgress > 0 || propertyData.expectedCompletion) && (
          <div className="space-y-2 mb-4">
            <div className="flex justify-between text-sm">
              <span>Construction Progress</span>
              <span>{propertyData.constructionProgress}%</span>
            </div>
            <Progress value={propertyData.constructionProgress} className="h-2 bg-background/20" />
            {propertyData.expectedCompletion && (
              <p className="text-xs opacity-80">
                Expected completion:{" "}
                {(() => {
                  const d = new Date(propertyData.expectedCompletion);
                  return Number.isNaN(d.getTime())
                    ? propertyData.expectedCompletion
                    : d.toLocaleDateString("en-GB", { month: "short", year: "numeric" });
                })()}
              </p>
            )}
          </div>
        )}

        {/* Funding Progress */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>${propertyData.fundedAmount.toLocaleString()} funded</span>
            <span>{propertyData.fundingProgress}%</span>
          </div>
          <Progress value={propertyData.fundingProgress} className="h-2 bg-background/20" />
        </div>

        {/* Stats */}
        <div className="flex justify-between mt-4 text-sm">
          <div className="flex items-center gap-1">
            <Users size={14} />
            <span>{propertyData.investorsCount} investors</span>
          </div>
          {propertyData.daysLeft != null && propertyData.daysLeft > 0 && (
            <div className="flex items-center gap-1">
              <Clock size={14} />
              <span>{propertyData.daysLeft} days left</span>
            </div>
          )}
        </div>
      </div>

      {/* Investment Form */}
      <div className="p-6 space-y-6">
        {/* Amount Selection */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-3">
            Investment Amount
          </label>
          
          {/* Quick Amounts */}
          <div className="flex flex-wrap gap-2 mb-4">
            {quickAmounts.map((amount) => (
              <button
                key={amount}
                onClick={() => setInvestmentAmount(amount)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  investmentAmount === amount
                    ? "bg-primary text-primary-foreground"
                    : "bg-secondary text-foreground hover:bg-secondary/80"
                }`}
              >
                ${amount.toLocaleString()}
              </button>
            ))}
          </div>

          {/* Slider */}
          <div className="space-y-3">
            <Slider
              value={[investmentAmount]}
              onValueChange={([value]) => setInvestmentAmount(value)}
              min={propertyData.minInvestment}
              max={propertyData.maxInvestment}
              step={unitPrice > 0 ? unitPrice : 100}
              className="w-full"
            />
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>Min: ${propertyData.minInvestment}</span>
              <span>Max: ${propertyData.maxInvestment.toLocaleString()}</span>
            </div>
          </div>

          {/* Custom Amount Input */}
          <div className="mt-4 relative">
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
            <input
              type="number"
              value={investmentAmount}
              onChange={(e) => {
                const value = Math.min(Math.max(Number(e.target.value), propertyData.minInvestment), propertyData.maxInvestment);
                setInvestmentAmount(value);
              }}
              className="w-full pl-8 pr-4 py-3 bg-secondary border border-border rounded-xl text-foreground text-lg font-semibold focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          {unitPrice > 0 && (
            <p className="mt-2 text-xs text-muted-foreground" data-testid="plan-units-hint">
              Units cost {fmtUnitPrice(unitPrice)} each. This amount covers{" "}
              <span className="font-medium text-foreground">
                {wholeUnits.toLocaleString("en-US")} whole unit{wholeUnits === 1 ? "" : "s"}
              </span>
              {planAmount !== investmentAmount && wholeUnits > 0 ? ` (${fmtMoney(planAmount)})` : ""}: the
              plan is for those.
            </p>
          )}
        </div>

        {/* Installment Duration */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-3">
            <Calendar className="inline h-4 w-4 mr-1" />
            Installment Duration
          </label>
          <Select value={duration} onValueChange={setDuration}>
            <SelectTrigger>
              <SelectValue placeholder="Select duration" />
            </SelectTrigger>
            <SelectContent>
              {installmentDurations.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label} ({opt.downPaymentPercent}% down payment)
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Payment Method */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-3">
            Payment Method
          </label>
          <PaymentMethodList value={selectedPayment} onChange={setSelectedPayment} />
          <p className="mt-2 text-xs text-muted-foreground">
            This pays the down payment; the monthly installments come from your wallet on their
            dates.
          </p>
          {sukukSelected && (
            <div className="mt-3">
              <SukukCertificateFields amountDue={downPayment} value={sukuk} onChange={setSukuk} />
            </div>
          )}
          {cryptoSelected && (
            <div className="mt-3">
              <CryptoCoinSelect value={coin} onChange={setCoin} purpose="plan" />
            </div>
          )}
        </div>

        {/* Installment Summary */}
        <div className="bg-accent/10 rounded-xl p-4 border border-accent/20">
          <h4 className="font-semibold text-foreground flex items-center gap-2 mb-4">
            <Calculator size={16} className="text-accent" />
            Installment Plan Summary
          </h4>
          
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Down Payment ({downPaymentPercent}%)</span>
              <span className="font-semibold text-foreground">${downPayment.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Monthly Installment</span>
              <span className="font-semibold text-foreground">${installmentAmount.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Number of Installments</span>
              <span className="font-semibold text-foreground">{numberOfInstallments} months</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">First Installment Due</span>
              <span className="font-semibold text-foreground">{format(addMonths(new Date(), 1), 'MMM dd, yyyy')}</span>
            </div>
          </div>
        </div>

        {/* Fee Breakdown */}
        <div className="bg-secondary/50 rounded-xl p-4 space-y-3">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <FileText size={16} className="text-primary" />
            Fee Breakdown
          </h4>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">
                Investment Amount
                {unitPrice > 0 && ` (${wholeUnits.toLocaleString("en-US")} unit${wholeUnits === 1 ? "" : "s"})`}
              </span>
              <span className="text-foreground">${planAmount.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Down Payment ({downPaymentPercent}%)</span>
              <span className="text-foreground">${baseDownPayment.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Down Payment Fee (4%)</span>
              <span className="text-foreground">+${downPaymentFee.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Installment Fee (4% × {numberOfInstallments})</span>
              <span className="text-foreground">+${(installmentFee * numberOfInstallments).toFixed(2)}</span>
            </div>
            {downPaymentDiscount > 0 && (
              <div className="flex justify-between text-success">
                <span>Pronova discount (-{pronovaPct}% of the down payment)</span>
                <span>-${downPaymentDiscount.toFixed(2)}</span>
              </div>
            )}
            <div className="border-t border-border pt-2 flex justify-between font-semibold">
              <span className="text-foreground">Total Investment</span>
              <span className="text-foreground">${totalInvestment.toFixed(2)}</span>
            </div>
          </div>
        </div>

        {/* Expected Returns */}
        <div className="bg-primary/5 rounded-xl p-4 space-y-3">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <TrendingUp size={16} className="text-primary" />
            Expected Returns (Post-Completion)
          </h4>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Annual Rental Income</span>
              <span className="font-medium text-success">+${expectedAnnualReturn.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Est. Total Return (5yr)</span>
              <span className="font-medium text-success">+${expectedTotalReturn.toFixed(2)}</span>
            </div>
          </div>
        </div>

        {/* View Schedule Button */}
        <Button 
          variant="outline" 
          className="w-full gap-2"
          onClick={() => setShowSchedule(true)}
        >
          <Calendar size={18} />
          Review Full Installment Schedule
        </Button>

        {/* Warning */}
        <div className="flex items-start gap-3 p-4 bg-warning/10 rounded-xl border border-warning/20">
          <AlertCircle className="h-5 w-5 text-warning flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium text-foreground">Review Required</p>
            <p className="text-muted-foreground">
              You must review the full installment schedule before proceeding to payment.
            </p>
          </div>
        </div>

        {/* Start the plan: review the schedule, then confirm the down payment (real,
            wallet-funded, server-authoritative). */}
        <Button
          variant="hero"
          size="xl"
          className="w-full"
          disabled={belowOneUnit}
          onClick={() => {
            if (sukukSelected && !sukukReady(sukuk)) {
              toast.error("Attach your Nova certificate", {
                description: "Add the certificate (PDF) and accept the Nova Finance pledge first.",
              });
              return;
            }
            if (!scheduleReviewed) {
              setShowSchedule(true);
            } else {
              setShowConfirmation(true);
            }
          }}
        >
          Start Installment Plan
          <ArrowRight size={20} />
        </Button>

        {/* Trust Indicators */}
        <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            <CheckCircle size={12} className="text-success" />
            <span>Secure Payment</span>
          </div>
          <div className="flex items-center gap-1">
            <CheckCircle size={12} className="text-success" />
            <span>SPV Protected</span>
          </div>
        </div>
      </div>

      {/* Installment Schedule Dialog */}
      <Dialog open={showSchedule} onOpenChange={setShowSchedule}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5 text-primary" />
              Installment Schedule
            </DialogTitle>
            <DialogDescription>
              Review your complete payment schedule for {propertyTitle}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-6 py-4">
            {/* Summary Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-primary/10 rounded-lg p-3 text-center">
                <p className="text-xs text-muted-foreground">Total Investment</p>
                <p className="text-lg font-bold text-primary">${totalInvestment.toFixed(2)}</p>
              </div>
              <div className="bg-accent/10 rounded-lg p-3 text-center">
                <p className="text-xs text-muted-foreground">Down Payment</p>
                <p className="text-lg font-bold text-accent">${downPayment.toFixed(2)}</p>
              </div>
              <div className="bg-secondary rounded-lg p-3 text-center">
                <p className="text-xs text-muted-foreground">Monthly Amount</p>
                <p className="text-lg font-bold">${installmentAmount.toFixed(2)}</p>
              </div>
              <div className="bg-secondary rounded-lg p-3 text-center">
                <p className="text-xs text-muted-foreground">Duration</p>
                <p className="text-lg font-bold">{months} Months</p>
              </div>
            </div>

            {/* Fee Details */}
            <div className="bg-muted/50 rounded-lg p-4">
              <h4 className="font-semibold text-sm mb-3">Fees Breakdown (4% per payment)</h4>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Down Payment Fee</p>
                  <p className="font-medium">${downPaymentFee.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Total Installment Fees</p>
                  <p className="font-medium">${(installmentFee * numberOfInstallments).toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Total Fees</p>
                  <p className="font-medium text-primary">${totalFees.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Performance Fee</p>
                  <p className="font-medium text-muted-foreground">10% on profits*</p>
                </div>
              </div>
              {downPaymentDiscount > 0 && (
                <p className="text-success text-sm mt-2">Pronova discount on the down payment: -${downPaymentDiscount.toFixed(2)}</p>
              )}
              <p className="text-xs text-muted-foreground mt-3">*Performance fee calculated annually on realized profit</p>
            </div>

            {/* Schedule Table */}
            <div className="border rounded-lg overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Period</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Due Date</TableHead>
                    <TableHead className="text-right">Base</TableHead>
                    <TableHead className="text-right">Fee (4%)</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {installmentSchedule.map((item) => (
                    <TableRow key={item.period}>
                      <TableCell className="font-medium">
                        {item.type === "downpayment" ? "Initial" : `Month ${item.period}`}
                      </TableCell>
                      <TableCell>
                        <Badge 
                          variant={item.type === "downpayment" ? "default" : "outline"}
                          className={item.type === "downpayment" ? "bg-accent" : ""}
                        >
                          {item.type === "downpayment" ? "Down Payment" : 
                           item.type === "final" ? "Final Payment" : "Installment"}
                        </Badge>
                      </TableCell>
                      <TableCell>{format(item.dueDate, 'MMM dd, yyyy')}</TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        ${item.baseAmount.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right text-primary">
                        +${item.fee.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right font-semibold">
                        ${item.amount.toFixed(2)}
                      </TableCell>
                    </TableRow>
                  ))}
                  <TableRow className="bg-muted/50">
                    <TableCell colSpan={3} className="font-semibold">Total</TableCell>
                    <TableCell className="text-right font-medium">${planAmount.toFixed(2)}</TableCell>
                    <TableCell className="text-right font-medium text-primary">${totalFees.toFixed(2)}</TableCell>
                    <TableCell className="text-right font-bold text-primary">
                      ${totalInvestment.toFixed(2)}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </div>

            {/* Confirmation Checkbox */}
            <div className="flex items-start gap-3 p-4 bg-secondary/50 rounded-lg">
              <Checkbox 
                id="reviewed" 
                checked={scheduleReviewed}
                onCheckedChange={(checked) => setScheduleReviewed(checked === true)}
              />
              <label htmlFor="reviewed" className="text-sm cursor-pointer">
                <span className="font-medium">I have reviewed and understand the installment schedule.</span>
                <span className="text-muted-foreground block mt-1">
                  I agree that installments are due on the dates shown above and are charged from my wallet on those dates. If my wallet cannot cover one, it is retried automatically; there is no late fee.
                </span>
              </label>
            </div>
          </div>

          <DialogFooter className="flex-col sm:flex-row gap-2">
            <Button variant="outline" onClick={downloadSchedulePDF} className="gap-2">
              <Download className="h-4 w-4" />
              Download Schedule
            </Button>
            <Button 
              onClick={() => {
                if (scheduleReviewed) {
                  setShowSchedule(false);
                  setShowConfirmation(true);
                } else {
                  toast.error("Please confirm you have reviewed the schedule");
                }
              }}
              disabled={!scheduleReviewed}
              className="gap-2"
            >
              <CheckCircle className="h-4 w-4" />
              Proceed to Payment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Payment Confirmation Modal */}
      {showConfirmation && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card rounded-2xl p-6 max-w-md w-full border border-border shadow-xl animate-scale-in">
            <div className="text-center mb-6">
              <div className="w-16 h-16 bg-success/10 rounded-full flex items-center justify-center mx-auto mb-4">
                <CheckCircle size={32} className="text-success" />
              </div>
              <h3 className="text-xl font-bold text-foreground mb-2">Confirm Down Payment</h3>
              <p className="text-muted-foreground">
                You are about to pay the down payment for {propertyTitle}
              </p>
            </div>

            <div className="bg-secondary/50 rounded-xl p-4 mb-6 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Down Payment</span>
                <span className="font-medium text-foreground">${downPayment.toFixed(2)}</span>
              </div>
              {downPaymentDiscount > 0 && (
                <div className="flex justify-between text-success">
                  <span>Pronova discount</span>
                  <span>-${downPaymentDiscount.toFixed(2)}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted-foreground">Paying with</span>
                <span className="font-medium text-foreground">{selectedMethod.label}</span>
              </div>
              {cryptoSelected && coin && (
                <p className="text-xs text-muted-foreground">
                  You pay in {chosenCoin ? coinLabel(chosenCoin) : coin.toUpperCase()}. Send that
                  coin and network only, the exact amount the payment page shows: the plan starts
                  once the network confirms it. Anything less goes to your wallet instead.
                </p>
              )}
              <div className="flex justify-between">
                <span className="text-muted-foreground">Remaining ({numberOfInstallments} installments)</span>
                <span className="font-medium text-foreground">${(installmentAmount * numberOfInstallments).toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>(includes 4% fee per installment)</span>
              </div>
              <div className="border-t border-border pt-2 flex justify-between font-semibold">
                <span className="text-foreground">Total Investment</span>
                <span className="text-foreground">${totalInvestment.toFixed(2)}</span>
              </div>
            </div>

            <div className="bg-primary/5 rounded-xl p-4 mb-6">
              <p className="text-sm text-muted-foreground">
                After payment, your installment plan will be added to your <strong>Investor Dashboard</strong> where you can track and manage all upcoming payments.
              </p>
            </div>

            <div className="flex gap-3">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => setShowConfirmation(false)}
                disabled={isSubmitting}
              >
                Cancel
              </Button>
              <Button
                variant="hero"
                className="flex-1"
                onClick={handleConfirmPayment}
                disabled={isSubmitting}
              >
                {isSubmitting
                  ? "Processing…"
                  : selectedPayment === "wallet"
                    ? `Pay $${dueNow.toFixed(2)}`
                    : sukukSelected
                      ? "Submit certificate"
                      : `Continue to pay $${dueNow.toFixed(2)}`}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default InstallmentCalculator;
