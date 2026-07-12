import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from "react";
import { authApi, MeResponse, refreshAccessToken, setAccessToken } from "@/lib/api";

export type UserRole =
  | "guest"
  | "investor"
  | "owner"
  | "broker"
  | "liquidity_provider"
  | "admin";

interface AuthContextType {
  user: MeResponse | null;
  /** The current ACTIVE role (or "guest" when unauthenticated). Read-only. */
  userRole: UserRole;
  /** Roles the user is authorized to switch to (from the backend). */
  authorizedRoles: UserRole[];
  /** Roles with a pending admin approval request — grants read-only preview access. */
  pendingRoles: UserRole[];
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: {
    email: string;
    password: string;
    full_name?: string;
    phone?: string;
    referral_code?: string;
  }) => Promise<void>;
  signOut: () => Promise<void>;
  /** Switch active role. The backend rejects any role not authorized for the user. */
  switchActiveRole: (role: UserRole) => Promise<void>;
  /** Request a new role: self-serve (investor/owner) is granted; others queue for admin. */
  requestRole: (role: UserRole) => Promise<{ status: string; role: string }>;
  /** Submit a Broker / Liquidity-Provider join application (fields + documents). */
  applyForRole: (
    role: UserRole,
    fields: Record<string, string>,
    documents: { label: string; file: File }[],
  ) => Promise<{ status: string; role: string; request_id: string }>;
  /** Reload the current user from the backend. */
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const applyMe = useCallback((me: MeResponse | null) => setUser(me), []);

  const loadMe = useCallback(async () => {
    try {
      const me = await authApi.me();
      applyMe(me);
    } catch {
      applyMe(null);
    }
  }, [applyMe]);

  useEffect(() => {
    // On boot, try to mint an access token from the httpOnly refresh cookie.
    let cancelled = false;
    (async () => {
      const ok = await refreshAccessToken();
      if (!cancelled) {
        if (ok) await loadMe();
        setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadMe]);

  const login = useCallback(async (email: string, password: string) => {
    const me = await authApi.login(email, password);
    setUser(me);
  }, []);

  const register = useCallback(
    async (input: {
      email: string;
      password: string;
      full_name?: string;
      phone?: string;
      referral_code?: string;
    }) => {
      const me = await authApi.register(input);
      setUser(me);
    },
    [],
  );

  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const switchActiveRole = useCallback(
    async (role: UserRole) => {
      // Persist the new active role, then MINT A FRESH TOKEN that carries it: active_role lives
      // inside the JWT, so without a refresh the API keeps seeing the old role and rejects owner/
      // broker/etc. actions with "activate <role>" even though the switch "succeeded" client-side.
      await authApi.switchRole(role);
      const ok = await refreshAccessToken();
      if (ok) await loadMe();
    },
    [loadMe],
  );

  const requestRole = useCallback(
    async (role: UserRole) => {
      const result = await authApi.requestRole(role);
      // Self-serve grants take effect immediately — reload roles.
      await loadMe();
      return result;
    },
    [loadMe],
  );

  const applyForRole = useCallback(
    async (
      role: UserRole,
      fields: Record<string, string>,
      documents: { label: string; file: File }[],
    ) => {
      const result = await authApi.applyForRole(role, fields, documents);
      await loadMe(); // reflect the now-pending role (enables preview access)
      return result;
    },
    [loadMe],
  );

  const activeRole = (user?.active_role as UserRole | undefined) ?? "guest";
  const authorizedRoles = (user?.roles as UserRole[] | undefined) ?? [];
  const pendingRoles = (user?.pending_roles as UserRole[] | undefined) ?? [];

  return (
    <AuthContext.Provider
      value={{
        user,
        userRole: user ? activeRole : "guest",
        authorizedRoles,
        pendingRoles,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        signOut,
        switchActiveRole,
        requestRole,
        applyForRole,
        refresh: loadMe,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
};
