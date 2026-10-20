import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import Footer from "./Footer";

describe("Footer", () => {
  it("keeps every link and contact detail, with the legal disclaimer before the copyright", () => {
    render(
      <MemoryRouter>
        <Footer />
      </MemoryRouter>,
    );
    const footer = screen.getByRole("contentinfo");
    for (const name of [
      "Browse Properties",
      "How It Works",
      "Secondary Market",
      "Fees",
      "About Capimax PropShare",
      "Verification Center",
      "Partners",
      "Platform Rules",
      "Terms & Conditions",
      "Risk Disclosure",
      "Compliance",
      "Help Center",
      "FAQ",
      "Contact Us",
      "Disclaimer",
    ]) {
      expect(within(footer).getByRole("link", { name })).toBeInTheDocument();
    }
    expect(footer).toHaveTextContent("support@capimaxpropshare.com");
    expect(footer).toHaveTextContent("+44 7577 370309");
    expect(footer).toHaveTextContent("Dover, Kent, DE 19901");
    const disclaimer = within(footer).getByTestId("home-legal-disclaimer");
    expect(disclaimer).toHaveTextContent(/not a registered broker-dealer/);
    // the copyright comes last, after the disclaimer
    const copyright = within(footer).getByText(
      "Copyright © 2026 Capimax Real Estate Technologies LLC. All rights reserved.",
    );
    expect(disclaimer.compareDocumentPosition(copyright) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(footer).not.toHaveTextContent(/Regulated by/);
  });
});
