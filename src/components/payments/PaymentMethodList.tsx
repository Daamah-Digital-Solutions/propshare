import { useQuery } from "@tanstack/react-query";
import { investApi } from "@/lib/api";
import {
  PAYMENT_METHODS,
  applePayOnThisDevice,
  type PayMethodId,
  type PaymentOptions,
} from "@/lib/paymentMethods";

/**
 * The payment methods of a property purchase — the SAME list, in the same order, on every
 * property (a ready one and an installment plan's down payment alike). The server says which
 * rails are live; one that is not is shown as unavailable, never hidden.
 */
interface Props {
  value: PayMethodId;
  onChange: (id: PayMethodId) => void;
  /** Only these can be picked right now (e.g. a reinvestment is paid from the wallet). */
  only?: readonly PayMethodId[];
  /** Why the others are locked (shown under the list). */
  onlyNote?: string;
}

export function usePaymentOptions() {
  return useQuery<PaymentOptions>({
    queryKey: ["payment-options"],
    queryFn: investApi.paymentOptions,
    staleTime: 60_000,
  });
}

export function PaymentMethodList({ value, onChange, only, onlyNote }: Props) {
  const { data: options } = usePaymentOptions();
  const pronovaPct = Number(options?.pronova_discount_pct ?? 0);
  const applePay = applePayOnThisDevice();

  return (
    <div className="space-y-2" data-testid="payment-methods">
      {PAYMENT_METHODS.map((method) => {
        // unknown until the server answers: offer it (the server still refuses a dead rail)
        const live = options ? options[method.id] : true;
        const locked = Boolean(only && !only.includes(method.id));
        const noDevice = method.id === "apple_pay" && !applePay;
        const disabled = !live || locked || noDevice;
        const note = !live
          ? "Not available right now"
          : noDevice
            ? "Not available in this browser"
            : null;
        const badge =
          method.id === "pronova"
            ? pronovaPct > 0
              ? `${pronovaPct}% OFF`
              : undefined
            : method.badge;
        const selected = value === method.id && !disabled;
        return (
          <button
            key={method.id}
            type="button"
            disabled={disabled}
            aria-pressed={selected}
            data-method={method.id}
            onClick={() => !disabled && onChange(method.id)}
            className={`w-full flex items-center justify-between gap-3 p-4 rounded-xl border text-left transition-all ${
              disabled
                ? "border-border opacity-50 cursor-not-allowed"
                : selected
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/50"
            }`}
          >
            <div className="flex items-center gap-3 min-w-0">
              <method.icon size={20} className="text-primary shrink-0" />
              <div className="min-w-0">
                <div className="font-medium text-foreground">{method.label}</div>
                <div className="text-xs text-muted-foreground">
                  {method.id === "pronova" && pronovaPct > 0
                    ? `${pronovaPct}% off everything you pay now — settled on Stripe`
                    : method.description}
                </div>
                {note && <div className="text-xs text-muted-foreground italic">{note}</div>}
              </div>
            </div>
            {badge && (
              <span className="text-xs font-semibold text-muted-foreground bg-secondary px-2 py-1 rounded-full shrink-0">
                {badge}
              </span>
            )}
          </button>
        );
      })}
      {only && onlyNote && <p className="text-xs text-muted-foreground">{onlyNote}</p>}
    </div>
  );
}

export default PaymentMethodList;
