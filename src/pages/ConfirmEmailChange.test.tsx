/**
 * The page both email-change links open. Opening it changes nothing (mail scanners open links
 * on their own): it shows the new address in full and acts only on a button. The approval
 * says a confirmation link went to the new address; the confirmation says the change is done;
 * "This wasn't me" stops it; a used link says so.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

// plain async functions, not spies: a spy returning a rejected promise is reported as an
// unhandled rejection even when the page catches it
const { link, authState } = vi.hoisted(() => ({
  link: {
    calls: [] as string[],
    inspected: null as unknown,
    result: null as unknown,
    rejected: null as unknown,
    error: null as unknown,
  },
  authState: { isAuthenticated: false, refresh: async () => null, signOut: async () => undefined },
}));
vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    authApi: {
      inspectEmailChangeLink: async (token: string) => {
        link.calls.push(`inspect:${token}`);
        if (link.error) throw link.error;
        return link.inspected;
      },
      followEmailChangeLink: async (token: string) => {
        link.calls.push(`follow:${token}`);
        return link.result;
      },
      rejectEmailChangeLink: async (token: string) => {
        link.calls.push(`reject:${token}`);
        return link.rejected;
      },
    },
  };
});
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => authState }));

import { ApiError } from "@/lib/api";
import ConfirmEmailChange from "./ConfirmEmailChange";

const at = (token: string) =>
  render(
    <MemoryRouter initialEntries={[`/confirm-email-change?token=${token}`]}>
      <ConfirmEmailChange />
    </MemoryRouter>,
  );

const approveLink = {
  step: "approve",
  new_email: "new.address@x.com",
  account_email: "o***d@x.com",
  expires_at: "2026-10-02T10:00:00Z",
};

describe("ConfirmEmailChange", () => {
  beforeEach(() => {
    link.calls = [];
    link.inspected = null;
    link.result = null;
    link.rejected = null;
    link.error = null;
  });

  it("opening the approval link only shows it; the button approves", async () => {
    link.inspected = approveLink;
    link.result = { status: "awaiting_confirmation", new_email: "n***s@x.com", sent_to: null, expires_at: null };
    at("approve-token-123");
    expect(await screen.findByTestId("new-email")).toHaveTextContent("new.address@x.com");
    expect(screen.getByText(/signs in with o\*\*\*d@x\.com/i)).toBeInTheDocument();
    expect(link.calls).toEqual(["inspect:approve-token-123"]); // nothing acted yet
    fireEvent.click(screen.getByRole("button", { name: /approve the change/i }));
    expect(await screen.findByText(/we sent a confirmation link to new\.address@x\.com/i)).toBeInTheDocument();
    expect(link.calls).toEqual(["inspect:approve-token-123", "follow:approve-token-123"]);
  });

  it("the confirmation link makes the change on its button", async () => {
    link.inspected = { ...approveLink, step: "confirm" };
    link.result = { status: "completed", new_email: "n***s@x.com", sent_to: null, expires_at: null };
    at("confirm-token-456");
    fireEvent.click(await screen.findByRole("button", { name: /confirm my new email/i }));
    expect(await screen.findByText(/your email is now new\.address@x\.com/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/auth");
  });

  it("this wasn't me stops the change and says every device was signed out", async () => {
    link.inspected = approveLink;
    link.rejected = { status: "cancelled", signed_out: true };
    at("approve-token-789");
    fireEvent.click(await screen.findByRole("button", { name: /this wasn't me/i }));
    expect(await screen.findByText(/stopped\. nothing changed/i)).toBeInTheDocument();
    expect(screen.getByText(/every device was signed out/i)).toBeInTheDocument();
    expect(link.calls).toEqual(["inspect:approve-token-789", "reject:approve-token-789"]);
  });

  it("a used or expired link says so", async () => {
    link.error = new ApiError("TOKEN_INVALID", "x", 400);
    at("used-token-789");
    expect(await screen.findByText(/invalid, has expired or was already used/i)).toBeInTheDocument();
  });
});
