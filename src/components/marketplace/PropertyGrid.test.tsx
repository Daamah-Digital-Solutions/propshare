/**
 * Go-live audit, Step 1: every ownership model must open the data-driven property page.
 * Before the fix, installment / future / option / shared-development cards linked to
 * `/advanced-property/<model>` — a model-keyed demo page that showed the NEWEST property of
 * that model (not the clicked one) with fabricated SPV/valuation/document content.
 */
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";
import PropertyGrid from "./PropertyGrid";
import type { Property } from "@/pages/Marketplace";

const MODELS = [
  "ready-income",
  "ready-portfolio",
  "installment",
  "future",
  "option",
  "shared-development",
  "construction-portfolio",
] as const;

const prop = (i: number, model: (typeof MODELS)[number]): Property => ({
  id: `id-${i}`,
  slug: `slug-${i}`,
  title: `Property ${i}`,
  location: "London",
  country: "UK",
  city: "London",
  image: "",
  price: 1000000,
  minInvestment: 100,
  yield: 7,
  funded: 10,
  type: "apartment",
  status: "open",
  propertyStatus: model.startsWith("ready") ? "ready" : "construction",
  ownershipModel: model,
  investors: 3,
  daysLeft: 0,
  developer: "Dev",
});

describe("PropertyGrid routing", () => {
  it("links every ownership model to /property/:slug (never to the demo page)", () => {
    const properties = MODELS.map((m, i) => prop(i, m));
    const { container } = render(
      <MemoryRouter>
        <PropertyGrid properties={properties} viewMode="grid" />
      </MemoryRouter>,
    );
    const hrefs = Array.from(container.querySelectorAll("a[href]")).map((a) => a.getAttribute("href"));
    expect(hrefs.some((h) => h?.includes("/advanced-property/"))).toBe(false);
    for (let i = 0; i < MODELS.length; i++) {
      expect(hrefs).toContain(`/property/slug-${i}`);
    }
  });

  it("never shows a fake 'Completed' or days-left pill when no deadline exists", () => {
    const { container } = render(
      <MemoryRouter>
        <PropertyGrid properties={[prop(1, "ready-income")]} viewMode="grid" />
      </MemoryRouter>,
    );
    expect(container.textContent).not.toMatch(/Completed|days left/);
  });
});
