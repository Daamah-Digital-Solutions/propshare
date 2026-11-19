/**
 * "Investment Strategy" on the property page (client, 2026-11-19): a button that opens a fixed
 * text chosen by the property's type.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { InvestmentStrategyButton } from "./InvestmentStrategyButton";

describe("InvestmentStrategyButton", () => {
  it("a ready property: rental income, then price and value over time", async () => {
    render(<InvestmentStrategyButton ready />);
    fireEvent.click(screen.getByTestId("investment-strategy"));
    const text = await screen.findByTestId("investment-strategy-text");
    expect(text).toHaveTextContent(/potential rental income from operating the property/);
    expect(text).toHaveTextContent(/price to rise/);
    expect(screen.getByRole("dialog")).toHaveTextContent("Ready Property");
  });

  it("under construction: value as construction advances, milestones, schedule, handover, exit", async () => {
    render(<InvestmentStrategyButton ready={false} />);
    fireEvent.click(screen.getByRole("button", { name: /Investment Strategy/ }));
    const text = await screen.findByTestId("investment-strategy-text");
    expect(text).toHaveTextContent(/as construction advances, until it is complete/);
    expect(text).toHaveTextContent(/installment schedule when one is available/);
    expect(text).toHaveTextContent(/handover dates and the exit options available/);
    expect(text).not.toHaveTextContent(/rental income/);
  });
});
