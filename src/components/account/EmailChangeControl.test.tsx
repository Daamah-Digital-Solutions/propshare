/**
 * Changing the sign-in email from Account settings: the change starts with an approval link
 * to the CURRENT address, says where each link went, and can be cancelled.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { auth } = vi.hoisted(() => ({
  auth: { emailChangeStatus: vi.fn(), startEmailChange: vi.fn(), cancelEmailChange: vi.fn() },
}));
vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return { ...real, authApi: auth };
});

import { ApiError } from "@/lib/api";
import { EmailChangeControl } from "./EmailChangeControl";

describe("EmailChangeControl", () => {
  beforeEach(() => Object.values(auth).forEach((m) => m.mockReset()));

  it("starts a change and says the approval link went to the current address", async () => {
    auth.emailChangeStatus.mockResolvedValue({ pending: null });
    auth.startEmailChange.mockResolvedValue({
      status: "awaiting_approval",
      new_email: "n***w@x.com",
      sent_to: "o***d@x.com",
      expires_at: "later",
    });
    render(<EmailChangeControl />);
    fireEvent.click(screen.getByRole("button", { name: /change email/i }));
    fireEvent.change(screen.getByLabelText(/new email address/i), { target: { value: " new@x.com " } });
    fireEvent.click(screen.getByRole("button", { name: /send approval link/i }));
    await waitFor(() => expect(auth.startEmailChange).toHaveBeenCalledWith("new@x.com"));
    const pending = await screen.findByTestId("email-change-pending");
    expect(pending).toHaveTextContent("Changing your email to n***w@x.com");
    expect(pending).toHaveTextContent("current address (o***d@x.com)");
  });

  it("shows why a change was refused", async () => {
    auth.emailChangeStatus.mockResolvedValue({ pending: null });
    auth.startEmailChange.mockRejectedValue(
      new ApiError("EMAIL_EXISTS", "That email address is already used by another account.", 409),
    );
    render(<EmailChangeControl />);
    fireEvent.click(screen.getByRole("button", { name: /change email/i }));
    fireEvent.change(screen.getByLabelText(/new email address/i), { target: { value: "taken@x.com" } });
    fireEvent.click(screen.getByRole("button", { name: /send approval link/i }));
    expect(await screen.findByText(/already used by another account/i)).toBeInTheDocument();
  });

  it("a change waiting for the new address can be cancelled", async () => {
    auth.emailChangeStatus.mockResolvedValue({
      pending: { status: "awaiting_confirmation", new_email: "n***w@x.com", sent_to: "n***w@x.com", expires_at: "later" },
    });
    auth.cancelEmailChange.mockResolvedValue(undefined);
    render(<EmailChangeControl />);
    expect(await screen.findByText(/approved\. open the confirmation link/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /cancel this change/i }));
    await waitFor(() => expect(auth.cancelEmailChange).toHaveBeenCalled());
    expect(await screen.findByRole("button", { name: /change email/i })).toBeInTheDocument();
  });
});
