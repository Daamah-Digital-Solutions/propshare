/**
 * Transfers (client, 2026-10-28, as on Capimax BRX): the tab lists every transfer with its TR-
 * number and status, counts and filters them, and cancels one not delivered (after a confirm);
 * the dialog goes form -> review (priced by the server) -> confirm, sending once with one key.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { api, auth } = vi.hoisted(() => ({
  api: { list: vi.fn(), options: vi.fn(), quote: vi.fn(), send: vi.fn(), cancel: vi.fn() },
  auth: { user: { email_verified: true, kyc_status: "verified" } as Record<string, unknown> },
}));

vi.mock("@/lib/api", () => ({
  transfersApi: api,
  ApiError: class ApiError extends Error {
    code: string;
    status: number;
    constructor(code: string, message: string, status: number) {
      super(message);
      this.code = code;
      this.status = status;
    }
  },
}));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { TransfersTab } from "./TransfersTab";
import { ApiError } from "@/lib/api";

const row = (over: Record<string, unknown>) => ({
  id: "t1",
  reference: "TR-ABCDEFGH23",
  direction: "sent",
  counterparty: "Bassel",
  recipient_email: "bassel@x.com",
  asset: "balance",
  property_id: null,
  property_title: null,
  units: null,
  unit_price: null,
  amount: "120.00",
  fee: "0.00",
  message: null,
  deliver_on: "2026-10-28",
  status: "delivered",
  status_label: "Delivered",
  expires_at: null,
  delivered_at: "2026-10-28T10:00:00Z",
  closed_reason: null,
  created_at: "2026-10-28T10:00:00Z",
  can_cancel: false,
  ...over,
});

const OPTIONS = {
  positions: [
    { property_id: "p1", property_title: "Marina Loft", units: 10, free_units: 6, unit_price: "100.00" },
  ],
  balance: "500.00",
  fee_pct: "0",
  claim_days: 30,
  max_days_ahead: 365,
};

function mount(path = "/dashboard?tab=transfers") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <TransfersTab />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TransfersTab", () => {
  beforeEach(() => {
    Object.values(api).forEach((f) => f.mockReset());
    auth.user = { email_verified: true, kyc_status: "verified" };
    api.options.mockResolvedValue(OPTIONS);
  });

  it("lists, counts and filters transfers by direction and status", async () => {
    api.list.mockResolvedValue({
      items: [
        row({}),
        row({
          id: "t2",
          reference: "TR-WAIT234567",
          status: "waiting",
          status_label: "Waiting for the recipient",
          expires_at: "2026-11-27T10:00:00Z",
          can_cancel: true,
          asset: "units",
          units: 3,
          property_title: "Marina Loft",
          message: "Happy birthday",
        }),
        row({ id: "t3", reference: "TR-RECEIVED23", direction: "received", counterparty: "Amira", recipient_email: null }),
      ],
    });
    mount();
    await waitFor(() => expect(screen.getAllByTestId("transfer-row")).toHaveLength(3));
    expect(screen.getByTestId("count-sent")).toHaveTextContent("2");
    expect(screen.getByTestId("count-received")).toHaveTextContent("1");
    expect(screen.getByTestId("count-waiting")).toHaveTextContent("1");
    const list = screen.getByTestId("transfer-list");
    expect(list).toHaveTextContent("TR-WAIT234567");
    expect(list).toHaveTextContent("3 units · Marina Loft");
    expect(list).toHaveTextContent("Must be received by Nov 27, 2026");
    expect(list).toHaveTextContent("“Happy birthday”");
    expect(list).toHaveTextContent("From Amira");

    fireEvent.click(screen.getByRole("tab", { name: /waiting/i }));
    expect(screen.getAllByTestId("transfer-row")).toHaveLength(1);
    fireEvent.click(screen.getByRole("tab", { name: /received/i }));
    expect(screen.getByTestId("transfer-list")).toHaveTextContent("TR-RECEIVED23");
  });

  it("cancels a transfer only after the member confirms", async () => {
    api.list.mockResolvedValue({
      items: [row({ status: "waiting", status_label: "Waiting", can_cancel: true, fee: "1.20" })],
    });
    api.cancel.mockResolvedValue(row({ status: "cancelled" }));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Cancel TR-ABCDEFGH23" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("The amount goes back to your wallet, with the fee.");
    expect(api.cancel).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel transfer" }));
    await waitFor(() => expect(api.cancel).toHaveBeenCalledWith("t1"));
  });

  it("asks an unverified member to verify before sending", async () => {
    auth.user = { email_verified: true, kyc_status: "pending" };
    api.list.mockResolvedValue({ items: [] });
    mount();
    expect(await screen.findByRole("link", { name: /verify my identity/i })).toHaveAttribute("href", "/kyc");
    expect(screen.queryByRole("button", { name: /transfer units/i })).toBeNull();
  });

  it("sends after a review the server priced, with one key per confirmation", async () => {
    api.list.mockResolvedValue({ items: [] });
    api.quote.mockResolvedValue({
      asset: "units",
      recipient_email: "bassel@x.com",
      recipient_name: "Bassel",
      property_id: "p1",
      property_title: "Marina Loft",
      units: 4,
      unit_price: "100.00",
      amount: "400.00",
      fee: "8.00",
      fee_pct: "2",
      charged: "8.00",
      deliver_on: new Date().toISOString().slice(0, 10),
      message: null,
      claim_days: 30,
    });
    api.send.mockResolvedValue(
      row({ reference: "TR-NEW2345678", status: "waiting", status_label: "Waiting", counterparty: "Bassel" }),
    );
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /transfer units/i }));
    const dialog = await screen.findByTestId("transfer-dialog");
    await waitFor(() => expect(within(dialog).getByText(/6 of your 10 units can be sent/)).toBeInTheDocument());
    const review = within(dialog).getByRole("button", { name: /review transfer/i });
    expect(review).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Units"), { target: { value: "7" } });
    fireEvent.change(within(dialog).getByLabelText("Recipient email"), { target: { value: "bassel@x.com" } });
    expect(review).toBeDisabled(); // more than the 6 free units
    fireEvent.change(within(dialog).getByLabelText("Units"), { target: { value: "4" } });
    fireEvent.change(within(dialog).getByLabelText("Recipient name (optional)"), { target: { value: "Bassel" } });
    expect(review).toBeEnabled();
    fireEvent.click(review);

    const summary = await screen.findByTestId("transfer-review");
    expect(api.quote).toHaveBeenCalledWith(
      expect.objectContaining({ asset: "units", property_id: "p1", units: 4, recipient_email: "bassel@x.com" }),
    );
    expect(summary).toHaveTextContent("4 units of Marina Loft");
    expect(summary).toHaveTextContent("$8.00 (2%)");
    expect(summary).toHaveTextContent("From your wallet now$8.00");
    expect(api.send).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /confirm and send/i }));
    expect(await screen.findByTestId("transfer-reference")).toHaveTextContent("TR-NEW2345678");
    expect(screen.getByTestId("transfer-result")).toHaveTextContent("Waiting for Bassel");
    expect(api.send).toHaveBeenCalledTimes(1);
    // the amount the review showed travels with the send: the server refuses if it changed
    expect(api.send.mock.calls[0][0]).toEqual(expect.objectContaining({ expected_charged: "8.00" }));
    const key = api.send.mock.calls[0][1];
    expect(typeof key).toBe("string");
    expect(key.length).toBeGreaterThan(10);
  });

  it("shows why the server refused it, and sends nothing", async () => {
    api.list.mockResolvedValue({ items: [] });
    api.quote.mockRejectedValue(
      new ApiError("INSUFFICIENT_FUNDS", "Your wallet balance is $500.00; this needs $900.00.", 422),
    );
    mount("/dashboard?tab=transfers&new=balance");
    const dialog = await screen.findByTestId("transfer-dialog");
    fireEvent.change(within(dialog).getByLabelText("Amount (USD)"), { target: { value: "900" } });
    fireEvent.change(within(dialog).getByLabelText("Recipient email"), { target: { value: "b@x.com" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /review transfer/i }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("this needs $900.00");
    expect(api.send).not.toHaveBeenCalled();
  });
});
