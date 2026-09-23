/**
 * Account Settings → Two-Factor Authentication. Replaces the disabled "Not available yet"
 * row: enrol with a QR code + first code, recovery codes shown once and acknowledged,
 * turn off with password + code (code only for Google accounts).
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { api } = vi.hoisted(() => ({
  api: {
    status: vi.fn(),
    setup: vi.fn(),
    enable: vi.fn(),
    disable: vi.fn(),
    regenerateRecoveryCodes: vi.fn(),
  },
}));

vi.mock("@/lib/api", () => ({
  ApiError: class extends Error {},
  mfaApi: api,
}));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

import { TwoFactorSettings } from "./TwoFactorSettings";

const OFF = {
  has_password: true,
  enabled: false,
  enabled_at: null,
  recovery_codes_remaining: 0,
  available: true,
};
const ON = { ...OFF, enabled: true, enabled_at: "2026-09-23T10:00:00Z", recovery_codes_remaining: 10 };
const CODES = Array.from({ length: 10 }, (_, i) => `AAAA-BBBB-CCCC-DD${String(i).padStart(2, "0")}`);

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TwoFactorSettings />
    </QueryClientProvider>,
  );
}

describe("TwoFactorSettings", () => {
  beforeEach(() => Object.values(api).forEach((m) => m.mockReset()));

  it("enrols: QR + key, first code, then recovery codes that must be acknowledged", async () => {
    api.status.mockResolvedValue(OFF);
    api.setup.mockResolvedValue({
      secret: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
      otpauth_uri: "otpauth://totp/x",
      qr_svg_data_uri: "data:image/svg+xml;base64,PHN2Zy8+",
      expires_in: 1800,
    });
    api.enable.mockResolvedValue({ recovery_codes: CODES });
    mount();

    fireEvent.click(await screen.findByRole("button", { name: /turn on/i }));
    expect(await screen.findByTestId("mfa-qr")).toHaveAttribute("src", "data:image/svg+xml;base64,PHN2Zy8+");
    expect(screen.getByTestId("mfa-secret")).toHaveTextContent("JBSW Y3DP");

    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByRole("textbox", { name: /authentication code/i }), {
      target: { value: "123456" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: /^turn on$/i }));
    await waitFor(() => expect(api.enable).toHaveBeenCalledWith("123456"));

    const list = await screen.findByTestId("recovery-codes");
    expect(list).toHaveTextContent(CODES[0]);
    expect(list).toHaveTextContent(CODES[9]);
    const done = within(list).getByRole("button", { name: /done/i });
    expect(done).toBeDisabled(); // not until the user confirms they saved them
    fireEvent.click(within(list).getByRole("checkbox", { name: /saved my recovery codes/i }));
    expect(done).not.toBeDisabled();
  });

  it("is honest when the platform cannot enrol anyone right now", async () => {
    api.status.mockResolvedValue({ ...OFF, available: false });
    mount();
    expect(await screen.findByText(/not available right now/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /turn on/i })).toBeDisabled();
  });

  it("shows the state when on and turns off with password + code", async () => {
    api.status.mockResolvedValue(ON);
    api.disable.mockResolvedValue(undefined);
    mount();
    expect(await screen.findByText(/10 recovery codes left/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^turn off$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/current password/i), { target: { value: "pw" } });
    fireEvent.change(within(dialog).getByLabelText(/code from your app/i), { target: { value: "654321" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /^turn off$/i }));
    await waitFor(() => expect(api.disable).toHaveBeenCalledWith({ password: "pw", code: "654321" }));
  });

  it("does not ask a Google-only account for a password it does not have", async () => {
    api.status.mockResolvedValue({ ...ON, has_password: false });
    api.disable.mockResolvedValue(undefined);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /^turn off$/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByLabelText(/current password/i)).toBeNull();
    fireEvent.change(within(dialog).getByLabelText(/code from your app/i), { target: { value: "654321" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /^turn off$/i }));
    await waitFor(() => expect(api.disable).toHaveBeenCalledWith({ password: null, code: "654321" }));
  });

  it("warns when recovery codes are running low", async () => {
    api.status.mockResolvedValue({ ...ON, recovery_codes_remaining: 2 });
    mount();
    expect(await screen.findByText(/running low on recovery codes/i)).toBeInTheDocument();
  });
});
