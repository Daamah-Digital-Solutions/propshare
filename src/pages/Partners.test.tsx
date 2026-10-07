/**
 * The Partners page shows the client's partner register (technical content brief, 2026): seven
 * sections, each partner with its role, its copy, its market, its own logo and a link that
 * opens its site in a new tab. Before this the page listed placeholder companies over stock
 * photographs.
 */
import { readFileSync } from "node:fs";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import Partners from "./Partners";
import { PARTNERS, PARTNER_SECTIONS } from "@/lib/partners";

// the register, in the brief's order: section -> [name, role, market, link]
const REGISTER: [string, [string, string | null, string, string | null][]][] = [
  [
    "Payments and Digital Asset Payments",
    [
      ["Stripe", "Integrated payment provider", "Global", "https://stripe.com"],
      ["PayPal", "Integrated payment provider", "Global", "https://www.paypal.com"],
      ["NOWPayments", "Crypto payment provider", "Global", "https://nowpayments.io"],
    ],
  ],
  [
    "Identity Verification and Compliance",
    [["Sumsub", "Compliance integration", "Global", "https://sumsub.com"]],
  ],
  [
    "Banking and Treasury Rails",
    [
      ["Mercury", "Business account rail", "United States", "https://mercury.com"],
      ["Revolut Business", "Business account rail", "International", "https://www.revolut.com/business"],
      ["Wise Business", "Business payment rail", "International", "https://wise.com/business"],
      // a category that fills as banks are approved, not a company: no role, no site
      ["Other Approved Banks", null, "Multiple jurisdictions", null],
    ],
  ],
  [
    "Finance, Valuation, Legal and Risk",
    [
      ["Nova Digital Finance", "Financing", "Capimax ecosystem", "https://novadf.com"],
      [
        "CIM Global Financial",
        "Financial advisory and valuation",
        "United Kingdom and United States",
        "https://www.cimglobalfinancial.com",
      ],
      // the brief's lexcrestglobal.com does not exist: the firm's own site
      ["LexCrest Global Legal", "Legal and due diligence", "Global", "https://lexcrestlegal.xyz"],
    ],
  ],
  [
    "Insurance and Asset Protection",
    [
      ["CoverTech Insurance", "Insurance and risk", "Global", "https://www.covertechinsurance.com"],
      ["Assurax Insurance", "Insurance and risk", "International", "https://assuraxinsurance.com"],
    ],
  ],
  [
    "Real Estate Development Partners",
    [
      ["Westoria Capital Estates", "Developer", "United States", "https://westoriacapital.com"],
      ["Crestmark Global", "Developer", "United Kingdom", "https://crestmarkglobal.com"],
      ["Valora Estates Global", "Developer", "Spain", "https://valoraestatesglobal.com"],
      ["Verdea Estates", "Developer", "Georgia", "https://verdeaestates.com"],
      ["Aethera Development", "Developer", "Greece", "https://aetheradevelopment.com"],
      ["Elevate Properties Pte. Ltd", "Developer", "Singapore", "https://elevateproperties.world"],
      ["Prime Stone Global", "Developer", "South Africa", "https://primestoneglobal.dev"],
    ],
  ],
  [
    "Hospitality, Property and Facility Management",
    [
      ["Priminn Hotels", "Hospitality operator", "International", "https://priminnhotels.com"],
      ["Elite Gate Properties", "Property management", "International", "https://elitegateproperties.com"],
      ["Crown Facilities", "Facility management", "Global", "https://crownfm.online"],
    ],
  ],
];

const mount = () =>
  render(
    <MemoryRouter>
      <Partners />
    </MemoryRouter>,
  );

describe("Partners page", () => {
  it("lists the register's sections and partners, in its order", () => {
    mount();
    const sections = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(sections).toEqual([...REGISTER.map(([title]) => title), "Become a Partner"]);
    const names = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(names).toEqual(REGISTER.flatMap(([, partners]) => partners.map(([name]) => name)));
    expect(names).toHaveLength(23);
  });

  it("gives each partner its role, its market and a link to its own site in a new tab", () => {
    mount();
    REGISTER.forEach(([title, partners], s) => {
      const section = screen.getByTestId(`partners-${PARTNER_SECTIONS[s].key}`);
      expect(within(section).getByRole("heading", { level: 2 })).toHaveTextContent(title);
      const cards = within(section).getAllByRole("listitem");
      expect(cards).toHaveLength(partners.length);
      partners.forEach(([name, role, market, url], i) => {
        const card = cards[i];
        expect(within(card).getByRole("heading", { level: 3 })).toHaveTextContent(name);
        expect(card).toHaveTextContent(market);
        if (role) expect(card).toHaveTextContent(role);
        const links = within(card).queryAllByRole("link");
        if (url === null) {
          expect(links).toHaveLength(0);
          return;
        }
        expect(links).toHaveLength(1);
        expect(links[0]).toHaveAttribute("href", url);
        expect(links[0]).toHaveAttribute("target", "_blank");
        expect(links[0]).toHaveAttribute("rel", "noopener noreferrer");
      });
    });
  });

  it("says what each partner does, in the register's words, and where its link goes", () => {
    mount();
    const stripe = screen.getByTestId("partner-stripe");
    expect(stripe).toHaveTextContent(
      "Payment infrastructure for card and online payments, checkout, billing and transaction processing.",
    );
    expect(within(stripe).getByRole("link")).toHaveAccessibleName("Stripe website: stripe.com");
    expect(screen.getByTestId("partner-revolut-business")).toHaveTextContent("revolut.com/business");
    expect(screen.getByTestId("partner-cim-global-financial")).toHaveTextContent(
      "Financial studies, asset valuation, risk assessment, due diligence support, reporting and document verification.",
    );
    const banks = screen.getByTestId("partner-other-approved-banks");
    expect(banks).toHaveTextContent(
      "Additional banks and payment institutions may be displayed only after onboarding, approval and documentary verification.",
    );
    expect(banks).not.toHaveTextContent("Dynamic category");
    // the two newest developers, said as the others are
    expect(screen.getByTestId("partner-elevate-properties")).toHaveTextContent(
      "Real-estate development partner supporting selected opportunities in Singapore.",
    );
    expect(screen.getByTestId("partner-prime-stone-global")).toHaveTextContent(
      "Real-estate development partner supporting selected opportunities in South Africa.",
    );
  });

  it("shows each partner's own logo, none of them a stock photograph", () => {
    mount();
    const logos = screen.getAllByRole("img");
    expect(logos).toHaveLength(23);
    PARTNERS.forEach((partner, i) => {
      expect(logos[i]).toHaveAttribute("alt", `${partner.name} logo`);
      expect(logos[i].getAttribute("src")).toContain(`/partners/${partner.key}.webp`);
      expect(logos[i].getAttribute("src")).not.toMatch(/^https?:/);
    });
    expect(new Set(PARTNERS.map((p) => p.logo)).size).toBe(23);
    expect(new Set(PARTNERS.map((p) => p.key)).size).toBe(23);
  });

  it("no longer lists the placeholder companies, nor the entry meant for other platforms", () => {
    mount();
    for (const gone of [
      "TDH Development",
      "Capimax Development",
      "CIM Financial Group",
      "Capimax Financial Management",
      "HCC International Insurance",
      "Nova Property Management",
      // in the brief for the ecosystem's other platforms; here it is on the Verification Center
      "Proof Anchor",
    ]) {
      expect(screen.queryByText(gone)).toBeNull();
    }
    expect(document.body.innerHTML).not.toContain("unsplash");
  });

  it("names every partner the assistant's copy of the register names", () => {
    // the assistant answers from this file: the page and it must name the same partners
    const register = readFileSync("backend/app/knowledge/reference/partners_register_2026.md", "utf8");
    for (const partner of PARTNERS) {
      expect(register, partner.name).toContain(partner.name);
    }
    // its partner rows: an empty Logo cell, then the name
    const rows = register.match(/^\|\s+\|\s+[A-Za-z*]/gm) ?? [];
    expect(rows).toHaveLength(PARTNERS.length);
  });
});
