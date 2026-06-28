/**
 * Guards the Phase 12 bell: the unread badge is the LIVE count from notificationApi
 * (the hardcoded "3" is gone), and it's hidden when there are no unread notifications.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi } from "vitest";
import { MainLayout } from "./MainLayout";

const unreadMock = vi.fn();

vi.mock("@/lib/api", () => ({
  notificationApi: { unreadCount: (...a: unknown[]) => unreadMock(...a) },
}));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
vi.mock("./AppSidebar", () => ({ AppSidebar: () => <div /> }));
vi.mock("./MobileBottomNav", () => ({ default: () => <div /> }));
vi.mock("./DevelopmentNoticeBanner", () => ({ DevelopmentNoticeBanner: () => <div /> }));

function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MainLayout>
          <div>content</div>
        </MainLayout>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MainLayout bell", () => {
  it("shows the live unread count, not a hardcoded 3", async () => {
    unreadMock.mockResolvedValue({ count: 5 });
    renderIt();
    expect(await screen.findByText("5")).toBeInTheDocument();
    expect(screen.queryByText("3")).toBeNull();
  });

  it("hides the badge when there are no unread notifications", async () => {
    unreadMock.mockResolvedValue({ count: 0 });
    renderIt();
    const bell = await screen.findByRole("button", { name: /Notifications/i });
    expect(bell.querySelector("span")).toBeNull();
  });
});
