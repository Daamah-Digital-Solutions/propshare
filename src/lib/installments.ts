/**
 * The platform's standard installment plans. MUST mirror
 * backend/app/services/installment_service.py `_DOWN_PCT` — the server rejects any other
 * duration and computes the down payment from this table. Installment terms are
 * platform-wide, not per property (owner decision).
 */
export const INSTALLMENT_DURATIONS = [
  { value: "6", label: "6 Months", months: 6, downPaymentPercent: 30 },
  { value: "12", label: "12 Months", months: 12, downPaymentPercent: 25 },
  { value: "18", label: "18 Months", months: 18, downPaymentPercent: 20 },
  { value: "24", label: "24 Months", months: 24, downPaymentPercent: 15 },
] as const;
