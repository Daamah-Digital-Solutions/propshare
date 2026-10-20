import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import LegalDisclaimer from "./LegalDisclaimer";

describe("LegalDisclaimer", () => {
  it("shows the client's disclaimer with links to the agreement and the privacy policy", () => {
    render(
      <MemoryRouter>
        <LegalDisclaimer />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Capimax PropShare Legal Disclaimer" })).toBeInTheDocument();
    expect(screen.getByText(/not a registered broker-dealer or investment adviser/)).toBeInTheDocument();
    expect(screen.getByText(/possible loss of some or all invested capital/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "User Agreement" })).toHaveAttribute("href", "/terms");
    expect(screen.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/privacy");
    expect(
      screen.getByText("Copyright © 2026 Capimax Real Estate Technologies LLC. All rights reserved."),
    ).toBeInTheDocument();
  });
});
