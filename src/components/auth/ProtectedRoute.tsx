import { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Clock } from "lucide-react";
import { useAuth, UserRole } from "@/contexts/AuthContext";
import { roleLabel } from "@/lib/roles";

interface ProtectedRouteProps {
  children: ReactNode;
  /** If set, the user's ACTIVE role must be one of these. Otherwise any
   *  authenticated user is allowed. Authorization is also enforced server-side
   *  on every API call — this guard is a UX layer, not the security boundary. */
  roles?: UserRole[];
}

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
    // Authenticated but the active role can't see this page. If the user holds a required role,
    // send them to switch; otherwise to their own dashboard.
    const canSwitch = roles.some((r) => authorizedRoles.includes(r));
    return (
      <Navigate
        to={canSwitch ? "/auth?switch=1" : "/"}
        replace
        state={{ from: location.pathname, needRoles: roles }}
      />
    );
  }

  return <>{children}</>;
}
