import { describe, expect, it } from "vitest";
import { Building2, LogIn, UserPlus, Wallet } from "lucide-react";
import { greeting, linkIcon, toolLabel } from "./assistantUi";

describe("assistant UI helpers", () => {
  it("names tool work in plain language, never the raw tool name", () => {
    expect(toolLabel("get_my_wallet", "running")).toBe("Checking your wallet…");
    expect(toolLabel("get_my_wallet", "ok")).toBe("Checked your wallet");
    expect(toolLabel("search_reference", "ok")).toBe("Read company documents");
    expect(toolLabel("get_my_wallet", "error")).toBe("Couldn't check: checked your wallet");
    expect(toolLabel("get_future_thing", "ok")).toBe("Future thing"); // unknown tools still read well
  });

  it("gives each page button a matching icon", () => {
    expect(linkIcon("/auth")).toBe(LogIn);
    expect(linkIcon("/auth?tab=register")).toBe(UserPlus);
    expect(linkIcon("/dashboard?tab=wallet")).toBe(Wallet);
    expect(linkIcon("/property/creek-tower")).toBe(Building2);
  });

  it("greets by time of day and name", () => {
    expect(greeting("Sara", new Date(2026, 8, 24, 9))).toBe("Good morning, Sara");
    expect(greeting("Sara", new Date(2026, 8, 24, 15))).toBe("Good afternoon, Sara");
    expect(greeting(null, new Date(2026, 8, 24, 21))).toBe("Welcome to Capimax");
  });
});
