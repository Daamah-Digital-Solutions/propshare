import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { authApi, ApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { MfaChallenge } from "@/components/auth/MfaChallenge";

/** OAuth redirect target: providers send the user back here with ?code=...
 *  We exchange the code with the backend, which verifies it with the provider.
 *  The redirect_uri MUST match the one used to start the flow (see Auth.tsx). */
export default function AuthCallback() {
  const { provider = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [error, setError] = useState<string | null>(null);
  // Google succeeded but the account has two-factor on: a code is still owed.
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    const code = params.get("code");
    const providerError = params.get("error");
    if (providerError) {
      setError(`Sign-in was cancelled or failed (${providerError}).`);
      return;
    }
    if (!code) {
      setError("Missing authorization code.");
      return;
    }
    const redirectUri = `${window.location.origin}/auth/callback/${provider}`;
    authApi
      .oauthLogin(provider, code, redirectUri)
      .then(async (result) => {
        if (result.status === "mfa_required") {
          setMfaToken(result.mfaToken);
          return;
        }
        await refresh();
        navigate("/dashboard", { replace: true });
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.code === "OAUTH_NOT_CONFIGURED") {
          setError(`${provider} sign-in is not configured yet.`);
        } else {
          setError(e instanceof Error ? e.message : "Sign-in failed.");
        }
      });
  }, [provider, params, navigate, refresh]);

  if (mfaToken && !error) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center p-6">
        <div className="w-full max-w-sm rounded-2xl border border-border bg-card p-6">
          <MfaChallenge
            mfaToken={mfaToken}
            onDone={() => navigate("/dashboard", { replace: true })}
            onRestart={() => navigate("/auth", { replace: true })}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center gap-4 p-6 text-center">
      {error ? (
        <>
          <p className="text-destructive font-medium">{error}</p>
          <button className="text-primary underline" onClick={() => navigate("/auth")}>
            Back to sign in
          </button>
        </>
      ) : (
        <>
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          <p className="text-muted-foreground">Completing sign-in…</p>
        </>
      )}
    </div>
  );
}
