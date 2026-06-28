import { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth, UserRole } from "@/contexts/AuthContext";

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
  const { isAuthenticated, isLoading, userRole, authorizedRoles } = useAuth();
  const location = useLocation();

  if (isLoading) return <Spinner />;

  if (!isAuthenticated) {
    return <Navigate to="/auth" replace state={{ from: location.pathname }} />;
  }

  if (roles && roles.length > 0 && !roles.includes(userRole)) {
    // Authenticated but the active role can't see this page. If the user holds
    // a required role, send them to switch; otherwise to their own dashboard.
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
