/**
 * The email-confirmation link (2026-10-11): an address is confirmed from inside its account.
 * A visitor who follows the link is sent to sign in and comes back; the link confirms
 * nothing for a visitor, and nothing from another account.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { api, auth, navigate, ApiError } = vi.hoisted(() => {
  class ApiError extends Error {
    code: string;
    status: number;
    constructor(code: string, message: string, status: number) {
      super(message);
      this.code = code;
      this.status = status;
    }
  }
  return {
    api: { verifyEmail: vi.fn() },
    auth: {
      current: {
        isAuthenticated: false,
        isLoading: false,
        userRole: "guest",
        refresh: vi.fn(),
        signOut: vi.fn(),
      },
    },
    navigate: vi.fn(),
    ApiError,
  };
});
vi.mock("@/lib/api", () => ({ ApiError, authApi: api }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth.current }));
vi.mock("react-router-dom", () => ({
  useNavigate: () => navigate,
  useSearchParams: () => [new URLSearchParams("token=tok 1")],
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => <a href={to}>{children}</a>,
}));

import VerifyEmail from "./VerifyEmail";

describe("VerifyEmail", () => {
  beforeEach(() => {
    api.verifyEmail.mockReset();
    navigate.mockReset();
    auth.current = {
      isAuthenticated: false,
      isLoading: false,
      userRole: "guest",
      refresh: vi.fn().mockResolvedValue(null),
      signOut: vi.fn().mockResolvedValue(undefined),
    };
  });

  it("a visitor is asked to sign in, and the link is not used", () => {
    render(<VerifyEmail />);
    const prompt = screen.getByTestId("sign-in-to-confirm");
    expect(prompt).toHaveTextContent("Sign in to confirm your email address");
    expect(prompt).toHaveTextContent(/Did not open a Capimax PropShare account\? Ignore this link/);
    expect(api.verifyEmail).not.toHaveBeenCalled();
    // signing in brings them back to this link
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(navigate).toHaveBeenCalledWith("/auth", { state: { from: "/verify-email?token=tok%201" } });
  });

  it("waits for the session to be known before deciding", () => {
    auth.current = { ...auth.current, isLoading: true };
    render(<VerifyEmail />);
    expect(screen.queryByTestId("sign-in-to-confirm")).toBeNull();
    expect(screen.getByText("Verifying your email…")).toBeInTheDocument();
    expect(api.verifyEmail).not.toHaveBeenCalled();
  });

  it("confirms the address of the signed-in account, once", async () => {
    auth.current = { ...auth.current, isAuthenticated: true, userRole: "investor" };
    api.verifyEmail.mockResolvedValue(undefined);
    const { rerender } = render(<VerifyEmail />);
    await screen.findByText("Your email is verified.");
    rerender(<VerifyEmail />);
    expect(api.verifyEmail).toHaveBeenCalledTimes(1);
    expect(api.verifyEmail).toHaveBeenCalledWith("tok 1");
    // the pages that ask for a confirmed address read it again
    expect(auth.current.refresh).toHaveBeenCalled();
  });

  it("says so when the link belongs to another account, and offers the way to it", async () => {
    auth.current = { ...auth.current, isAuthenticated: true, userRole: "investor" };
    api.verifyEmail.mockRejectedValue(
      new ApiError("NOT_YOUR_LINK", "This link confirms the email address of another account.", 403),
    );
    render(<VerifyEmail />);
    const box = await screen.findByTestId("other-account");
    expect(box).toHaveTextContent("This link is for another account.");
    fireEvent.click(screen.getByRole("button", { name: "Sign out and sign in to the other account" }));
    await waitFor(() => expect(auth.current.signOut).toHaveBeenCalled());
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith("/auth", { state: { from: "/verify-email?token=tok%201" } }),
    );
  });

  it("says when the link has expired, and where a new one comes from", async () => {
    auth.current = { ...auth.current, isAuthenticated: true, userRole: "investor" };
    api.verifyEmail.mockRejectedValue(new ApiError("TOKEN_INVALID", "Invalid or expired token", 400));
    render(<VerifyEmail />);
    expect(
      await screen.findByText(/invalid or has expired\. Ask for a new one from Account Settings\./),
    ).toBeInTheDocument();
  });
});
