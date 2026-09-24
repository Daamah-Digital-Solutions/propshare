/**
 * "Add card" opens Stripe's own secure form (Payment Element on a SetupIntent). The card number
 * goes from Stripe's form to Stripe; our API only receives the finished SetupIntent id and reads
 * the card from Stripe itself. A card that needs the bank's check comes back to the wallet with
 * setup_intent in the URL, and the wallet finishes the save once.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { api, stripe, toast } = vi.hoisted(() => ({
  api: { setupIntent: vi.fn(), add: vi.fn(), list: vi.fn() },
  stripe: { confirmSetup: vi.fn(), loadStripe: vi.fn() },
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock("@stripe/stripe-js", () => ({
  loadStripe: (...a: unknown[]) => stripe.loadStripe(...a),
}));
vi.mock("@stripe/react-stripe-js", async () => {
  const { useEffect } = await import("react");
  return {
    Elements: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    PaymentElement: ({ onReady }: { onReady?: () => void }) => {
      useEffect(() => onReady?.(), [onReady]);
      return <div data-testid="stripe-card-form" />;
    },
    useStripe: () => ({ confirmSetup: stripe.confirmSetup }),
    useElements: () => ({}),
  };
});
vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    code: string;
    status: number;
    constructor(code: string, message: string, status: number) {
      super(message);
      this.code = code;
      this.status = status;
    }
  },
  walletApi: {
    getMe: async () => ({ balance: "0.00", pending_balance: "0.00", currency: "USD" }),
    transactions: async () => ({ items: [], total: 0 }),
    depositMethods: async () => ({ card: true, crypto: true, bank: false }),
  },
  withdrawApi: { create: vi.fn() },
  paymentMethodsApi: {
    list: (...a: unknown[]) => api.list(...a),
    setupIntent: (...a: unknown[]) => api.setupIntent(...a),
    add: (...a: unknown[]) => api.add(...a),
    remove: vi.fn(),
    setDefault: vi.fn(),
  },
  bankAccountsApi: { list: async () => [], create: vi.fn(), remove: vi.fn(), setDefault: vi.fn() },
  cryptoWalletsApi: { list: async () => [], create: vi.fn(), remove: vi.fn(), setDefault: vi.fn() },
  bankDepositApi: { platformAccounts: async () => [], claim: vi.fn() },
  payoutConfigApi: {
    get: async () => ({
      auto_approve_limit: "5000",
      methods: {
        bank: { mode: "manual", connect_required: false, requested_auto: false, provider_configured: false },
        crypto: { mode: "manual", connect_required: false, requested_auto: false, provider_configured: false },
      },
    }),
  },
  connectApi: { status: vi.fn(), onboard: vi.fn() },
}));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/components/exit/ExitButton", () => ({ ExitButton: () => <button>exit</button> }));

import { ApiError } from "@/lib/api";
import { InvestorWallet } from "./InvestorWallet";

function Url() {
  const l = useLocation();
  return <div data-testid="url">{l.pathname + l.search}</div>;
}

function mount(url = "/dashboard?tab=wallet") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <InvestorWallet />
        <Url />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Add card — Stripe's secure form", () => {
  beforeEach(() => {
    Object.values(api).forEach((f) => f.mockReset());
    Object.values(stripe).forEach((f) => f.mockReset());
    Object.values(toast).forEach((f) => f.mockReset());
    api.list.mockResolvedValue([]);
    stripe.loadStripe.mockResolvedValue({});
  });

  // Stripe.js is cached per publishable key for the page's lifetime, so each test uses its own.
  function startsSetup(publishableKey: string, clientSecret = "seti_123_secret_abc") {
    api.setupIntent.mockResolvedValue({ client_secret: clientSecret, publishable_key: publishableKey });
  }

  it("opens Stripe's form and saves the card the finished setup produced", async () => {
    startsSetup("pk_test_one");
    stripe.confirmSetup.mockResolvedValue({ setupIntent: { id: "seti_123", status: "succeeded" } });
    api.add.mockResolvedValue({ id: "m1" });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /add card/i }));

    expect(await screen.findByTestId("stripe-card-form")).toBeInTheDocument();
    expect(stripe.loadStripe).toHaveBeenCalledWith("pk_test_one");
    fireEvent.click(screen.getByRole("button", { name: /save card/i }));

    await waitFor(() => expect(api.add).toHaveBeenCalledWith("seti_123"));
    const call = stripe.confirmSetup.mock.calls[0][0];
    expect(call.redirect).toBe("if_required");
    // back to the dashboard the card was added from
    expect(call.confirmParams.return_url).toMatch(/\/dashboard\?tab=wallet$/);
    // the server marks the card for Checkout only once it is recorded, not the browser
    expect(call.confirmParams.payment_method_data).toBeUndefined();
    expect(toast.success).toHaveBeenCalledWith("Card saved");
  });

  it("retries only our side when recording the card failed after Stripe saved it", async () => {
    startsSetup("pk_test_retry");
    stripe.confirmSetup.mockResolvedValue({ setupIntent: { id: "seti_77", status: "succeeded" } });
    api.add.mockRejectedValueOnce(new ApiError("PAYMENT_PROVIDER_ERROR", "Stripe error (502).", 502));
    api.add.mockResolvedValueOnce({ id: "m1" });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /add card/i }));
    fireEvent.click(await screen.findByRole("button", { name: /save card/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Stripe error (502).");
    fireEvent.click(await screen.findByRole("button", { name: /try again/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Card saved"));
    expect(stripe.confirmSetup).toHaveBeenCalledTimes(1); // the card is not confirmed twice
    expect(api.add).toHaveBeenNthCalledWith(2, "seti_77");
  });

  it("treats a setup Stripe already finished as saved", async () => {
    startsSetup("pk_test_done");
    stripe.confirmSetup.mockResolvedValue({
      error: {
        code: "setup_intent_unexpected_state",
        message: "You cannot confirm this SetupIntent because it has already succeeded.",
        setup_intent: { id: "seti_55", status: "succeeded" },
      },
    });
    api.add.mockResolvedValue({ id: "m1" });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /add card/i }));
    fireEvent.click(await screen.findByRole("button", { name: /save card/i }));

    await waitFor(() => expect(api.add).toHaveBeenCalledWith("seti_55"));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says so when Stripe's form cannot load, and tries again next time", async () => {
    startsSetup("pk_test_blocked");
    stripe.loadStripe.mockRejectedValueOnce(new Error("Failed to load Stripe.js"));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /add card/i }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/could not load/i)),
    );
    expect(screen.queryByTestId("stripe-card-form")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /add card/i }));
    expect(await screen.findByTestId("stripe-card-form")).toBeInTheDocument();
    expect(stripe.loadStripe).toHaveBeenCalledTimes(2);
  });

  it("does not close while the card is being saved", async () => {
    startsSetup("pk_test_busy");
    stripe.confirmSetup.mockResolvedValue({ setupIntent: { id: "seti_66", status: "succeeded" } });
    api.add.mockReturnValue(new Promise(() => {})); // still waiting on the server
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /add card/i }));
    fireEvent.click(await screen.findByRole("button", { name: /save card/i }));
    await screen.findByRole("button", { name: /saving/i });

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows Stripe's message and saves nothing when the card is refused", async () => {
    startsSetup("pk_test_refused");
    stripe.confirmSetup.mockResolvedValue({ error: { message: "Your card was declined." } });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /add card/i }));
    fireEvent.click(await screen.findByRole("button", { name: /save card/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Your card was declined.");
    expect(api.add).not.toHaveBeenCalled();
  });

  it("says honestly when saving cards is not available, instead of an empty form", async () => {
    api.setupIntent.mockRejectedValue(new ApiError("PAYMENTS_NOT_CONFIGURED", "Saving cards is not available yet.", 503));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /add card/i }));

    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith("Saving cards isn't available yet", expect.anything()),
    );
    expect(screen.queryByTestId("stripe-card-form")).toBeNull();
  });

  it("finishes a save once after the bank's check and cleans the URL", async () => {
    api.add.mockResolvedValue({ id: "m1" });
    mount(
      "/dashboard?tab=wallet&setup_intent=seti_9&setup_intent_client_secret=seti_9_secret",
    );

    await waitFor(() => expect(api.add).toHaveBeenCalledWith("seti_9"));
    await waitFor(() => expect(screen.getByTestId("url")).toHaveTextContent("/dashboard?tab=wallet"));
    expect(screen.getByTestId("url").textContent).not.toMatch(/setup_intent|redirect_status/);
    expect(api.add).toHaveBeenCalledTimes(1);
  });

  it("leaves the verdict on a failed bank check to the server, and shows its answer", async () => {
    api.add.mockRejectedValue(
      new ApiError("CARD_SETUP_INCOMPLETE", "The card was not saved: its setup did not finish.", 409),
    );
    mount("/dashboard?tab=wallet&setup_intent=seti_8&setup_intent_client_secret=seti_8_secret");

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("The card was not saved: its setup did not finish."),
    );
    expect(api.add).toHaveBeenCalledWith("seti_8");
    expect(toast.success).not.toHaveBeenCalled();
    expect(screen.getByTestId("url").textContent).not.toMatch(/setup_intent/);
  });
});
