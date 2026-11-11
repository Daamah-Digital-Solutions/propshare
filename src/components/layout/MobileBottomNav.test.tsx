import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import MobileBottomNav from "./MobileBottomNav";

vi.mock("@/components/ui/sidebar", () => ({ useSidebar: () => ({ toggleSidebar: vi.fn() }) }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ userRole: "investor" }) }));

describe("MobileBottomNav", () => {
  it("has six places in the client's order, Trade leading to the secondary market", () => {
    render(
      <MemoryRouter>
        <MobileBottomNav />
      </MemoryRouter>,
    );
    const nav = screen.getByRole("navigation");
    const labels = Array.from(nav.querySelectorAll("a, button")).map((el) => el.textContent?.trim());
    expect(labels).toEqual(["Home", "Properties", "Dashboard", "Account", "Trade", "More"]);
    expect(screen.getByRole("link", { name: "Properties" })).toHaveAttribute("href", "/marketplace");
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("href", "/dashboard");
    expect(screen.getByRole("link", { name: "Trade" })).toHaveAttribute("href", "/secondary-market");
    expect(screen.queryByText("Exit")).toBeNull();
  });
});
