import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Lock, ArrowRight, UserPlus, Loader2, ShieldCheck, FileText } from "lucide-react";
import { useAuth, type UserRole } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { ApiError } from "@/lib/api";
import { roleLabel, applicationRoles } from "@/lib/roles";

/**
 * Shown when an authenticated user opens a role-gated dashboard they don't have
 * access to (and have no pending application) — instead of silently bouncing them
 * home. Approval roles (Broker / Liquidity Provider) get a "Request Access" CTA
 * into the join-form flow; self-serve roles (Property Owner) get an instant
 * "Become" button. Real authorization stays enforced server-side.
 */
export function RoleGate({ role }: { role: UserRole }) {
  const navigate = useNavigate();
  const { requestRole, switchActiveRole } = useAuth();
  const { toast } = useToast();
  const [busy, setBusy] = useState(false);

  const label = roleLabel(role);
  const needsApplication = applicationRoles().includes(role);

  const becomeSelfServe = async () => {
    setBusy(true);
    try {
      await requestRole(role);
      await switchActiveRole(role); // refreshes the JWT so the dashboard opens immediately
      toast({ title: `${label} role activated`, description: "Opening your dashboard…" });
    } catch (e) {
      toast({
        title: "Couldn't activate the role",
        description: e instanceof ApiError ? e.message : "Please try again.",
        variant: "destructive",
      });
      setBusy(false);
    }
  };

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4 py-12">
      <Card className="max-w-lg w-full border-border">
        <CardContent className="p-8 text-center space-y-5">
          <div className="mx-auto h-14 w-14 rounded-2xl bg-primary/10 flex items-center justify-center">
            <Lock className="h-7 w-7 text-primary" />
          </div>

          <div>
            <h1 className="text-2xl font-bold text-foreground">{label} Access</h1>
            <p className="text-muted-foreground mt-2">
              {needsApplication
                ? `You don't have ${label} access yet. Submit a short application with your details and documents — our team reviews it and activates your ${label} role once approved.`
                : `You don't have the ${label} role yet. Activate it to open this dashboard.`}
            </p>
          </div>

          {needsApplication ? (
            <>
              <div className="rounded-lg border border-border bg-muted/30 p-4 text-left text-sm text-muted-foreground space-y-2">
                <div className="flex items-center gap-2 text-foreground font-medium">
                  <FileText className="h-4 w-4 text-primary" />
                  How activation works
                </div>
                <ol className="list-decimal list-inside space-y-1">
                  <li>Fill in the {label} application (details + required documents).</li>
                  <li>Our team reviews your submission.</li>
                  <li>On approval, your {label} role activates automatically and this dashboard opens.</li>
                </ol>
              </div>
              <Button size="lg" className="w-full gap-2" onClick={() => navigate(`/roles/apply/${role}`)}>
                <ShieldCheck className="h-4 w-4" />
                Request Access
                <ArrowRight className="h-4 w-4" />
              </Button>
            </>
          ) : (
            <Button size="lg" className="w-full gap-2" disabled={busy} onClick={becomeSelfServe}>
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <UserPlus className="h-4 w-4" /> Become {label}
                </>
              )}
            </Button>
          )}

          <Button variant="ghost" className="w-full" onClick={() => navigate("/")}>
            Back to Home
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export default RoleGate;
