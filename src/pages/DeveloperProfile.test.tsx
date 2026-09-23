/**
 * Developer profile — reached from "View Profile" on a property page. Shows only what the
 * server returns: facts entered for the developer + live figures of its public listings.
 * An unfilled field is not rendered; an unknown developer gets an honest not-found page.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";

// `fail` makes the (plain async) fetcher throw: a vi.fn returning a rejected promise trips
// vitest's result tracking as an unhandled rejection even though react-query catches it.
const { get, fail, FakeApiError } = vi.hoisted(() => ({
  get: vi.fn(),
  fail: { error: null as Error | null },
  FakeApiError: class extends Error {
    code: string;
    status: number;
    constructor(code: string, message: string, status: number) {
      super(message);
      this.code = code;
      this.status = status;
    }
  },
}));

vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    ApiError: FakeApiError,
    developerApi: {
      get: async (s: string) => {
        if (fail.error) throw fail.error;
        return get(s);
      },
    },
  };
});

import DeveloperProfile from "./DeveloperProfile";

const summary = (id: string, title: string) => ({
  id,
  slug: `${id}-slug`,
  title,
  subtitle: null,
  location: "Dubai Marina, Dubai",
  country: "UAE",
  city: "Dubai",
  model: "ready-income",
  property_type: "apartment",
  status: "active",
  image: null,
  total_value: 100000,
  minimum_investment: 200,
  unit_price: 100,
  target_yield: 7,
  expected_yield: 7,
  capital_appreciation: 3,
  total_return: 10,
  funded_amount: 25000,
  funding_progress: 25,
  total_units: 1000,
  available_units: 750,
  investors_count: 12,
  developer_name: "Emaar Properties",
  developer_slug: "emaar-properties",
});

function mount(slug: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/developers/${slug}`]}>
        <Routes>
          <Route path="/developers/:slug" element={<DeveloperProfile />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DeveloperProfile", () => {
  beforeEach(() => {
    get.mockReset();
    fail.error = null;
  });

  it("renders the developer's facts, live figures and public listings", async () => {
    get.mockResolvedValue({
      slug: "emaar-properties",
      name: "Emaar Properties",
      logo: null,
      about: "Founded in 1997.\n\nDelivered 120 projects.",
      website: "https://www.emaar.com",
      rating: 4.6,
      projects_completed: 120,
      stats: { listings: 2, active: 1, funded: 1, total_raised: 125000, investors: 52 },
      properties: [summary("p1", "Marina Loft"), summary("p2", "Creek Tower")],
    });
    mount("emaar-properties");

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: "Emaar Properties" })).toBeInTheDocument(),
    );
    expect(get).toHaveBeenCalledWith("emaar-properties");
    expect(screen.getByText("Founded in 1997.")).toBeInTheDocument();
    expect(screen.getByText("Delivered 120 projects.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /emaar\.com/i })).toHaveAttribute(
      "href",
      "https://www.emaar.com",
    );
    const stats = screen.getByTestId("developer-stats");
    expect(stats).toHaveTextContent("$125,000");
    expect(stats).toHaveTextContent("52");
    expect(screen.getByText("Marina Loft")).toBeInTheDocument();
    expect(screen.getByText("Creek Tower")).toBeInTheDocument();
  });

  it("hides every field that was never entered instead of inventing it", async () => {
    get.mockResolvedValue({
      slug: "horizon",
      name: "Horizon",
      logo: null,
      about: null,
      website: null,
      rating: null,
      projects_completed: null,
      stats: { listings: 1, active: 1, funded: 0, total_raised: 0, investors: 0 },
      properties: [summary("p3", "Horizon One")],
    });
    mount("horizon");
    await waitFor(() => expect(screen.getByText("Horizon One")).toBeInTheDocument());
    expect(screen.queryByText(/About Horizon/)).toBeNull();
    expect(screen.queryByText(/projects completed/i)).toBeNull();
    expect(screen.queryByText(/\/ 5/)).toBeNull();
  });

  it("shows an honest not-found page for an unknown developer", async () => {
    fail.error = new FakeApiError("DEVELOPER_NOT_FOUND", "Developer not found.", 404);
    mount("nobody");
    await waitFor(() => expect(screen.getByTestId("developer-missing")).toBeInTheDocument());
    expect(screen.getByText("Developer not found")).toBeInTheDocument();
  });
});
