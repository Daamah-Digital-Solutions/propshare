import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { REGEXP_ONLY_DIGITS } from "input-otp";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { useAuth } from "@/contexts/AuthContext";
import { ApiError } from "@/lib/api";

/**
 * Second sign-in step, shared by the password sign-in page and the Google callback.
 * The password (or Google) step already passed; no session exists until this succeeds.
 */
export function MfaChallenge({
  mfaToken,
  onDone,
  onRestart,
}: {
  mfaToken: string;
  onDone: () => void;
  /** Back to the first step (challenge expired, or the user gave up). */
  onRestart: () => void;
}) {
  const { completeMfaLogin } = useAuth();
  const [useRecovery, setUseRecovery] = useState(false);
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (value: string) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await completeMfaLogin(mfaToken, value);
      onDone();
    } catch (e) {
      const err = e instanceof ApiError ? e : null;
      const details = (err?.details ?? {}) as { attempts_left?: number; retry_after?: number };
      switch (err?.code) {
        case "MFA_INVALID_CODE":
          setError(
            details.attempts_left != null
              ? `That code is not valid. ${details.attempts_left} attempt${details.attempts_left === 1 ? "" : "s"} left.`
              : "That code is not valid.",
          );
          break;
        case "MFA_LOCKED":
          setError(
            `Too many wrong codes. Try again in ${Math.ceil((details.retry_after ?? 900) / 60)} minutes.`,
          );
          break;
        case "MFA_CHALLENGE_EXPIRED":
          setExpired(true);
          setError("Your sign-in took too long. Please sign in again.");
          break;
        case "MFA_UNAVAILABLE":
          setUseRecovery(true);
          setError("Authenticator codes cannot be checked right now. Use one of your recovery codes.");
          break;
        default:
          setError(err?.message ?? "Could not verify the code. Please try again.");
      }
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="mfa-challenge">
      <div className="text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
          <ShieldCheck className="h-6 w-6 text-primary" />
        </div>
        <h2 className="text-xl font-semibold text-foreground">Two-factor verification</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {useRecovery
            ? "Enter one of the recovery codes you saved when you turned two-factor on."
            : "Enter the 6-digit code from your authenticator app."}
        </p>
      </div>

      {useRecovery ? (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (recovery.trim()) submit(recovery.trim());
          }}
        >
          <Label htmlFor="recovery-code">Recovery code</Label>
          <Input
            id="recovery-code"
            value={recovery}
            onChange={(e) => setRecovery(e.target.value)}
            placeholder="ABCD-EFGH-JKLM-NPQR"
            autoComplete="off"
            autoFocus
            className="font-mono tracking-wider"
          />
          <Button type="submit" className="w-full" disabled={busy || !recovery.trim() || expired}>
            {busy ? "Checking…" : "Verify"}
          </Button>
        </form>
      ) : (
        <div className="flex flex-col items-center gap-3">
          <InputOTP
            maxLength={6}
            pattern={REGEXP_ONLY_DIGITS}
            value={code}
            onChange={setCode}
            onComplete={(v: string) => submit(v)}
            disabled={busy || expired}
            autoFocus
            aria-label="Authentication code"
          >
            <InputOTPGroup>
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <InputOTPSlot key={i} index={i} />
              ))}
            </InputOTPGroup>
          </InputOTP>
          <Button
            className="w-full"
            onClick={() => submit(code)}
            disabled={busy || code.length !== 6 || expired}
          >
            {busy ? "Checking…" : "Verify"}
          </Button>
        </div>
      )}

      {error && (
        <p role="alert" className="text-center text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="flex flex-col items-center gap-2 text-sm">
        {!expired && (
          <button
            type="button"
            className="text-primary underline underline-offset-4"
            onClick={() => {
              setUseRecovery((v) => !v);
              setError(null);
            }}
          >
            {useRecovery ? "Use my authenticator app instead" : "Lost your phone? Use a recovery code"}
          </button>
        )}
        <button type="button" className="text-muted-foreground hover:text-foreground" onClick={onRestart}>
          Back to sign in
        </button>
      </div>
    </div>
  );
}
