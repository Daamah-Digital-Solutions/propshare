import { ReactNode, useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { Clock, Repeat } from "lucide-react";
import { useAuth, UserRole } from "@/contexts/AuthContext";
import { applicationRoles, roleHome, roleLabel } from "@/lib/roles";
import { RoleGate } from "@/components/auth/RoleGate";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface ProtectedRouteProps {
  children: ReactNode;
  /** If set, the user's ACTIVE role must be one of these. Otherwise any
   *  authenticated user is allowed. Authorization is also enforced server-side
   *  on every API call — this guard is a UX layer, not the security boundary. */
  roles?: UserRole[];
}

// roles whose own dashboard has a wallet tab (?tab=wallet)
const WALLET_DASHBOARD_ROLES = new Set<string>(["owner", "broker", "liquidity_provider"]);

const Spinner = () => (
  <div className="flex items-center justify-center min-h-[60vh]">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
  </div>
);

export function ProtectedRoute({ children, roles }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, userRole, authorizedRoles, pendingRoles } = useAuth();
  const location = useLocation();

  if (isLoading) return <Spinner />;

  if (!isAuthenticated) {
    return <Navigate to="/auth" replace state={{ from: location.pathname }} />;
  }

  // The wallet is one per member, shared by every role, and each role's dashboard has it. A
  // wallet link to the investor dashboard (an assistant card, an older checkout return URL)
  // opens the wallet of the dashboard the member is using instead of a role wall.
  if (
    roles &&
    !roles.includes(userRole) &&
    location.pathname === "/dashboard" &&
    new URLSearchParams(location.search).get("tab") === "wallet" &&
    WALLET_DASHBOARD_ROLES.has(userRole)
  ) {
    return <Navigate to={`${roleHome(userRole)}${location.search}`} replace />;
  }

  if (roles && roles.length > 0 && !roles.includes(userRole)) {
    // Task 12 — preview access: a user whose application for a required role is still pending
    // may browse that role's area READ-ONLY (with a banner), instead of being bounced. Real
    // actions stay gated server-side until the admin approves.
    const previewing = roles.find((r) => pendingRoles.includes(r));
    if (previewing) {
      return (
        <div>
          <div className="flex items-center justify-center gap-2 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-center text-sm text-amber-700">
            <Clock className="h-4 w-4 shrink-0" />
            <span>
              You're previewing the <strong>{roleLabel(previewing)}</strong> area — your
              application is pending admin approval. Some actions stay locked until it's approved.
            </span>
          </div>
          {children}
        </div>
      );
    }
    // Authenticated but the active role can't see this page. If the user already HOLDS a
    // required role, send them to switch it. Otherwise, show a Role Gate that explains the
    // access requirement and offers "Request Access" (approval roles) / "Become" (self-serve)
    // — instead of silently bouncing them home with no way forward.
    const held = roles.find((r) => authorizedRoles.includes(r));
    if (held) {
      return <SwitchRoleCard need={held} current={userRole} />;
    }
    const target = roles.find((r) => applicationRoles().includes(r)) ?? roles[0];
    return <RoleGate role={target} />;
  }

  return <>{children}</>;
}

/** The member holds the role this page needs but is using another one right now: switch in
 * place (the page then opens), or go back to the dashboard of the role they are using. */
function SwitchRoleCard({ need, current }: { need: UserRole; current: UserRole }) {
  const { switchActiveRole } = useAuth();
  const [switching, setSwitching] = useState(false);
  const [failed, setFailed] = useState(false);
  const onSwitch = async () => {
    setSwitching(true);
    setFailed(false);
    try {
      await switchActiveRole(need);
    } catch {
      setFailed(true);
    } finally {
      setSwitching(false);
    }
  };
  return (
    <div className="container mx-auto px-4 py-16 flex justify-center">
      <Card className="max-w-md w-full" data-testid="switch-role-card">
        <CardContent className="p-6 space-y-4 text-center">
          <Repeat className="h-8 w-8 text-primary mx-auto" />
          <h2 className="text-lg font-semibold">This page is part of your {roleLabel(need)} role</h2>
          <p className="text-sm text-muted-foreground">
            You are using the platform as {roleLabel(current)} right now. Switch to open it — you
            can switch back anytime from the sidebar.
          </p>
          {failed && <p className="text-sm text-destructive">The switch did not go through. Please try again.</p>}
          <div className="flex flex-col sm:flex-row gap-2 justify-center">
            <Button onClick={onSwitch} disabled={switching}>
              {switching ? "Switching…" : `Switch to ${roleLabel(need)}`}
            </Button>
            <Button asChild variant="outline">
              <Link to={roleHome(current)}>Back to my {roleLabel(current)} dashboard</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
