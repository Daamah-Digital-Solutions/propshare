import { useCallback, useEffect, useState } from "react";
import { Loader2, MailCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authApi, ApiError, type EmailChange } from "@/lib/api";

/**
 * Changing the sign-in email (Account settings). Two links make the change, in order: one to
 * the CURRENT address approves it, then one to the NEW address confirms it; nothing changes
 * before both. The assistant starts the same change from the chat.
 */
export function EmailChangeControl() {
  const [pending, setPending] = useState<EmailChange | null>(null);
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  const refresh = useCallback(async () => {
    try {
      setPending((await authApi.emailChangeStatus()).pending);
    } catch {
      /* not essential: the form still works */
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const start = async () => {
    setBusy(true);
    setProblem("");
    try {
      setPending(await authApi.startEmailChange(value.trim()));
      setOpen(false);
      setValue("");
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : "Could not start the change. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    setBusy(true);
    setProblem("");
    try {
      await authApi.cancelEmailChange();
      setPending(null);
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : "Could not cancel the change. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  if (pending) {
    return (
      <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-xs" data-testid="email-change-pending">
        <div className="flex items-start gap-2">
          <MailCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <div className="space-y-1">
            <div className="font-medium text-foreground">Changing your email to {pending.new_email}</div>
            <div className="text-muted-foreground">
              {pending.status === "awaiting_approval"
                ? `Open the approval link we sent to your current address (${pending.sent_to}). We then send a confirmation link to the new address.`
                : `Approved. Open the confirmation link we sent to ${pending.sent_to}: the change is made then.`}
            </div>
            <button type="button" onClick={() => void cancel()} disabled={busy} className="text-primary underline disabled:opacity-50">
              Cancel this change
            </button>
            {problem && <div className="text-destructive">{problem}</div>}
          </div>
        </div>
      </div>
    );
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="text-xs font-medium text-primary underline">
        Change email
      </button>
    );
  }

  return (
    <div className="space-y-2 rounded-lg border border-border p-3" data-testid="email-change-form">
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium text-foreground">New email address</div>
        <button type="button" aria-label="Close" onClick={() => setOpen(false)} className="rounded p-0.5 text-muted-foreground hover:bg-muted">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <Input
        type="email"
        placeholder="name@example.com"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-label="New email address"
      />
      <p className="text-[11px] text-muted-foreground">
        For your security we email an approval link to your current address first, then a
        confirmation link to the new one. Your email changes when you open the second link.
      </p>
      {problem && <p className="text-[11px] text-destructive">{problem}</p>}
      <Button size="sm" onClick={() => void start()} disabled={busy || !value.trim()}>
        {busy ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : null}
        Send approval link
      </Button>
    </div>
  );
}
