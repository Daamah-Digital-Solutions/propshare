import { Bitcoin, Coins, CreditCard, FileText, Smartphone, Wallet } from "lucide-react";
import type { LucideIcon } from "lucide-react";

/**
 * The ways to pay for a property — ONE list, the same on every property and every property
 * type (client feedback 2026-09-27, the Capimax BRX concept). Both purchase panels (a ready
 * property and an installment plan's down payment) render exactly this list, in this order;
 * a method whose provider is not set up is shown as unavailable, never dropped.
 *
 * Card, Apple Pay, Google Pay and Pronova all pay on Stripe's secure checkout (the wallets
 * show there on devices that support them); crypto on NOWPayments' page; a Nova Sukuk
 * certificate is reviewed by our team; the wallet pays at once.
 */
export type PayMethodId =
  | "wallet"
  | "card"
  | "apple_pay"
  | "google_pay"
  | "crypto"
  | "pronova"
  | "sukuk";

/** What the server is sent: Apple / Google Pay are card payments on Stripe's checkout. */
export type PayApiMethod = "wallet" | "card" | "crypto" | "pronova" | "sukuk";

export interface PayMethod {
  id: PayMethodId;
  label: string;
  description: string;
  icon: LucideIcon;
  apiMethod: PayApiMethod;
  badge?: string;
}

export const PAYMENT_METHODS: readonly PayMethod[] = [
  {
    id: "wallet",
    label: "Wallet Balance",
    description: "Pay at once from your Capimax wallet",
    icon: Wallet,
    apiMethod: "wallet",
  },
  {
    id: "card",
    label: "Credit / Debit Card",
    description: "Visa, Mastercard, Amex — on Stripe's secure page",
    icon: CreditCard,
    apiMethod: "card",
  },
  {
    id: "apple_pay",
    label: "Apple Pay",
    description: "On iPhone, iPad or Mac with Safari",
    icon: Smartphone,
    apiMethod: "card",
  },
  {
    id: "google_pay",
    label: "Google Pay",
    description: "On Android or Chrome",
    icon: Smartphone,
    apiMethod: "card",
  },
  {
    id: "crypto",
    label: "Cryptocurrency",
    description: "USDT, USDC, BTC, ETH and more: choose your coin here, pay on NOWPayments' page",
    icon: Bitcoin,
    apiMethod: "crypto",
  },
  {
    id: "pronova",
    label: "Pronova Token",
    description: "A discount on everything you pay now",
    icon: Coins,
    apiMethod: "pronova",
    badge: "OFF",
  },
  {
    id: "sukuk",
    label: "Nova Sukuk",
    description: "Sharia-compliant financing — pay with your Nova certificate",
    icon: FileText,
    apiMethod: "sukuk",
    badge: "Financing",
  },
];

/** Which methods are live right now (GET /investments/payment-options). */
export interface PaymentOptions {
  wallet: boolean;
  card: boolean;
  apple_pay: boolean;
  google_pay: boolean;
  crypto: boolean;
  pronova: boolean;
  sukuk: boolean;
  pronova_discount_pct: string;
}

export function payMethod(id: string): PayMethod {
  return PAYMENT_METHODS.find((m) => m.id === id) ?? PAYMENT_METHODS[0];
}

/** Apple Pay only exists in Safari on Apple devices with a card in Wallet. */
export function applePayOnThisDevice(): boolean {
  try {
    const session = (window as unknown as { ApplePaySession?: { canMakePayments?: () => boolean } })
      .ApplePaySession;
    return Boolean(session?.canMakePayments?.());
  } catch {
    return false;
  }
}
