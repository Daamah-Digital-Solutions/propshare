import { describe, it, expect } from "vitest";
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { useNumberDraft } from "./useNumberDraft";

function Field({ start = 105, min = 105, max = 5000, integer = false }) {
  const [value, setValue] = useState(start);
  const field = useNumberDraft({ value, onValueChange: setValue, min, max, integer });
  return (
    <>
      <input type="number" aria-label="amount" {...field.inputProps} />
      <output data-testid="value">{value}</output>
      <button onClick={() => setValue(300)}>slider</button>
    </>
  );
}

const input = () => screen.getByLabelText("amount") as HTMLInputElement;
const value = () => screen.getByTestId("value").textContent;
const type = (t: string) => fireEvent.change(input(), { target: { value: t } });

describe("useNumberDraft", () => {
  it("lets the field be cleared and a new number typed (the minimum does not come back)", () => {
    render(<Field />);
    type("");
    expect(input().value).toBe(""); // stays empty, not 105 again
    expect(value()).toBe("105"); // the page keeps the last good number meanwhile
    type("2");
    expect(input().value).toBe("2"); // not "1052"
    type("25");
    type("250");
    expect(value()).toBe("250");
    expect(input()).not.toHaveAttribute("aria-invalid");
  });

  it("corrects a number out of range on leaving the field, and an empty field goes back", () => {
    render(<Field />);
    type("20");
    expect(input()).toHaveAttribute("aria-invalid", "true");
    expect(value()).toBe("105");
    fireEvent.blur(input());
    expect(input().value).toBe("105");

    type("99999");
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(input().value).toBe("5000");
    expect(value()).toBe("5000");

    type("");
    fireEvent.blur(input());
    expect(input().value).toBe("5000");
  });

  it("shows a number set from outside (the slider)", () => {
    render(<Field />);
    fireEvent.click(screen.getByText("slider"));
    expect(input().value).toBe("300");
  });

  it("keeps units whole", () => {
    render(<Field start={1} min={1} max={10} integer />);
    type("");
    type("7");
    expect(value()).toBe("7");
    type("2.6");
    expect(value()).toBe("7"); // not a whole number: waits
    fireEvent.blur(input());
    expect(input().value).toBe("3");
    expect(value()).toBe("3");
  });
});
