/**
 * The notice shown to a member whose email address is not confirmed, on a page where
 * something may have been sent to that address (2026-10-11).
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { api, auth, toast } = vi.hoisted(() => ({
  api: { resendVerification: vi.fn() },
  auth: { current: { user: null as Record<string, unknown> | null } },
  toast: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ ApiError: class extends Error {}, authApi: api }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth.current }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast }) }));

import { ConfirmAddressNotice } from "./ConfirmAddressNotice";

describe("ConfirmAddressNotice", () => {
  beforeEach(() => {
    api.resendVerification.mockReset();
    toast.mockReset();
  });

  it("says nothing to a visitor, or to a member whose address is confirmed", () => {
    auth.current = { user: null };
    const { rerender } = render(<ConfirmAddressNotice>why</ConfirmAddressNotice>);
    expect(screen.queryByTestId("confirm-address-notice")).toBeNull();
    auth.current = { user: { email: "omar@fam.io", email_verified: true } };
    rerender(<ConfirmAddressNotice>why</ConfirmAddressNotice>);
    expect(screen.queryByTestId("confirm-address-notice")).toBeNull();
  });

  it("tells a member whose address is not confirmed why it matters, and sends the link", async () => {
    auth.current = { user: { email: "omar@fam.io", email_verified: false } };
    api.resendVerification.mockResolvedValue(undefined);
    render(<ConfirmAddressNotice>Units sent to your address wait for it.</ConfirmAddressNotice>);
    const notice = screen.getByTestId("confirm-address-notice");
    expect(notice).toHaveTextContent("Confirm your email address");
    expect(notice).toHaveTextContent("Units sent to your address wait for it.");
    fireEvent.click(screen.getByRole("button", { name: "Send me the confirmation link" }));
    await waitFor(() => expect(api.resendVerification).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Confirmation link sent",
          description: "Open the email we sent to omar@fam.io and follow the link.",
        }),
      ),
    );
  });
});
