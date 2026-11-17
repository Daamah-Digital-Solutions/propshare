import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import MobileBottomNav from "./MobileBottomNav";

vi.mock("@/components/ui/sidebar", () => ({ useSidebar: () => ({ toggleSidebar: vi.fn() }) }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ userRole: "investor" }) }));

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function mount(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MobileBottomNav />
      <Routes>
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("MobileBottomNav", () => {
  it("has six places in the client's order", () => {
    mount();
    const nav = screen.getByRole("navigation");
    const labels = Array.from(nav.querySelectorAll(":scope > div > a, :scope > div > button")).map((el) => el.textContent?.trim());
    expect(labels).toEqual(["Home", "Properties", "Dashboard", "Account", "Trade", "More"]);
    expect(screen.getByRole("link", { name: "Properties" })).toHaveAttribute("href", "/marketplace");
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("href", "/dashboard");
    expect(screen.queryByText("Exit")).toBeNull();
  });

  it("Trade opens a choice of the two markets, and a choice closes it and goes there", () => {
    mount("/dashboard");
    fireEvent.click(screen.getByTestId("nav-trade"));
    const sheet = screen.getByTestId("trade-sheet");
    expect(within(sheet).getByText("Trade")).toBeInTheDocument();
    expect(within(sheet).getByText("Buy and sell units with other investors and manage your offers.")).toBeInTheDocument();
    expect(within(sheet).getByText("Sell your units instantly to a liquidity provider at the platform price.")).toBeInTheDocument();

    fireEvent.click(within(sheet).getByRole("button", { name: /Liquidity Provider Market/ }));
    expect(screen.getByTestId("where")).toHaveTextContent("/liquidity-market");
    expect(screen.queryByTestId("trade-sheet")).toBeNull();
  });

  it("Trade stays lit on either market, and the current market is marked in the sheet", () => {
    mount("/secondary-market");
    const trade = screen.getByTestId("nav-trade");
    expect(trade.className).toContain("text-primary");
    fireEvent.click(trade);
    const sheet = screen.getByTestId("trade-sheet");
    expect(within(sheet).getByRole("button", { name: /Secondary Market/ })).toHaveAttribute("aria-current", "page");
    expect(within(sheet).getByRole("button", { name: /Liquidity Provider Market/ })).not.toHaveAttribute("aria-current");
  });

  it("Trade is not lit elsewhere", () => {
    mount("/dashboard");
    expect(screen.getByTestId("nav-trade").className).not.toContain("text-primary");
  });
});
