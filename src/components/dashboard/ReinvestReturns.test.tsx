/**
 * Regression (review 2026-09-24): the dashboard's Reinvest tab passed a fixed
 * `availableReturns={19000}`, so every investor saw $19,000 of "available returns" whatever
 * they had earned. The tab now uses the member's own figure from the portfolio API.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi } from "vitest";
import dashboardSource from "@/pages/InvestorDashboard.tsx?raw";

vi.mock("@/lib/api", () => ({
  investApi: {
    portfolio: async () => ({ total_returns: "1234.50" }),
    reinvestSettings: async () => ({ discount_pct: "5.0" }),
  },
}));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

import { ReinvestReturns } from "./ReinvestReturns";
import { ReinvestProvider } from "@/contexts/ReinvestContext";

describe("ReinvestReturns", () => {
  it("shows the member's own returns from the server", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ReinvestProvider>
            <ReinvestReturns />
          </ReinvestProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect((await screen.findAllByText("$1,234.5")).length).toBeGreaterThan(0);
    expect(screen.queryByText("$19,000")).toBeNull();
  });

  it("is never handed a made-up amount by the dashboard", () => {
    expect(dashboardSource).not.toMatch(/availableReturns=\{\d/);
  });
});
