import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/contexts/AuthContext";
import { kycApi, KycStatusResponse, ApiError } from "@/lib/api";
import {
  Shield,
  CheckCircle,
  Clock,
  XCircle,
  AlertTriangle,
  Loader2,
  ShieldCheck,
} from "lucide-react";

type KycStatus = "pending" | "submitted" | "verified" | "rejected";

const SUMSUB_SDK_SRC = "https://static.sumsub.com/idensic/static/sns-websdk-builder.js";

declare global {
  interface Window {
    // Sumsub WebSDK builder (loaded on demand from their CDN).
    snsWebSdk?: {
      init: (
        token: string,
        refresh: () => Promise<string>,
      ) => {
        withConf: (c: Record<string, unknown>) => {
          on: (e: string, cb: () => void) => {
            build: () => { launch: (sel: string) => void };
          };
          build: () => { launch: (sel: string) => void };
        };
      };
    };
  }
}

function loadSumsubScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.snsWebSdk) return resolve();
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${SUMSUB_SDK_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("Failed to load Sumsub SDK")));
      return;
    }
    const s = document.createElement("script");
    s.src = SUMSUB_SDK_SRC;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Failed to load Sumsub SDK"));
    document.body.appendChild(s);
  });
}

const KYCVerification = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const { user, refresh } = useAuth();

  const [kyc, setKyc] = useState<KycStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [launched, setLaunched] = useState(false);
  const pollRef = useRef<number | null>(null);

  const status = (kyc?.status ?? (user?.kyc_status as KycStatus) ?? "pending") as KycStatus;

  const loadStatus = useCallback(async () => {
    try {
      const data = await kycApi.getMine();
      setKyc(data);
      return data.status;
    } catch {
      return undefined;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  // While the SDK flow is open, poll for the (automatic, webhook-driven) decision.
  useEffect(() => {
    if (!launched) return;
    pollRef.current = window.setInterval(async () => {
      const s = await loadStatus();
      if (s === "verified" || s === "rejected") {
        if (pollRef.current) window.clearInterval(pollRef.current);
        setLaunched(false);
        await refresh();
      }
    }, 5000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [launched, loadStatus, refresh]);

  const handleStart = async () => {
    setStarting(true);
    try {
      const { sdk_token } = await kycApi.start();
      await loadSumsubScript();
      if (!window.snsWebSdk) throw new Error("Sumsub SDK unavailable");
      const instance = window.snsWebSdk
        .init(sdk_token, () => kycApi.start().then((r) => r.sdk_token))
        .withConf({ lang: "en" })
        .on("idCheck.onApplicantStatusChanged", () => {
          void loadStatus();
        })
        .build();
      instance.launch("#sumsub-websdk-container");
      setLaunched(true);
      await loadStatus();
    } catch (error) {
      if (error instanceof ApiError && error.code === "KYC_NOT_CONFIGURED") {
        toast({
          title: "Verification coming online soon",
          description: "Instant identity verification is being connected and will be available shortly.",
        });
      } else if (error instanceof ApiError && error.code === "KYC_ALREADY_VERIFIED") {
        toast({ title: "Already verified", description: "Your identity is already verified." });
        await loadStatus();
      } else {
        const message = error instanceof ApiError ? error.message : "Could not start verification.";
        toast({ title: "Error", description: message, variant: "destructive" });
      }
    } finally {
      setStarting(false);
    }
  };

  const getStatusBadge = (s: KycStatus) => {
    switch (s) {
      case "pending":
        return (
          <Badge variant="outline" className="text-muted-foreground">
            <Clock className="h-3 w-3 mr-1" /> Not Started
          </Badge>
        );
      case "submitted":
        return (
          <Badge variant="outline" className="text-amber-600 border-amber-600">
            <Clock className="h-3 w-3 mr-1" /> {kyc?.manual_review_required ? "Under Review" : "In Progress"}
          </Badge>
        );
      case "verified":
        return (
          <Badge className="bg-green-500 hover:bg-green-600">
            <CheckCircle className="h-3 w-3 mr-1" /> Verified
          </Badge>
        );
      case "rejected":
        return (
          <Badge variant="destructive">
            <XCircle className="h-3 w-3 mr-1" /> Rejected
          </Badge>
        );
    }
  };

  const progress = { pending: 0, submitted: 50, verified: 100, rejected: 25 }[status] ?? 0;

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-3xl flex items-center justify-center min-h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const canVerify = status === "pending" || status === "rejected" || status === "submitted";

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <div className="text-center mb-8">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
          <Shield className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-3xl font-bold text-foreground mb-2">KYC Verification</h1>
        <p className="text-muted-foreground">
          Fast, automated identity verification — most checks complete in minutes, with no manual
          back-office step.
        </p>
      </div>

      {/* Status */}
      <Card className="mb-8">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Verification Status</CardTitle>
            {getStatusBadge(status)}
          </div>
        </CardHeader>
        <CardContent>
          <Progress value={progress} className="h-2 mb-4" />
          <div className="flex justify-between text-sm text-muted-foreground">
            <span>Start</span>
            <span>In Progress</span>
            <span>Verified</span>
          </div>

          {status === "verified" && kyc?.verified_at && (
            <div className="mt-4 p-4 bg-green-500/10 rounded-lg border border-green-500/20">
              <div className="flex items-center gap-2 text-green-600">
                <CheckCircle className="h-5 w-5" />
                <span className="font-medium">Verification Complete</span>
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                Verified on {new Date(kyc.verified_at).toLocaleDateString()}
              </p>
            </div>
          )}

          {status === "rejected" && (
            <div className="mt-4 p-4 bg-destructive/10 rounded-lg border border-destructive/20">
              <div className="flex items-center gap-2 text-destructive">
                <AlertTriangle className="h-5 w-5" />
                <span className="font-medium">Verification Unsuccessful</span>
              </div>
              {kyc?.rejection_reason && (
                <p className="text-sm text-muted-foreground mt-1">Reason: {kyc.rejection_reason}</p>
              )}
              <p className="text-sm text-foreground mt-2">You can restart verification below.</p>
            </div>
          )}

          {status === "submitted" && kyc?.manual_review_required && (
            <div className="mt-4 p-4 bg-amber-500/10 rounded-lg border border-amber-500/20">
              <div className="flex items-center gap-2 text-amber-600">
                <Clock className="h-5 w-5" />
                <span className="font-medium">Under Review</span>
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                A few cases need a brief manual check. We&apos;ll notify you when it&apos;s done.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Verification action */}
      {status !== "verified" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5" />
              {status === "rejected" ? "Restart Verification" : "Verify Your Identity"}
            </CardTitle>
            <CardDescription>
              You&apos;ll be guided through document capture and a quick liveness check. Approval is
              automatic.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {canVerify && (
              <Button onClick={handleStart} disabled={starting || launched} size="lg">
                {starting ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" /> Starting…
                  </>
                ) : launched ? (
                  "Verification in progress…"
                ) : status === "submitted" ? (
                  "Continue Verification"
                ) : (
                  "Start Verification"
                )}
              </Button>
            )}
            {/* Sumsub WebSDK mounts here once a session token is issued. */}
            <div id="sumsub-websdk-container" />
          </CardContent>
        </Card>
      )}

      {status === "verified" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-green-600">
              <CheckCircle className="h-5 w-5" /> You&apos;re Verified!
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground mb-4">
              Your identity has been verified. You now have full access to all platform features.
            </p>
            <Separator className="my-6" />
            <div className="flex gap-4">
              <Button onClick={() => navigate("/marketplace")}>Browse Properties</Button>
              <Button variant="outline" onClick={() => navigate("/dashboard")}>
                Go to Dashboard
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default KYCVerification;
