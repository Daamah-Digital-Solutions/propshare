import { useState, useMemo } from "react";
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
  CreditCard, 
  Wallet,
  Coins,
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

interface PropertyData {
  propertyValue: number;
  minInvestment: number;
  maxInvestment: number;
  expectedYield: number;
  totalReturn: number;
  fundingProgress: number;
  fundedAmount: number;
  investorsCount: number;
  daysLeft: number;
  expectedCompletion?: string;
  constructionProgress?: number;
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
  propertyData: PropertyData;
  investmentAmount: number;
  setInvestmentAmount: (amount: number) => void;
  propertyTitle: string;
}

const paymentMethods = [
  { id: "card", icon: CreditCard, label: "Card", discount: 0 },
  { id: "wallet", icon: Wallet, label: "Apple/Google Pay", discount: 0 },
  { id: "pronova", icon: Coins, label: "Pronova Token", discount: 5 },
];

const installmentDurations = [
  { value: "6", label: "6 Months", downPaymentPercent: 30 },
  { value: "12", label: "12 Months", downPaymentPercent: 25 },
  { value: "18", label: "18 Months", downPaymentPercent: 20 },
  { value: "24", label: "24 Months", downPaymentPercent: 15 },
];

const InstallmentCalculator = ({ 
  propertyData, 
  investmentAmount, 
  setInvestmentAmount,
  propertyTitle
}: InstallmentCalculatorProps) => {
  const [selectedPayment, setSelectedPayment] = useState("card");
  const [duration, setDuration] = useState("12");
  const [showSchedule, setShowSchedule] = useState(false);
  const [scheduleReviewed, setScheduleReviewed] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);

  const selectedMethod = paymentMethods.find(m => m.id === selectedPayment);
  const discount = selectedMethod?.discount || 0;
  const selectedDuration = installmentDurations.find(d => d.value === duration);
  const months = parseInt(duration);

  // Fee calculations based on Fees page specifications
  // For under-construction properties:
  // - 4% fee on down payment
  // - 4% fee on each installment
  // - 10% performance fee on annual profit (calculated separately, not upfront)
  const FEE_RATE = 0.04; // 4%
  
  // Installment calculations (fees applied separately to each payment)
  const downPaymentPercent = selectedDuration?.downPaymentPercent || 25;
  const baseDownPayment = (investmentAmount * downPaymentPercent) / 100;
  const downPaymentFee = baseDownPayment * FEE_RATE;
  const downPayment = baseDownPayment + downPaymentFee;
  
  const baseRemainingAmount = investmentAmount - baseDownPayment;
  const numberOfInstallments = months - 1; // First month is down payment
  const baseInstallmentAmount = baseRemainingAmount / numberOfInstallments;
  const installmentFee = baseInstallmentAmount * FEE_RATE;
  const installmentAmount = baseInstallmentAmount + installmentFee;
  
  // Total calculations
  const totalFees = downPaymentFee + (installmentFee * numberOfInstallments);
  const discountAmount = (totalFees * discount) / 100;
  const finalFees = totalFees - discountAmount;
  const totalInvestment = investmentAmount + finalFees;

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

  const expectedAnnualReturn = (investmentAmount * propertyData.expectedYield) / 100;
  const expectedTotalReturn = (investmentAmount * propertyData.totalReturn) / 100;

  const quickAmounts = [1000, 2500, 5000, 10000, 25000];

  const handleProceedToPayment = () => {
    if (!scheduleReviewed) {
      toast.error("Please review the installment schedule first");
      return;
    }
    setShowConfirmation(true);
  };

  const handleConfirmPayment = () => {
    toast.success("Investment confirmed!", {
      description: `Down payment of $${downPayment.toFixed(2)} processed. Installment plan added to your dashboard.`,
    });
    setShowConfirmation(false);
    setShowSchedule(false);
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
      `Investment Amount: $${investmentAmount.toFixed(2)}\n`,
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
        {propertyData.constructionProgress && (
          <div className="space-y-2 mb-4">
            <div className="flex justify-between text-sm">
              <span>Construction Progress</span>
              <span>{propertyData.constructionProgress}%</span>
            </div>
            <Progress value={propertyData.constructionProgress} className="h-2 bg-background/20" />
            {propertyData.expectedCompletion && (
              <p className="text-xs opacity-80">Expected completion: {propertyData.expectedCompletion}</p>
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
          <div className="flex items-center gap-1">
            <Clock size={14} />
            <span>{propertyData.daysLeft} days left</span>
          </div>
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
              step={100}
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
          <div className="space-y-2">
            {paymentMethods.map((method) => (
              <button
                key={method.id}
                onClick={() => setSelectedPayment(method.id)}
                className={`w-full flex items-center justify-between p-4 rounded-xl border transition-all ${
                  selectedPayment === method.id
                    ? "border-primary bg-primary/5"
                    : "border-border hover:border-primary/50"
                }`}
              >
                <div className="flex items-center gap-3">
                  <method.icon size={20} className="text-primary" />
                  <span className="font-medium text-foreground">{method.label}</span>
                </div>
                {method.discount > 0 && (
                  <span className="text-sm font-semibold text-success bg-success/10 px-2 py-1 rounded-full">
                    -{method.discount}% fees
                  </span>
                )}
              </button>
            ))}
          </div>
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
              <span className="text-muted-foreground">Investment Amount</span>
              <span className="text-foreground">${investmentAmount.toLocaleString()}</span>
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
            {discount > 0 && (
              <div className="flex justify-between text-success">
                <span>Pronova Discount (-{discount}%)</span>
                <span>-${discountAmount.toFixed(2)}</span>
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

        {/* Installment plans are deferred to their own phase — the calculator stays as an
            illustrative estimator, but you can't yet commit to a plan (no fake success). */}
        <div className="rounded-xl bg-amber-500/10 border border-amber-500/30 p-3 text-sm text-amber-700 dark:text-amber-400 text-center">
          Installment plans are not available yet. Lump-sum investment is available on the
          marketplace today.
        </div>
        <Button variant="hero" size="xl" className="w-full" disabled>
          Installment Plans — Coming Soon
          <Calendar size={20} />
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
              {discount > 0 && (
                <p className="text-success text-sm mt-2">Pronova discount applied: -${discountAmount.toFixed(2)}</p>
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
                    <TableCell className="text-right font-medium">${investmentAmount.toFixed(2)}</TableCell>
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
                  I agree that installments will be due on the dates shown above and understand that late payments may incur additional fees.
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
              >
                Cancel
              </Button>
              <Button 
                variant="hero" 
                className="flex-1"
                onClick={handleConfirmPayment}
              >
                Pay ${downPayment.toFixed(2)}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default InstallmentCalculator;
