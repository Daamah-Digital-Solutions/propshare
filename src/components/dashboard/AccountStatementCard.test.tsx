/**
 * Account statement card: picks a period, downloads PDF or Excel through the authenticated
 * API, refuses impossible periods before calling the server, and shows the server's own
 * message when it refuses one.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { download, save, toastError, state } = vi.hoisted(() => ({
  download: vi.fn(),
  save: vi.fn(),
  toastError: vi.fn(),
  state: { fail: false },
}));

vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown> & { ApiError: new (...a: unknown[]) => Error };
  return {
    ...real,
    walletApi: {
      downloadStatement: (...args: unknown[]) => {
        download(...args);
        if (state.fail) {
          return { then: (_ok: unknown, bad: (e: Error) => void) => bad(new real.ApiError("PERIOD_TOO_LONG", "Server says: shorter period please.", 422)) };
        }
        return Promise.resolve(new Blob(["%PDF"]));
      },
    },
  };
});
vi.mock("@/lib/certificates", () => ({ saveBlob: save }));
vi.mock("sonner", () => ({ toast: { error: toastError, success: vi.fn() } }));

import { AccountStatementCard, validatePeriod } from "./AccountStatementCard";

describe("AccountStatementCard", () => {
  beforeEach(() => {
    download.mockReset();
    save.mockReset();
    toastError.mockReset();
    state.fail = false;
  });

  it("downloads the chosen period as PDF and as Excel", async () => {
    render(<AccountStatementCard />);
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-02-01" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-03-02" } });

    fireEvent.click(screen.getByRole("button", { name: /download pdf/i }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(download).toHaveBeenCalledWith("2026-02-01", "2026-03-02", "pdf");
    expect(save.mock.calls[0][1]).toBe("capimax-statement-2026-02-01-to-2026-03-02.pdf");

    fireEvent.click(screen.getByRole("button", { name: /download excel/i }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(download).toHaveBeenLastCalledWith("2026-02-01", "2026-03-02", "xlsx");
    expect(save.mock.calls[1][1]).toBe("capimax-statement-2026-02-01-to-2026-03-02.xlsx");
  });

  it("refuses an impossible period without calling the server", () => {
    render(<AccountStatementCard />);
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-03-02" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-02-01" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/start date must be on or before/i);
    const pdf = screen.getByRole("button", { name: /download pdf/i });
    expect(pdf).toBeDisabled();
    fireEvent.click(pdf);
    expect(download).not.toHaveBeenCalled();
  });

  it("shows the server's message when it refuses", async () => {
    state.fail = true;
    render(<AccountStatementCard />);
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-01-31" } });
    fireEvent.click(screen.getByRole("button", { name: /download pdf/i }));
    await waitFor(() => expect(toastError).toHaveBeenCalledWith("Server says: shorter period please."));
    expect(save).not.toHaveBeenCalled();
  });

  it("presets fill a valid period ending today at the latest", () => {
    render(<AccountStatementCard />);
    for (const name of ["This month", "Last month", "Last 3 months", "This year"]) {
      fireEvent.click(screen.getByRole("button", { name }));
      const from = (screen.getByLabelText("From") as HTMLInputElement).value;
      const to = (screen.getByLabelText("To") as HTMLInputElement).value;
      expect(validatePeriod(from, to), name).toBeNull();
    }
  });

  it("validates the three-year cap and future dates", () => {
    expect(validatePeriod("2020-01-01", "2024-01-01", "2026-09-23")).toMatch(/three years/);
    expect(validatePeriod("2026-09-01", "2026-09-24", "2026-09-23")).toMatch(/future/);
    expect(validatePeriod("2023-09-24", "2026-09-23", "2026-09-23")).toBeNull();
  });
});
