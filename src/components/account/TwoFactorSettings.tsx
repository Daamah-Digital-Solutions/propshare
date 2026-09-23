import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Download, KeyRound, ShieldCheck, Smartphone } from "lucide-react";
import { REGEXP_ONLY_DIGITS } from "input-otp";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { useToast } from "@/hooks/use-toast";
import { ApiError, mfaApi } from "@/lib/api";
import type { MfaSetup } from "@/lib/api";

/**
 * Two-factor authentication in Account Settings — the real thing: an authenticator app
 * (Google Authenticator, Microsoft Authenticator, Authy, 1Password…) plus ten one-time
 * recovery codes. Every step talks to the server; nothing here is decorative.
 */

const errorText = (e: unknown, fallback: string) => {
  if (!(e instanceof ApiError)) return fallback;
  const d = (e.details ?? {}) as { attempts_left?: number; retry_after?: number };
  if (e.code === "MFA_INVALID_CODE" && d.attempts_left != null)
    return `That code is not valid. ${d.attempts_left} attempt${d.attempts_left === 1 ? "" : "s"} left.`;
  if (e.code === "MFA_LOCKED")
    return `Too many wrong codes. Try again in ${Math.ceil((d.retry_after ?? 900) / 60)} minutes.`;
  return e.message || fallback;
};

function CodeInput({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled?: boolean }) {
  return (
    <InputOTP
      maxLength={6}
      pattern={REGEXP_ONLY_DIGITS}
      value={value}
      onChange={onChange}
      disabled={disabled}
      aria-label="Authentication code"
    >
      <InputOTPGroup>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <InputOTPSlot key={i} index={i} />
        ))}
      </InputOTPGroup>
    </InputOTP>
  );
}

/** Shown once after enabling or regenerating. The user must confirm they saved them. */
function RecoveryCodes({ codes, onClose }: { codes: string[]; onClose: () => void }) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = `Capimax PropShare — two-factor recovery codes\nEach code works once.\n\n${codes.join("\n")}\n`;

  const copyAll = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      /* the codes stay on screen; the user can select them */
    }
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "capimax-recovery-codes.txt";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4" data-testid="recovery-codes">
      <p className="text-sm text-muted-foreground">
        If you lose your phone, each of these codes lets you sign in once. Save them somewhere
        safe now — <b>they will not be shown again</b>.
      </p>
      <div className="grid grid-cols-2 gap-2 rounded-lg bg-muted/50 p-4 font-mono text-sm">
        {codes.map((c) => (
          <span key={c}>{c}</span>
        ))}
      </div>
      <div className="flex gap-2">
        <Button type="button" variant="outline" className="flex-1" onClick={copyAll}>
          {copied ? <Check className="mr-2 h-4 w-4" /> : <Copy className="mr-2 h-4 w-4" />}
          {copied ? "Copied" : "Copy all"}
        </Button>
        <Button type="button" variant="outline" className="flex-1" onClick={download}>
          <Download className="mr-2 h-4 w-4" /> Download
        </Button>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox checked={saved} onCheckedChange={(v) => setSaved(v === true)} aria-label="I saved my recovery codes" />
        I saved these codes somewhere safe
      </label>
      <DialogFooter>
        <Button onClick={onClose} disabled={!saved}>
          Done
        </Button>
      </DialogFooter>
    </div>
  );
}

export function TwoFactorSettings() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data: status, isLoading } = useQuery({ queryKey: ["mfa-status"], queryFn: mfaApi.status });
  const refresh = () => qc.invalidateQueries({ queryKey: ["mfa-status"] });

  // --- turn on -------------------------------------------------------------
  const [enableOpen, setEnableOpen] = useState(false);
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [keyCopied, setKeyCopied] = useState(false);

  const startEnable = async () => {
    setErr(null);
    setCode("");
    setCodes(null);
    setSetup(null);
    setEnableOpen(true);
    try {
      setSetup(await mfaApi.setup());
    } catch (e) {
      setErr(errorText(e, "Could not start the setup. Please try again."));
    }
  };

  const confirmEnable = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await mfaApi.enable(code);
      setCodes(res.recovery_codes);
      refresh();
    } catch (e) {
      setErr(errorText(e, "That code did not match."));
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  // --- turn off ------------------------------------------------------------
  const [disableOpen, setDisableOpen] = useState(false);
  const [pw, setPw] = useState("");
  const [offCode, setOffCode] = useState("");

  const confirmDisable = async () => {
    setBusy(true);
    setErr(null);
    try {
      await mfaApi.disable({ password: status?.has_password ? pw : null, code: offCode.trim() });
      setDisableOpen(false);
      refresh();
      toast({ title: "Two-factor authentication is off", description: "We emailed you about this change." });
    } catch (e) {
      setErr(errorText(e, "Could not turn two-factor off."));
    } finally {
      setBusy(false);
    }
  };

  // --- new recovery codes --------------------------------------------------
  const [regenOpen, setRegenOpen] = useState(false);
  const [regenCode, setRegenCode] = useState("");

  const confirmRegen = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await mfaApi.regenerateRecoveryCodes(regenCode);
      setCodes(res.recovery_codes);
      refresh();
    } catch (e) {
      setErr(errorText(e, "Could not create new codes."));
      setRegenCode("");
    } finally {
      setBusy(false);
    }
  };

  if (isLoading || !status) {
    return <div className="h-[72px] rounded-lg bg-muted/50 animate-pulse" />;
  }

  const lowCodes = status.enabled && status.recovery_codes_remaining <= 3;

  return (
    <div className="space-y-3" data-testid="two-factor-settings">
      <div className="flex items-center justify-between gap-4 rounded-lg bg-muted/50 p-4">
        <div className="flex items-center gap-3">
          {status.enabled ? (
            <ShieldCheck className="h-5 w-5 text-green-500" />
          ) : (
            <Smartphone className="h-5 w-5 text-muted-foreground" />
          )}
          <div>
            <p className="font-medium text-foreground">Two-Factor Authentication</p>
            <p className="text-sm text-muted-foreground">
              {status.enabled
                ? `On since ${new Date(status.enabled_at ?? "").toLocaleDateString()} · ${status.recovery_codes_remaining} recovery code${status.recovery_codes_remaining === 1 ? "" : "s"} left`
                : status.available
                  ? "Ask for a code from your authenticator app every time you sign in."
                  : "Not available right now. Please try again later."}
            </p>
          </div>
        </div>
        {status.enabled ? (
          <Badge className="bg-green-500">On</Badge>
        ) : (
          <Button size="sm" onClick={startEnable} disabled={!status.available}>
            Turn on
          </Button>
        )}
      </div>

      {status.enabled && (
        <div className="flex flex-wrap gap-2">
          {lowCodes && (
            <p className="w-full text-sm text-amber-600">
              You are running low on recovery codes. Create a new set.
            </p>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setErr(null);
              setCodes(null);
              setRegenCode("");
              setRegenOpen(true);
            }}
          >
            <KeyRound className="mr-2 h-4 w-4" /> New recovery codes
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-destructive"
            onClick={() => {
              setErr(null);
              setPw("");
              setOffCode("");
              setDisableOpen(true);
            }}
          >
            Turn off
          </Button>
        </div>
      )}

      {/* Turn on: scan → first code → recovery codes */}
      <Dialog open={enableOpen} onOpenChange={(o) => !busy && setEnableOpen(o)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{codes ? "Save your recovery codes" : "Turn on two-factor authentication"}</DialogTitle>
            {!codes && (
              <DialogDescription>
                Scan this QR code with an authenticator app such as Google Authenticator,
                Microsoft Authenticator or Authy, then enter the 6-digit code it shows.
              </DialogDescription>
            )}
          </DialogHeader>
          {codes ? (
            <RecoveryCodes
              codes={codes}
              onClose={() => {
                setEnableOpen(false);
                toast({ title: "Two-factor authentication is on", description: "You'll be asked for a code at every sign-in." });
              }}
            />
          ) : (
            <div className="space-y-4">
              {setup ? (
                <>
                  <img
                    src={setup.qr_svg_data_uri}
                    alt="QR code for your authenticator app"
                    className="mx-auto h-48 w-48 rounded-lg bg-white p-2"
                    data-testid="mfa-qr"
                  />
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Can't scan it? Enter this key in the app:</p>
                    <div className="flex items-center gap-2">
                      <code className="flex-1 break-all rounded-md bg-muted px-2 py-1 font-mono text-xs" data-testid="mfa-secret">
                        {setup.secret.match(/.{1,4}/g)?.join(" ")}
                      </code>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        aria-label="Copy key"
                        onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(setup.secret);
                            setKeyCopied(true);
                          } catch {
                            /* visible on screen */
                          }
                        }}
                      >
                        {keyCopied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                      </Button>
                    </div>
                  </div>
                  <div className="flex flex-col items-center gap-2">
                    <Label>Code from the app</Label>
                    <CodeInput value={code} onChange={setCode} disabled={busy} />
                  </div>
                </>
              ) : (
                !err && <p className="text-center text-sm text-muted-foreground">Preparing your QR code…</p>
              )}
              {err && (
                <p role="alert" className="text-center text-sm text-destructive">
                  {err}
                </p>
              )}
              <DialogFooter>
                <Button variant="outline" onClick={() => setEnableOpen(false)} disabled={busy}>
                  Cancel
                </Button>
                <Button onClick={confirmEnable} disabled={!setup || code.length !== 6 || busy}>
                  {busy ? "Checking…" : "Turn on"}
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Turn off */}
      <Dialog open={disableOpen} onOpenChange={(o) => !busy && setDisableOpen(o)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Turn off two-factor authentication?</DialogTitle>
            <DialogDescription>
              Your account will be protected by your {status.has_password ? "password" : "Google sign-in"} only.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {status.has_password && (
              <div className="space-y-1">
                <Label htmlFor="mfa-off-password">Current password</Label>
                <Input
                  id="mfa-off-password"
                  type="password"
                  value={pw}
                  onChange={(e) => setPw(e.target.value)}
                  autoComplete="current-password"
                />
              </div>
            )}
            <div className="space-y-1">
              <Label htmlFor="mfa-off-code">Code from your app, or a recovery code</Label>
              <Input
                id="mfa-off-code"
                value={offCode}
                onChange={(e) => setOffCode(e.target.value)}
                autoComplete="one-time-code"
                placeholder="123456"
                className="font-mono"
              />
            </div>
            {err && (
              <p role="alert" className="text-sm text-destructive">
                {err}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisableOpen(false)} disabled={busy}>
              Keep it on
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDisable}
              disabled={busy || offCode.trim().length < 6 || (status.has_password && !pw)}
            >
              {busy ? "Checking…" : "Turn off"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* New recovery codes */}
      <Dialog open={regenOpen} onOpenChange={(o) => !busy && setRegenOpen(o)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{codes ? "Your new recovery codes" : "Create new recovery codes"}</DialogTitle>
            {!codes && (
              <DialogDescription>
                Your current recovery codes will stop working. Enter a code from your app to continue.
              </DialogDescription>
            )}
          </DialogHeader>
          {codes ? (
            <RecoveryCodes codes={codes} onClose={() => setRegenOpen(false)} />
          ) : (
            <div className="space-y-4">
              <div className="flex justify-center">
                <CodeInput value={regenCode} onChange={setRegenCode} disabled={busy} />
              </div>
              {err && (
                <p role="alert" className="text-center text-sm text-destructive">
                  {err}
                </p>
              )}
              <DialogFooter>
                <Button variant="outline" onClick={() => setRegenOpen(false)} disabled={busy}>
                  Cancel
                </Button>
                <Button onClick={confirmRegen} disabled={regenCode.length !== 6 || busy}>
                  {busy ? "Checking…" : "Create new codes"}
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
