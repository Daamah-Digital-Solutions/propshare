import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { authApi, ApiError } from "@/lib/api";
import { CheckCircle2, XCircle } from "lucide-react";

/** Target of the email-verification link: /verify-email?token=…
 *  Consumes the token via /api/v1/auth/verify-email on mount. */
export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const ran = useRef(false);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    if (!token) {
      setState("error");
      setMessage("This verification link is missing its token.");
      return;
    }
    authApi
      .verifyEmail(token)
      .then(() => setState("ok"))
      .catch((err: unknown) => {
        setState("error");
        setMessage(
          err instanceof ApiError && err.code === "TOKEN_INVALID"
            ? "This verification link is invalid or has expired."
            : err instanceof Error
              ? err.message
              : "Verification failed.",
        );
      });
  }, [token]);

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
            {state === "loading" && (
              <>
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto" />
                <p className="text-muted-foreground">Verifying your email…</p>
              </>
            )}
            {state === "ok" && (
              <>
                <CheckCircle2 className="h-12 w-12 text-primary mx-auto" />
                <p className="text-foreground font-medium">Your email is verified.</p>
                <Button className="w-full" onClick={() => navigate("/dashboard")}>Go to dashboard</Button>
                <Link to="/auth" className="text-sm text-primary underline block">Back to sign in</Link>
              </>
            )}
            {state === "error" && (
              <>
                <XCircle className="h-12 w-12 text-destructive mx-auto" />
                <p className="text-destructive font-medium">{message}</p>
                <Link to="/auth" className="text-primary underline">Back to sign in</Link>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
