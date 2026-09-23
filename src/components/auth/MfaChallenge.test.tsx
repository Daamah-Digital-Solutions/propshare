/**
 * Second sign-in step. The password already passed; no session exists until a code does.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const { complete, fail, FakeApiError } = vi.hoisted(() => ({
  complete: vi.fn(),
  fail: { error: null as Error | null },
  FakeApiError: class extends Error {
    code: string;
    status: number;
    details: unknown;
    constructor(code: string, message: string, status: number, details?: unknown) {
      super(message);
      this.code = code;
      this.status = status;
      this.details = details;
    }
  },
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    completeMfaLogin: async (t: string, c: string) => {
      complete(t, c);
      if (fail.error) throw fail.error;
    },
  }),
}));
vi.mock("@/lib/api", () => ({ ApiError: FakeApiError }));

import { MfaChallenge } from "./MfaChallenge";

const typeCode = (code: string) => {
  const input = screen.getByRole("textbox", { name: /authentication code/i });
  fireEvent.change(input, { target: { value: code } });
};

describe("MfaChallenge", () => {
  // input-otp schedules 0/10/50 ms timers on every value change and never clears them;
  // let them fire while the DOM still exists, or they throw after teardown.
  afterEach(async () => {
    cleanup();
    await new Promise((r) => setTimeout(r, 80));
  });

  beforeEach(() => {
    complete.mockReset();
    fail.error = null;
  });

  it("submits the 6-digit code with the challenge and signs in", async () => {
    const onDone = vi.fn();
    render(<MfaChallenge mfaToken="chal-1" onDone={onDone} onRestart={vi.fn()} />);
    typeCode("123456");
    await waitFor(() => expect(complete).toHaveBeenCalledWith("chal-1", "123456"));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("says how many attempts are left after a wrong code", async () => {
    fail.error = new FakeApiError("MFA_INVALID_CODE", "That code is not valid.", 401, { attempts_left: 3 });
    const onDone = vi.fn();
    render(<MfaChallenge mfaToken="chal-1" onDone={onDone} onRestart={vi.fn()} />);
    typeCode("000000");
    expect(await screen.findByRole("alert")).toHaveTextContent("3 attempts left");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("explains the lockout", async () => {
    fail.error = new FakeApiError("MFA_LOCKED", "locked", 429, { retry_after: 600 });
    render(<MfaChallenge mfaToken="chal-1" onDone={vi.fn()} onRestart={vi.fn()} />);
    typeCode("000000");
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again in 10 minutes");
  });

  it("accepts a recovery code", async () => {
    const onDone = vi.fn();
    render(<MfaChallenge mfaToken="chal-2" onDone={onDone} onRestart={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /use a recovery code/i }));
    fireEvent.change(screen.getByLabelText(/recovery code/i), { target: { value: "ABCD-EFGH-JKLM-NPQR" } });
    fireEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    await waitFor(() => expect(complete).toHaveBeenCalledWith("chal-2", "ABCD-EFGH-JKLM-NPQR"));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("sends the user back to sign in when the challenge expired", async () => {
    fail.error = new FakeApiError("MFA_CHALLENGE_EXPIRED", "Please sign in again.", 401);
    const onRestart = vi.fn();
    render(<MfaChallenge mfaToken="old" onDone={vi.fn()} onRestart={onRestart} />);
    typeCode("123456");
    expect(await screen.findByRole("alert")).toHaveTextContent(/sign in again/i);
    fireEvent.click(screen.getByRole("button", { name: /back to sign in/i }));
    expect(onRestart).toHaveBeenCalled();
  });
});
