import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { authApi, ApiError } from "@/lib/api";
import { CheckCircle2, LogIn, XCircle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { roleHome } from "@/lib/roles";

/** Target of the email-verification link: /verify-email?token=…
 *
 *  An address is confirmed from inside its account: the link does nothing for a visitor, or
 *  from another account. So a person who receives a link for an account they did not open
 *  cannot confirm that account by following it, and a confirmed address always means that
 *  whoever holds the account holds the mailbox. A visitor is sent to sign in and comes back
 *  here; the token is then used once, with their session. */
export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const { userRole, isAuthenticated, isLoading, refresh, signOut } = useAuth();
  const ran = useRef(false);
  const [state, setState] = useState<"loading" | "ok" | "error" | "other-account">("loading");
  const [message, setMessage] = useState("");
  const back = `/verify-email?token=${encodeURIComponent(token)}`;

  useEffect(() => {
    if (isLoading || !isAuthenticated || ran.current) return;
    ran.current = true;
    if (!token) {
      setState("error");
      setMessage("This verification link is missing its token.");
      return;
    }
    authApi
      .verifyEmail(token)
      .then(() => {
        setState("ok");
        void refresh(); // the pages that ask for a confirmed address read it from here
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.code === "NOT_YOUR_LINK") {
          setState("other-account");
          return;
        }
        setState("error");
        setMessage(
          err instanceof ApiError && err.code === "TOKEN_INVALID"
            ? "This verification link is invalid or has expired. Ask for a new one from Account Settings."
            : err instanceof Error
              ? err.message
              : "Verification failed.",
        );
      });
  }, [token, isLoading, isAuthenticated, refresh]);

  const toSignIn = () => navigate("/auth", { state: { from: back } });
  const visitor = !isLoading && !isAuthenticated;

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-gradient-to-br from-primary to-primary/80 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg">
            <span className="text-primary-foreground font-bold text-2xl">C</span>
          </div>
          <h1 className="text-2xl font-bold text-foreground">Email verification</h1>
        </div>

        <Card className="bg-card border-border">
          <CardContent className="p-6 text-center space-y-4">
            {visitor && !token && (
              <>
                <XCircle className="h-12 w-12 text-destructive mx-auto" />
                <p className="text-destructive font-medium">This verification link is missing its token.</p>
                <Link to="/auth" className="text-primary underline">Back to sign in</Link>
              </>
            )}
            {visitor && token && (
              <div data-testid="sign-in-to-confirm" className="space-y-4">
                <LogIn className="h-12 w-12 text-primary mx-auto" />
                <p className="text-foreground font-medium">Sign in to confirm your email address</p>
                <p className="text-sm text-muted-foreground">
                  An email address is confirmed from inside its account. Sign in, and this link finishes
                  the confirmation.
                </p>
                <Button className="w-full" onClick={toSignIn}>Sign in</Button>
                <p className="text-xs text-muted-foreground">
                  Did not open a Capimax PropShare account? Ignore this link: it does nothing on its own.
                </p>
              </div>
            )}
            {!visitor && state === "loading" && (
              <>
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto" />
                <p className="text-muted-foreground">Verifying your email…</p>
              </>
            )}
            {!visitor && state === "ok" && (
              <>
                <CheckCircle2 className="h-12 w-12 text-primary mx-auto" />
                <p className="text-foreground font-medium">Your email is verified.</p>
                <Button className="w-full" onClick={() => navigate(roleHome(userRole))}>Go to dashboard</Button>
              </>
            )}
            {!visitor && state === "other-account" && (
              <div data-testid="other-account" className="space-y-4">
                <XCircle className="h-12 w-12 text-destructive mx-auto" />
                <p className="text-destructive font-medium">This link is for another account.</p>
                <p className="text-sm text-muted-foreground">
                  You are signed in to a different account than the one this link confirms. Sign out, then
                  sign in to that account: the link works from there.
                </p>
                <Button
                  className="w-full"
                  variant="outline"
                  onClick={async () => {
                    await signOut();
                    ran.current = false;
                    setState("loading");
                    toSignIn();
                  }}
                >
                  Sign out and sign in to the other account
                </Button>
              </div>
            )}
            {!visitor && state === "error" && (
              <>
                <XCircle className="h-12 w-12 text-destructive mx-auto" />
                <p className="text-destructive font-medium">{message}</p>
                <Button className="w-full" variant="outline" onClick={() => navigate(roleHome(userRole))}>
                  Go to dashboard
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
