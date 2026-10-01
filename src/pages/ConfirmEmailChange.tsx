import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { authApi, ApiError, type EmailChange, type EmailChangeLink } from "@/lib/api";
import { CheckCircle2, MailCheck, ShieldAlert, XCircle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

type State = "loading" | "ready" | "working" | "done" | "stopped" | "error";

const errorText = (err: unknown) =>
  err instanceof ApiError && err.code === "TOKEN_INVALID"
    ? "This link is invalid, has expired or was already used."
    : err instanceof Error
      ? err.message
      : "Something went wrong.";

/** Target of both email-change links: /confirm-email-change?token=…
 *  Opening a link changes nothing (mail scanners open links on their own): the page shows
 *  what the link is about, the new address in full, and acts only on a button. The approval
 *  link (sent to the current address) then sends a confirmation link to the new address; the
 *  confirmation link makes the change. "This wasn't me" stops it. Each link works once. */
export default function ConfirmEmailChange() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { isAuthenticated, refresh, signOut } = useAuth();
  const ran = useRef(false);
  const [state, setState] = useState<State>("loading");
  const [link, setLink] = useState<EmailChangeLink | null>(null);
  const [result, setResult] = useState<EmailChange | null>(null);
  const [signedOut, setSignedOut] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    if (!token) {
      setState("error");
      setMessage("This link is missing its token.");
      return;
    }
    authApi
      .inspectEmailChangeLink(token)
      .then((out) => {
        setLink(out);
        setState("ready");
      })
      .catch((err: unknown) => {
        setState("error");
        setMessage(errorText(err));
      });
  }, [token]);

  const go = async () => {
    setState("working");
    try {
      const out = await authApi.followEmailChangeLink(token);
      setResult(out);
      setState("done");
      // signed in on this browser: show the new address everywhere straight away
      if (out.status === "completed" && isAuthenticated) void refresh();
    } catch (err) {
      setState("error");
      setMessage(errorText(err));
    }
  };

  const stop = async () => {
    setState("working");
    try {
      const out = await authApi.rejectEmailChangeLink(token);
      setSignedOut(out.signed_out);
      setState("stopped");
      // every session of the account was ended: this browser's too
      if (out.signed_out && isAuthenticated) void signOut().catch(() => undefined);
    } catch (err) {
      setState("error");
      setMessage(errorText(err));
    }
  };

  const approve = link?.step === "approve";

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-gradient-to-br from-primary to-primary/80 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg">
            <span className="text-primary-foreground font-bold text-2xl">C</span>
          </div>
          <h1 className="text-2xl font-bold text-foreground">Change of email</h1>
        </div>

        <Card className="bg-card border-border">
          <CardContent className="p-6 text-center space-y-4">
            {(state === "loading" || state === "working") && (
              <>
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto" />
                <p className="text-muted-foreground">
                  {state === "loading" ? "Checking your link…" : "One moment…"}
                </p>
              </>
            )}
            {state === "ready" && link && (
              <>
                <MailCheck className="h-12 w-12 text-primary mx-auto" />
                {approve ? (
                  <>
                    <p className="text-foreground font-medium">Approve the change of your sign-in email?</p>
                    <p className="text-sm text-muted-foreground">
                      The account that signs in with {link.account_email} will sign in with this
                      address instead:
                    </p>
                  </>
                ) : (
                  <p className="text-foreground font-medium">
                    Make this address the sign-in email of your Capimax PropShare account?
                  </p>
                )}
                <p
                  className="text-base font-semibold text-foreground break-all rounded-md bg-muted px-3 py-2"
                  data-testid="new-email"
                >
                  {link.new_email}
                </p>
                <p className="text-xs text-muted-foreground">
                  {approve
                    ? "Approve only if you asked for this and the address above is exactly yours. Nothing changes until you press a button."
                    : "If you did not ask for this, choose “This wasn't me”: nothing changes."}
                </p>
                <div className="flex flex-col gap-2 sm:flex-row sm:justify-center">
                  <Button onClick={() => void go()}>
                    {approve ? "Approve the change" : "Confirm my new email"}
                  </Button>
                  <Button variant="outline" onClick={() => void stop()}>
                    This wasn't me
                  </Button>
                </div>
              </>
            )}
            {state === "done" && result?.status === "awaiting_confirmation" && link && (
              <>
                <MailCheck className="h-12 w-12 text-primary mx-auto" />
                <p className="text-foreground font-medium">Approved.</p>
                <p className="text-sm text-muted-foreground">
                  We sent a confirmation link to {link.new_email}. Open it to finish: your email
                  changes then.
                </p>
              </>
            )}
            {state === "done" && result?.status === "completed" && (
              <>
                <CheckCircle2 className="h-12 w-12 text-primary mx-auto" />
                <p className="text-foreground font-medium">
                  Your email is now {link?.new_email ?? result.new_email}.
                </p>
                <p className="text-sm text-muted-foreground">Use it to sign in from now on.</p>
                <Link to={isAuthenticated ? "/settings" : "/auth"} className="text-sm text-primary underline block">
                  {isAuthenticated ? "Back to account settings" : "Sign in"}
                </Link>
              </>
            )}
            {state === "stopped" && (
              <>
                <ShieldAlert className="h-12 w-12 text-primary mx-auto" />
                <p className="text-foreground font-medium">Stopped. Nothing changed.</p>
                <p className="text-sm text-muted-foreground">
                  {signedOut
                    ? "Every device was signed out. Sign in again and change your password, and turn on two-factor authentication."
                    : "This address will not be added to the account."}
                </p>
                {signedOut && (
                  <Link to="/auth" className="text-sm text-primary underline block">
                    Sign in
                  </Link>
                )}
              </>
            )}
            {state === "error" && (
              <>
                <XCircle className="h-12 w-12 text-destructive mx-auto" />
                <p className="text-destructive font-medium">{message}</p>
                <Link to={isAuthenticated ? "/settings" : "/auth"} className="text-primary underline">
                  {isAuthenticated ? "Account settings" : "Back to sign in"}
                </Link>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
