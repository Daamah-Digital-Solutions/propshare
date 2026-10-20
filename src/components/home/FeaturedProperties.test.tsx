import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import FeaturedProperties from "./FeaturedProperties";
import { assetUrl } from "@/lib/api";

const listMock = vi.fn();
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  propertyApi: { list: (...a: unknown[]) => listMock(...a) },
}));

describe("FeaturedProperties", () => {
  it("loads each card's photo from the API, where it is stored", async () => {
    const photo = "/api/v1/files/property-images/p1/cover.jpg";
    listMock.mockResolvedValue({
      items: [
        {
          id: "p1",
          title: "Aethera Coast Studio",
          location: "Mykonos",
          image: photo,
          model: "installment",
          status: "active",
          total_value: 470100,
          funded_amount: 17940,
          funding_progress: 3.82,
          minimum_investment: 100,
          unit_price: 100,
          available_units: 4021,
          total_units: 4701,
          expected_yield: 8,
        },
      ],
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <FeaturedProperties />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const img = await screen.findByAltText("Aethera Coast Studio");
    // a bare "/api/..." path would load from the website's own address and break
    expect(img).toHaveAttribute("src", assetUrl(photo));
    expect(img.getAttribute("src")).not.toBe(photo);
  });
});
