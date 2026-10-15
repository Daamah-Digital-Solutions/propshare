/**
 * The unit movements list and its statement (client, 2026-10-15): the wallet had a statement
 * of its money, the units had none. "Download statement" opens the same period form as the
 * wallet's and downloads the unit statement as PDF or Excel.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { api, save } = vi.hoisted(() => ({
  api: { movements: vi.fn(), downloadMovementsStatement: vi.fn() },
  save: vi.fn(),
}));

vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return { ...real, investApi: api, walletApi: { downloadStatement: vi.fn() } };
});
vi.mock("@/lib/certificates", () => ({ saveBlob: save }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { UnitMovements } from "./UnitMovements";

const MOVE = {
  id: "m1",
  at: "2026-10-01T10:00:00Z",
  property_id: "p1",
  property_title: "Marina Heights",
  units: 5,
  direction: "in",
  reason: "purchase",
  label: "Purchase",
  counterparty: null,
};

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UnitMovements />
    </QueryClientProvider>,
  );
}

describe("UnitMovements", () => {
  beforeEach(() => {
    api.movements.mockReset();
    api.downloadMovementsStatement.mockReset();
    save.mockReset();
    api.movements.mockResolvedValue({ items: [MOVE], total: 1 });
    api.downloadMovementsStatement.mockResolvedValue(new Blob(["%PDF"]));
  });

  it("downloads a statement of the unit movements for a chosen period", async () => {
    mount();
    await screen.findByText("Marina Heights", { exact: false });
    expect(screen.queryByTestId("unit-statement")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Download statement/ }));
    const box = screen.getByTestId("unit-statement");
    expect(box).toHaveTextContent(/units held in each property/);
    fireEvent.change(within(box).getByLabelText("From"), { target: { value: "2026-09-01" } });
    fireEvent.change(within(box).getByLabelText("To"), { target: { value: "2026-09-30" } });

    fireEvent.click(within(box).getByRole("button", { name: /Download PDF/ }));
    await waitFor(() =>
      expect(api.downloadMovementsStatement).toHaveBeenCalledWith("2026-09-01", "2026-09-30", "pdf"),
    );
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith(expect.any(Blob), "capimax-unit-statement-2026-09-01-to-2026-09-30.pdf"),
    );

    fireEvent.click(within(box).getByRole("button", { name: /Download Excel/ }));
    await waitFor(() =>
      expect(api.downloadMovementsStatement).toHaveBeenLastCalledWith("2026-09-01", "2026-09-30", "xlsx"),
    );
  });

  it("does not ask the server for an impossible period", async () => {
    mount();
    await screen.findByText("Marina Heights", { exact: false });
    fireEvent.click(screen.getByRole("button", { name: /Download statement/ }));
    const box = screen.getByTestId("unit-statement");
    fireEvent.change(within(box).getByLabelText("From"), { target: { value: "2026-09-30" } });
    fireEvent.change(within(box).getByLabelText("To"), { target: { value: "2026-09-01" } });
    expect(within(box).getByRole("alert")).toHaveTextContent("The start date must be on or before the end date.");
    expect(within(box).getByRole("button", { name: /Download PDF/ })).toBeDisabled();
  });
});
