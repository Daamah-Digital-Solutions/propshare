/**
 * Prepared cards (owner: "help to the furthest limit, stop at the user's confirmation"):
 * a deposit or withdrawal card opens the wallet with everything filled in and says nothing
 * moves before the user's own click there; a statement card downloads the file from the chat.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { DepositCard, StatementCard, WithdrawalCard } from "@/lib/assistantApi";

const { download, save } = vi.hoisted(() => ({ download: vi.fn(), save: vi.fn() }));
vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return { ...real, walletApi: { downloadStatement: (...a: unknown[]) => download(...a) } };
});
vi.mock("@/lib/certificates", () => ({ saveBlob: (...a: unknown[]) => save(...a) }));

import { ApiError } from "@/lib/api";
import { AssistantCardView } from "./AssistantCards";

const show = (card: DepositCard | WithdrawalCard | StatementCard) =>
  render(
    <MemoryRouter>
      <AssistantCardView card={card} />
    </MemoryRouter>,
  );

const deposit: DepositCard = {
  kind: "deposit",
  amount: "5000.00",
  currency: "USD",
  method: "card",
  method_label: "Card",
  notes: [],
  ready: true,
  path: "/dashboard?tab=wallet&action=deposit&amount=5000.00&method=card",
};

const withdrawal: WithdrawalCard = {
  kind: "withdrawal",
  amount: "1000.00",
  currency: "USD",
  method: "bank",
  speed: "instant",
  fee: "15.00",
  net_amount: "985.00",
  destination: "Your linked bank account",
  timing: "Sent at once; usually arrives within 30 minutes.",
  notes: [],
  ready: true,
  path: "/dashboard?tab=wallet&action=withdraw&amount=1000.00&method=bank&speed=instant",
};

const statement: StatementCard = {
  kind: "statement",
  start: "2026-07-01",
  end: "2026-08-31",
  format: "pdf",
  movements: 2,
  currency: "USD",
  opening_balance: "1000.00",
  closing_balance: "612.50",
  money_in: "12.50",
  money_out: "400.00",
  path: "/dashboard?tab=wallet",
};

describe("prepared cards", () => {
  beforeEach(() => {
    download.mockReset();
    save.mockReset();
  });

  it("a deposit opens the wallet filled in; nothing is charged before the user confirms", () => {
    show(deposit);
    const card = screen.getByTestId("deposit-card");
    expect(card).toHaveTextContent("Your deposit is ready");
    expect(card).toHaveTextContent("You add$5,000.00");
    expect(card).toHaveTextContent(/nothing is charged until you confirm/i);
    expect(screen.getByRole("link", { name: /continue to payment/i })).toHaveAttribute("href", deposit.path);
  });

  it("a deposit that needs a step first says so and only opens the wallet", () => {
    show({ ...deposit, method: "bank", method_label: "Bank transfer", ready: false, notes: ["Complete identity verification first."] });
    const card = screen.getByTestId("deposit-card");
    expect(card).toHaveTextContent("Deposit prepared: one step first");
    expect(card).toHaveTextContent("Complete identity verification first.");
    expect(screen.getByRole("link", { name: /open wallet/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /continue to/i })).toBeNull();
  });

  it("a withdrawal shows speed, fee and what arrives before anything is sent", () => {
    show(withdrawal);
    const card = screen.getByTestId("withdrawal-card");
    expect(card).toHaveTextContent("SpeedInstant (minutes)");
    expect(card).toHaveTextContent("Fee$15.00");
    expect(card).toHaveTextContent("You receive$985.00");
    expect(card).toHaveTextContent("ToYour linked bank account");
    expect(card).toHaveTextContent(/nothing is sent until you confirm/i);
    expect(screen.getByRole("link", { name: /review & withdraw/i })).toHaveAttribute("href", withdrawal.path);
  });

  it("a standard withdrawal is free", () => {
    show({ ...withdrawal, speed: "standard", fee: "0.00", net_amount: "1000.00" });
    expect(screen.getByTestId("withdrawal-card")).toHaveTextContent("FeeFree");
  });

  it("a statement downloads straight from the chat, in the format asked first", async () => {
    const blob = new Blob(["%PDF"]);
    download.mockResolvedValue(blob);
    show(statement);
    const card = screen.getByTestId("statement-card");
    expect(card).toHaveTextContent("Period1 Jul 2026 – 31 Aug 2026");
    expect(card).toHaveTextContent("Closing balance$612.50");
    const buttons = screen.getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(["Download PDF", "Download Excel"]);
    fireEvent.click(screen.getByRole("button", { name: /download pdf/i }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(blob, "capimax-statement-2026-07-01-to-2026-08-31.pdf"));
    expect(download).toHaveBeenCalledWith("2026-07-01", "2026-08-31", "pdf");
  });

  it("a failed download says why, in the card", async () => {
    download.mockRejectedValue(new ApiError("PERIOD_TOO_LONG", "Please choose a shorter period.", 422));
    show({ ...statement, format: "xlsx" });
    expect(screen.getAllByRole("button")[0]).toHaveTextContent("Download Excel");
    fireEvent.click(screen.getByRole("button", { name: /download excel/i }));
    expect(await screen.findByText("Please choose a shorter period.")).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
  });
});
