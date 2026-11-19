import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import InvestmentModelSection from "./InvestmentModelSection";

describe("InvestmentModelSection (client letter, 2026-11-18)", () => {
  it("a ready property: rent + value growth, monthly rent, valuation updates, exit pricing", () => {
    render(<InvestmentModelSection ready />);
    expect(screen.getByTestId("model-ready")).toBeInTheDocument();
    expect(screen.queryByTestId("model-offplan")).toBeNull();
    expect(screen.getByText("Ready property")).toBeInTheDocument();
    expect(screen.getByText(/net annual rental yield and the growth in the property's market value/)).toBeInTheDocument();
    expect(screen.getByText(/paid into your wallet on the platform every month/)).toBeInTheDocument();
    expect(screen.getByText(/told by email and in your notifications/)).toBeInTheDocument();
  });

  it("under construction: the four drivers, the quarterly valuation and the exit", () => {
    render(<InvestmentModelSection ready={false} />);
    expect(screen.getByTestId("model-offplan")).toBeInTheDocument();
    for (const driver of [
      "Construction progress",
      "Rising release-phase prices",
      "Stepped prices offered to the platform",
      "Pre-launch purchase discount",
    ]) {
      expect(screen.getByText(driver)).toBeInTheDocument();
    }
    expect(screen.getByText(/issued every three months/)).toBeInTheDocument();
    expect(screen.getByText(/that is when the gain or loss is actually realised/)).toBeInTheDocument();
  });

  it("both show the journey from identity check to certificate, in order", () => {
    render(<InvestmentModelSection ready />);
    const steps = Array.from(screen.getByTestId("model-journey").querySelectorAll("li p.font-semibold")).map(
      (p) => p.textContent,
    );
    expect(steps).toEqual([
      "Verify your identity",
      "Buy your units",
      "Your certificate is issued",
      "Your units in Investments",
    ]);
  });
});
