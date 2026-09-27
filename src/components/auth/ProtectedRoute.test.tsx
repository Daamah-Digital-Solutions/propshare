/**
 * A member who holds the role a page needs but is using another one is offered the switch
 * right there — the old redirect to /auth?switch=1 bounced straight back (an LP could never
 * reach the investor wallet and vice versa).
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

const { auth } = vi.hoisted(() => ({ auth: { current: {} as Record<string, unknown> } }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth.current }));
vi.mock("@/components/auth/RoleGate", () => ({
  RoleGate: ({ role }: { role: string }) => <div>gate {role}</div>,
}));

import { ProtectedRoute } from "./ProtectedRoute";

function Where() {
  const l = useLocation();
  return <div data-testid="where">{l.pathname + l.search}</div>;
}

function mount(url = "/dashboard") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute roles={["investor"]}>
              <div>investor page</div>
            </ProtectedRoute>
          }
        />
        <Route path="/auth" element={<div>auth page</div>} />
        <Route path="/liquidity-dashboard" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  it("offers the switch in place instead of bouncing through /auth", async () => {
    const switchActiveRole = vi.fn().mockResolvedValue(undefined);
    auth.current = {
      isAuthenticated: true,
      isLoading: false,
      userRole: "liquidity_provider",
      authorizedRoles: ["investor", "liquidity_provider"],
      pendingRoles: [],
      switchActiveRole,
    };
    mount();
    expect(screen.getByTestId("switch-role-card")).toHaveTextContent(/part of your Investor role/);
    expect(screen.queryByText("auth page")).toBeNull();
    expect(screen.getByRole("link", { name: /Back to my Liquidity Provider dashboard/ })).toHaveAttribute(
      "href",
      "/liquidity-dashboard",
    );
    fireEvent.click(screen.getByRole("button", { name: "Switch to Investor" }));
    await waitFor(() => expect(switchActiveRole).toHaveBeenCalledWith("investor"));
  });

  it("still sends a visitor to sign in", () => {
    auth.current = {
      isAuthenticated: false,
      isLoading: false,
      userRole: "guest",
      authorizedRoles: [],
      pendingRoles: [],
    };
    mount();
    expect(screen.getByText("auth page")).toBeInTheDocument();
  });

  it("opens the page for the right active role", () => {
    auth.current = {
      isAuthenticated: true,
      isLoading: false,
      userRole: "investor",
      authorizedRoles: ["investor"],
      pendingRoles: [],
    };
    mount();
    expect(screen.getByText("investor page")).toBeInTheDocument();
  });
});

describe("ProtectedRoute — the shared wallet", () => {
  it("opens a wallet link in the dashboard of the role in use, keeping its parameters", () => {
    auth.current = {
      isAuthenticated: true,
      isLoading: false,
      userRole: "liquidity_provider",
      authorizedRoles: ["investor", "liquidity_provider"],
      pendingRoles: [],
      switchActiveRole: vi.fn(),
    };
    mount("/dashboard?tab=wallet&action=deposit&amount=500");
    expect(screen.getByTestId("where").textContent).toBe(
      "/liquidity-dashboard?tab=wallet&action=deposit&amount=500",
    );
  });
});
