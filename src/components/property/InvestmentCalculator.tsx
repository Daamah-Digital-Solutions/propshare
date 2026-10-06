import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { 
  Users, 
  Clock, 
  TrendingUp, 
  ArrowRight,
  Info,
  CheckCircle,
  FileText,
  Calendar,
  RefreshCcw,
  Sparkles,
  Gift
} from "lucide-react";
import { useReinvest } from "@/contexts/ReinvestContext";
import { toast } from "sonner";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { investApi, ApiError, type InvestMethod } from "@/lib/api";
import { rememberPendingPayment } from "@/components/dashboard/PaymentReturnStatus";
import { PaymentMethodList } from "@/components/payments/PaymentMethodList";
import { CryptoCoinSelect } from "@/components/payments/CryptoCoinSelect";
import { coinLabel, useCryptoCoins } from "@/lib/cryptoCoins";
import {
  EMPTY_SUKUK_DRAFT,
  SukukCertificateFields,
  sukukReady,
  type SukukDraft,
} from "@/components/payments/SukukCertificateFields";
import { payMethod, type PayMethodId } from "@/lib/paymentMethods";

interface PropertyData {
  propertyValue: number;
  unitPrice?: number; // price of one unit: an amount buys whole units only
  minInvestment: number;
  maxInvestment: number;
  expectedYield: number;
  totalReturn: number;
  fundingProgress: number;
  fundedAmount: number;
  investorsCount: number;
  daysLeft?: number; // real listings carry no funding countdown (unused here)
  // Backend-supplied fee rates (percent). Replaces the old hardcoded constants so
  // the displayed fee always matches what the server charges (admin-configurable).
  fees?: { platformFee?: number; managementFee?: number };
}

interface InvestmentCalculatorProps {
  propertyId: string;
  propertyData: PropertyData;
  investmentAmount: number;
  setInvestmentAmount: (amount: number) => void;
  /** Open the review step (the last one before payment) once: an order the assistant prepared. */
  openReview?: boolean;
  /** Under construction and paid in full: no rent before handover, the return is the unit price. */
  offplan?: boolean;
  /** Called when the review step opens for a prepared order, so the page offers it once. */
  onReviewOpened?: () => void;
}

// Funding rails: the ONE list every property offers (src/lib/paymentMethods.ts) — wallet,
// card / Apple Pay / Google Pay, crypto, Pronova (a discount off the total, settled on
// Stripe — D5) and Nova Sukuk (a certificate our team reviews). The server computes the real
// charge; the client only displays the rates.

const InvestmentCalculator = ({
  propertyId,
  propertyData,
  investmentAmount,
  setInvestmentAmount,
  openReview = false,
  offplan = false,
  onReviewOpened,
}: InvestmentCalculatorProps) => {
  const [selectedPayment, setSelectedPayment] = useState<PayMethodId>("wallet");
  const [sukuk, setSukuk] = useState<SukukDraft>(EMPTY_SUKUK_DRAFT);
  // crypto: the coin (and its network) the buyer will send, chosen here
  const [coin, setCoin] = useState<string | null>(null);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const reviewOpened = useRef(false);
  useEffect(() => {
    if (openReview && !reviewOpened.current) {
      reviewOpened.current = true;
      setShowConfirmation(true);
      onReviewOpened?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openReview]);
  const { reinvestState, clearReinvestment } = useReinvest();
  const queryClient = useQueryClient();

  const selectedMethod = payMethod(selectedPayment);
  const pronovaSelected = selectedPayment === "pronova";
  const sukukSelected = selectedPayment === "sukuk";
  const cryptoSelected = selectedPayment === "crypto";
  // the chosen coin as its list names it ("USDT · Tether USD (Tron)"), for the review step
  const chosenCoin = useCryptoCoins(cryptoSelected).data?.items.find((c) => c.code === coin);

  // Fee rates come from the backend (admin-configurable platform_settings), not
  // hardcoded constants. Platform fee is charged once AT PURCHASE; the management
  // fee is annual (deducted from distributions in Phase 6) — disclosed only here.
  const platformPct = propertyData.fees?.platformFee ?? 2.5;
  const mgmtPct = propertyData.fees?.managementFee ?? 1.0;
  const PURCHASE_FEE_RATE = platformPct / 100;
  const ANNUAL_MANAGEMENT_FEE_RATE = mgmtPct / 100;
  const reinvesting = reinvestState.isReinvesting;
  // a reinvestment is paid from the wallet: the other methods are locked meanwhile
  useEffect(() => {
    if (reinvesting && selectedPayment !== "wallet") setSelectedPayment("wallet");
  }, [reinvesting, selectedPayment]);
  // Whole units only (the server rounds the amount down at purchase): say how many it buys.
  const unitPrice = Number(propertyData.unitPrice ?? 0);
  const wholeUnits = unitPrice > 0 ? Math.floor((investmentAmount + 1e-9) / unitPrice) : 0;
  // The server buys whole units and charges for those, so every figure below is computed on
  // what they cost: the total shown is the total charged. (A reinvestment is priced by the
  // server at its own discounted unit price: its amount stays as typed.)
  const pricedAmount =
    !reinvesting && unitPrice > 0 ? Math.round(wholeUnits * unitPrice * 100) / 100 : investmentAmount;
  const belowOneUnit = !reinvesting && unitPrice > 0 && wholeUnits < 1;

  // The reinvest discount is REAL and applied SERVER-SIDE (admin-configurable
  // reinvest_discount_pct) as a discounted unit PRICE — you pay your returns and receive
  // MORE units; the exact units are computed by the server at confirmation. The client
  // only displays the rate; it never computes the final price (D5 reinvest exception).
  const { data: reinvestCfg } = useQuery({
    queryKey: ["reinvest", "settings"],
    queryFn: investApi.reinvestSettings,
    enabled: reinvesting,
  });
  const reinvestDiscountPct = Number(reinvestCfg?.discount_pct ?? 0);

  // Pronova pay: a REAL, server-applied discount off the TOTAL payable. "Pay with Pronova"
  // settles via card behind the scenes; the server reduces the CHARGED amount by this rate
  // (units + booked value stay full — the discount is a platform-funded promo). The client
  // only DISPLAYS the live rate; it never computes the final charge.
  const { data: pronovaCfg } = useQuery({
    queryKey: ["pronova", "settings"],
    queryFn: investApi.pronovaSettings,
    enabled: pronovaSelected,
  });
  const pronovaDiscountPct = Number(pronovaCfg?.discount_pct ?? 0);

  // Reinvest is funded from the wallet with NO separate purchase fee (the subsidy is the
  // discounted unit price). Standard invest charges the platform fee at purchase.
  const purchaseFee = reinvesting ? 0 : pricedAmount * PURCHASE_FEE_RATE;
  const annualManagementFee = pricedAmount * ANNUAL_MANAGEMENT_FEE_RATE;
  const nominalPayable = pricedAmount + purchaseFee;
  // Pronova promo: discount off the WHOLE payable (server-authoritative; shown to match the charge).
  const paymentDiscountAmount = pronovaSelected ? (nominalPayable * pronovaDiscountPct) / 100 : 0;
  const totalPayable = nominalPayable - paymentDiscountAmount;
  const investmentValue = pricedAmount;

  // Expected returns (net of annual management fee) - based on full investment value
  const grossAnnualReturn = (investmentValue * propertyData.expectedYield) / 100;
  const netAnnualReturn = grossAnnualReturn - annualManagementFee;
  const expectedTotalReturn = (investmentValue * propertyData.totalReturn) / 100;

  const quickAmounts = [100, 500, 1000, 2500, 5000];

  const handleConfirmPayment = async () => {
    const apiMethod = selectedMethod.apiMethod;
    if (!reinvesting && apiMethod === "crypto" && !coin) {
      // a prepared order can open the review step directly: the coin is still chosen first
      setShowConfirmation(false);
      toast.error("Choose the coin you will send", {
        description: "Pick it under Cryptocurrency, then continue.",
      });
      return;
    }
    setIsSubmitting(true);
    try {
      if (!reinvesting && apiMethod === "sukuk") {
        // Nova Sukuk: the certificate goes to our team; the units are held meanwhile.
        const r = await investApi.buyWithSukuk(
          { property_id: propertyId, amount: pricedAmount },
          {
            file: sukuk.file as File,
            certificate_no: sukuk.certificate_no,
            issuer: sukuk.issuer,
            certificate_value: sukuk.certificate_value,
            valid_until: sukuk.valid_until,
          },
          crypto.randomUUID(),
        );
        toast.success("Certificate sent for review", {
          description: `Your ${r.units} unit(s) are held for you while our team reviews it (it must cover $${r.amount_due}). Follow it in your dashboard.`,
        });
        setShowConfirmation(false);
        setSukuk(EMPTY_SUKUK_DRAFT);
        queryClient.invalidateQueries({ queryKey: ["property"] });
        queryClient.invalidateQueries({ queryKey: ["investments"] });
        queryClient.invalidateQueries({ queryKey: ["sukuk"] });
        return;
      }
      if (reinvesting) {
        // Reinvest path: the SERVER applies the discount + computes the units/price.
        const r = await investApi.reinvest(
          { property_id: propertyId, amount: investmentAmount },
          crypto.randomUUID(),
        );
        toast.success("Reinvestment confirmed!", {
          description: `You now own ${r.units} unit(s) at a ${r.discount_pct}% discount (effective price $${r.effective_price}).`,
        });
        setShowConfirmation(false);
        queryClient.invalidateQueries({ queryKey: ["property"] });
        queryClient.invalidateQueries({ queryKey: ["wallet"] });
        queryClient.invalidateQueries({ queryKey: ["transactions"] });
        queryClient.invalidateQueries({ queryKey: ["investments"] });
        queryClient.invalidateQueries({ queryKey: ["portfolio"] });
        clearReinvestment();
        return;
      }
      const res = await investApi.create(
        {
          property_id: propertyId,
          amount: pricedAmount,
          method: apiMethod as InvestMethod,
          // the price these amounts were shown at: the server refuses if it has changed
          ...(unitPrice > 0 ? { expected_unit_price: unitPrice } : {}),
          ...(apiMethod === "crypto" && coin ? { pay_currency: coin } : {}),
        },
        crypto.randomUUID(),
      );
      if (res.checkout_url) {
        // Direct pay: hand off to the hosted checkout; the server confirms the units and the
        // Investments tab follows the payment when the provider sends the buyer back.
        if (res.payment_id) rememberPendingPayment(res.payment_id);
        window.location.href = res.checkout_url;
        return;
      }
      // Wallet-funded: confirmed atomically server-side.
      toast.success("Investment confirmed!", {
        description: `You now own ${res.units} unit(s). Charged $${res.total_charged}.`,
      });
      setShowConfirmation(false);
      // Refresh the property (funding/units) and the user's wallet/portfolio views.
      queryClient.invalidateQueries({ queryKey: ["property"] });
      queryClient.invalidateQueries({ queryKey: ["wallet"] });
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["investments"] });
      if (reinvestState.isReinvesting) clearReinvestment();
    } catch (err) {
      const code = err instanceof ApiError ? err.code : undefined;
      if (code === "PRICE_CHANGED") {
        // the unit price moved while this page was open: show the new amounts, ask again
        setShowConfirmation(false);
        queryClient.invalidateQueries({ queryKey: ["property"] });
        toast.error("The unit price changed", {
          description: "The amounts were updated to the new price. Review them and confirm again.",
        });
        return;
      }
      const message =
        code === "KYC_REQUIRED"
          ? "Please complete identity verification before investing."
          : code === "INSUFFICIENT_FUNDS"
            ? "Your wallet balance is too low. Add funds and try again."
            : code === "INSUFFICIENT_UNITS" || code === "PROPERTY_NOT_OPEN"
              ? "Those units are no longer available."
              : code === "PAYMENTS_NOT_CONFIGURED"
                ? "This payment method is not available right now. Please choose another."
                : err instanceof Error
                  ? err.message
                  : "Something went wrong. Please try again.";
      toast.error(sukukSelected ? "Certificate not sent" : "Investment failed", {
        description: message,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-card rounded-2xl border border-border shadow-lg overflow-hidden">
      {/* Reinvest Discount Banner */}
      {reinvestState.isReinvesting && (
        <div className="bg-gradient-to-r from-primary via-primary/90 to-accent p-4 text-primary-foreground">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 bg-primary-foreground/20 rounded-full flex items-center justify-center">
              <RefreshCcw className="h-5 w-5" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-semibold">Reinvesting Your Returns</span>
                {reinvestDiscountPct > 0 && (
                  <Badge className="bg-primary-foreground/20 text-primary-foreground border-0">
                    <Sparkles className="h-3 w-3 mr-1" />
                    {reinvestDiscountPct}% OFF
                  </Badge>
                )}
              </div>
              <p className="text-sm text-primary-foreground/80">
                Reinvesting ${reinvestState.reinvestAmount.toLocaleString()} — units are priced{" "}
                {reinvestDiscountPct}% lower; your exact units are confirmed at purchase.
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="text-primary-foreground hover:bg-primary-foreground/10"
              onClick={clearReinvestment}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="bg-gradient-hero p-6 text-primary-foreground">
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

        {/* Funding Progress */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>${propertyData.fundedAmount.toLocaleString()} funded</span>
            <span>{propertyData.fundingProgress}%</span>
          </div>
          <Progress value={propertyData.fundingProgress} className="h-2 bg-primary-foreground/20" />
        </div>

        {/* Stats */}
        <div className="flex justify-between mt-4 text-sm">
          <div className="flex items-center gap-1">
            <Users size={14} />
            <span>{propertyData.investorsCount} investors</span>
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
            <p className="mt-2 text-xs text-muted-foreground" data-testid="unit-price-hint">
              Units cost ${unitPrice.toLocaleString()} each. This amount buys{" "}
              <span className="font-medium text-foreground">
                {wholeUnits.toLocaleString()} whole unit{wholeUnits === 1 ? "" : "s"}
              </span>
              ; the exact units are confirmed at purchase.
            </p>
          )}
        </div>

        {/* Payment Method */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-3">
            Payment Method
          </label>
          <PaymentMethodList
            value={selectedPayment}
            onChange={setSelectedPayment}
            only={reinvesting ? ["wallet"] : undefined}
            onlyNote="A reinvestment is paid from your wallet."
          />
          {sukukSelected && !reinvesting && (
            <div className="mt-3">
              <SukukCertificateFields amountDue={totalPayable} value={sukuk} onChange={setSukuk} />
            </div>
          )}
          {cryptoSelected && !reinvesting && (
            <div className="mt-3">
              <CryptoCoinSelect value={coin} onChange={setCoin} purpose="purchase" />
            </div>
          )}
        </div>

        {/* Reinvest discount note (real, server-applied) */}
        {reinvesting && (
          <div className="bg-success/10 rounded-xl p-4 border border-success/20">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 bg-success/20 rounded-full flex items-center justify-center">
                <Gift className="h-5 w-5 text-success" />
              </div>
              <div className="flex-1">
                <p className="font-semibold text-success">{reinvestDiscountPct}% Reinvest Discount</p>
                <p className="text-sm text-muted-foreground">
                  Reinvested returns buy units at a {reinvestDiscountPct}% lower price, applied by
                  the server. Your exact unit count is confirmed at purchase.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Expected Returns */}
        {offplan ? (
        <div className="bg-primary/5 rounded-xl p-4 space-y-2" data-testid="offplan-returns">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <TrendingUp size={16} className="text-primary" />
            How this investment earns
          </h4>
          <p className="text-sm text-muted-foreground">
            This property is under construction: it pays no rent before handover. Your return is
            the change in the unit price, which is updated as the project advances. You can offer
            your units for sale on the secondary market at the price of the day (a sale needs a
            buyer; a lock-up or a Nova pledge may apply).
          </p>
        </div>
        ) : (
        <div className="bg-primary/5 rounded-xl p-4 space-y-3">
          <h4 className="font-semibold text-foreground flex items-center gap-2">
            <TrendingUp size={16} className="text-primary" />
            Expected Returns
          </h4>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Gross Annual Rental</span>
              <span className="font-medium text-foreground">+${grossAnnualReturn.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Less: Management Fee ({mgmtPct}%)</span>
              <span className="font-medium text-destructive">-${annualManagementFee.toFixed(2)}</span>
            </div>
            <div className="flex justify-between border-t border-border pt-2">
              <span className="text-muted-foreground">Net Annual Income</span>
              <span className="font-medium text-success">+${netAnnualReturn.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Est. Total Return (5yr)</span>
              <span className="font-medium text-success">+${expectedTotalReturn.toFixed(2)}</span>
            </div>
          </div>
        </div>
        )}

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
                {!reinvesting && unitPrice > 0 && ` (${wholeUnits.toLocaleString()} unit${wholeUnits === 1 ? "" : "s"})`}
              </span>
              <span className="text-foreground">${pricedAmount.toLocaleString()}</span>
            </div>
            {reinvesting && (
              <div className="flex justify-between text-success">
                <span className="flex items-center gap-1">
                  <RefreshCcw size={12} />
                  Reinvest discount
                </span>
                <span>{reinvestDiscountPct}% (server-applied to unit price)</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">
                Purchase Fee ({reinvesting ? "0" : platformPct}%)
              </span>
              <span className="text-foreground">+${purchaseFee.toFixed(2)}</span>
            </div>
            {pronovaSelected && paymentDiscountAmount > 0 && (
              <div className="flex justify-between text-success">
                <span>Pronova discount (-{pronovaDiscountPct}% of total)</span>
                <span>-${paymentDiscountAmount.toFixed(2)}</span>
              </div>
            )}
            <div className="border-t border-border pt-2 flex justify-between font-semibold">
              <span className="text-foreground">Total Payable Now</span>
              <span className="text-foreground">${totalPayable.toFixed(2)}</span>
            </div>
          </div>
          
          {/* Annual fee note */}
          <div className="flex items-start gap-2 pt-2 border-t border-border">
            <Calendar size={14} className="text-muted-foreground mt-0.5 flex-shrink-0" />
            <p className="text-xs text-muted-foreground">
              <span className="font-medium">Annual Management Fee:</span> {mgmtPct}% (${annualManagementFee.toFixed(2)}/year)
              will be deducted from your rental distributions{offplan ? ", which start after handover" : ""}.
            </p>
          </div>
        </div>

        {/* CTA Button */}
        <Button 
          variant="hero" 
          size="xl" 
          className="w-full"
          disabled={belowOneUnit}
          onClick={() => {
            if (sukukSelected && !reinvesting && !sukukReady(sukuk)) {
              toast.error("Attach your Nova certificate", {
                description: "Add the certificate (PDF) and accept the Nova Finance pledge first.",
              });
              return;
            }
            if (cryptoSelected && !reinvesting && !coin) {
              toast.error("Choose the coin you will send", {
                description: "Pick it under Cryptocurrency: the payment page is made for that coin.",
              });
              return;
            }
            setShowConfirmation(true);
          }}
        >
          {reinvestState.isReinvesting ? (
            <>
              Reinvest ${investmentAmount.toLocaleString()} (Pay ${totalPayable.toFixed(2)})
              <RefreshCcw size={20} />
            </>
          ) : (
            <>
              Invest ${pricedAmount.toLocaleString()}
              <ArrowRight size={20} />
            </>
          )}
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

      {/* Confirmation Modal */}
      {showConfirmation && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card rounded-2xl p-6 max-w-md w-full border border-border shadow-xl animate-scale-in">
            <div className="text-center mb-6">
              <div className="w-16 h-16 bg-success/10 rounded-full flex items-center justify-center mx-auto mb-4">
                <CheckCircle size={32} className="text-success" />
              </div>
              <h3 className="text-xl font-bold text-foreground mb-2">
                {reinvestState.isReinvesting ? "Confirm Reinvestment" : "Confirm Investment"}
              </h3>
              <p className="text-muted-foreground">
                You are about to {reinvesting ? "reinvest" : "invest"} $
                {pricedAmount.toLocaleString()} in this property
              </p>
            </div>

            <div className="bg-secondary/50 rounded-xl p-4 mb-6 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Investment Value</span>
                <span className="font-medium text-foreground">${pricedAmount.toLocaleString()}</span>
              </div>
              {reinvesting && (
                <div className="flex justify-between text-success">
                  <span className="flex items-center gap-1">
                    <RefreshCcw size={12} />
                    Reinvest discount
                  </span>
                  <span>{reinvestDiscountPct}% (server-applied)</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted-foreground">
                  Purchase Fee ({reinvesting ? "0" : platformPct}%)
                </span>
                <span className="font-medium text-foreground">+${purchaseFee.toFixed(2)}</span>
              </div>
              {pronovaSelected && paymentDiscountAmount > 0 && (
                <div className="flex justify-between text-success">
                  <span>Pronova discount (-{pronovaDiscountPct}%)</span>
                  <span>-${paymentDiscountAmount.toFixed(2)}</span>
                </div>
              )}
              <div className="border-t border-border pt-2 flex justify-between font-semibold">
                <span className="text-foreground">Total Payable</span>
                <span className="text-foreground">${totalPayable.toFixed(2)}</span>
              </div>
              {reinvesting && (
                <div className="pt-2 border-t border-border">
                  <div className="flex items-center gap-2 text-success">
                    <Gift size={14} />
                    <span className="font-medium">
                      Units priced {reinvestDiscountPct}% lower — confirmed at purchase
                    </span>
                  </div>
                </div>
              )}
              <div className="pt-2 border-t border-border">
                <p className="text-xs text-muted-foreground">
                  + {mgmtPct}% annual management fee (${annualManagementFee.toFixed(2)}/yr) deducted from distributions
                </p>
              </div>
              {!reinvesting && (
                <div className="pt-2 border-t border-border flex justify-between">
                  <span className="text-muted-foreground">Paying with</span>
                  <span className="font-medium text-foreground">{selectedMethod.label}</span>
                </div>
              )}
              {!reinvesting && cryptoSelected && (
                <p className="text-xs text-muted-foreground">
                  {coin ? `You pay in ${chosenCoin ? coinLabel(chosenCoin) : coin.toUpperCase()}. ` : ""}
                  Send that coin and network
                  only, the exact amount the payment page shows: your units are confirmed once
                  the network confirms it. Anything less goes to your wallet instead.
                </p>
              )}
              {!reinvesting && sukukSelected && (
                <p className="text-xs text-muted-foreground">
                  Your certificate goes to our team for review. The units are held for you
                  meanwhile and stay pledged to Nova Finance once approved.
                </p>
              )}
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
                  : reinvesting || selectedPayment === "wallet"
                    ? "Confirm & Pay"
                    : sukukSelected
                      ? "Submit certificate"
                      : "Continue to secure payment"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default InvestmentCalculator;
