/**
 * Back from the hosted checkout (?deposit=success&payment=<id>): the page follows the payment
 * until the server settles it, then refreshes the balance; the parameters are consumed.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { api, toast } = vi.hoisted(() => ({
  api: { get: vi.fn() },
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock("@/lib/api", () => ({ paymentApi: { get: (...a: unknown[]) => api.get(...a) } }));
vi.mock("sonner", () => ({ toast }));

import { PaymentReturnStatus } from "./PaymentReturnStatus";

function Url() {
  const l = useLocation();
  return <div data-testid="url">{l.pathname + l.search}</div>;
}

const payment = (status: string) => ({
  id: "p1",
  provider: "stripe",
  status,
  amount: "50.00",
  amount_captured: status === "succeeded" ? "50.00" : null,
  created_at: "2026-09-27T10:00:00Z",
});

function mount(url: string, kind: "deposit" | "invest" = "deposit", timeoutMs = 120_000) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(qc, "invalidateQueries");
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <PaymentReturnStatus kind={kind} pollMs={10} timeoutMs={timeoutMs} />
        <Url />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { invalidate };
}

describe("PaymentReturnStatus", () => {
  beforeEach(() => {
    api.get.mockReset();
    toast.success.mockReset();
    toast.error.mockReset();
    toast.info.mockReset();
    sessionStorage.clear();
  });

  it("renders nothing when the page was not reached from a checkout", () => {
    mount("/dashboard?tab=wallet");
    expect(screen.queryByTestId("payment-return")).toBeNull();
    expect(api.get).not.toHaveBeenCalled();
  });

  it("follows a pending deposit until it is credited, then refreshes the wallet", async () => {
    api.get.mockResolvedValueOnce(payment("pending")).mockResolvedValue(payment("succeeded"));
    const { invalidate } = mount("/dashboard?tab=wallet&deposit=success&payment=p1");
    expect(await screen.findByTestId("payment-return")).toHaveTextContent(/crediting your wallet/i);
    await waitFor(() => expect(screen.getByTestId("payment-return")).toHaveTextContent(/Deposit credited/));
    expect(api.get).toHaveBeenCalledWith("p1");
    expect(toast.success).toHaveBeenCalledTimes(1);
    const keys = invalidate.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));
    expect(keys).toEqual(expect.arrayContaining(['["wallet"]', '["wallet-transactions"]', '["holdings"]']));
    // consumed: a refresh or Back does not restart it
    expect(screen.getByTestId("url").textContent).toBe("/dashboard?tab=wallet");
  });

  it("says so when the provider reports the payment failed", async () => {
    api.get.mockResolvedValue(payment("failed"));
    mount("/dashboard?tab=investments&invest=success&payment=p1", "invest");
    await waitFor(() => expect(screen.getByTestId("payment-return")).toHaveTextContent(/not completed/i));
    expect(toast.error).toHaveBeenCalledTimes(1);
  });

  it("stops asking after the timeout and promises a notification instead", async () => {
    api.get.mockResolvedValue(payment("pending"));
    mount("/dashboard?tab=wallet&deposit=success&payment=p1", "deposit", 0);
    await waitFor(() => expect(screen.getByTestId("payment-return")).toHaveTextContent(/Still confirming/));
    expect(screen.getByTestId("payment-return")).toHaveTextContent(/no need to pay again/i);
  });

  it("falls back to the remembered payment when the provider drops the query string", async () => {
    sessionStorage.setItem("capimax.pending_payment", "p1");
    api.get.mockResolvedValue(payment("succeeded"));
    mount("/dashboard?tab=wallet&deposit=success");
    await waitFor(() => expect(screen.getByTestId("payment-return")).toHaveTextContent(/Deposit credited/));
    expect(api.get).toHaveBeenCalledWith("p1");
    expect(sessionStorage.getItem("capimax.pending_payment")).toBeNull();
  });

  it("tells the member a cancelled checkout charged nothing", async () => {
    mount("/dashboard?tab=wallet&deposit=cancelled&payment=p1");
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith(expect.stringMatching(/nothing was charged/i)));
    expect(screen.queryByTestId("payment-return")).toBeNull();
    expect(api.get).not.toHaveBeenCalled();
    expect(screen.getByTestId("url").textContent).toBe("/dashboard?tab=wallet");
  });
});
