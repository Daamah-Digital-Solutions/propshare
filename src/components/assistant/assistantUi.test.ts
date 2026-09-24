import { describe, expect, it } from "vitest";
import { Building2, LogIn, UserPlus, Wallet } from "lucide-react";
import { greeting, linkIcon, pageStarters, toolLabel } from "./assistantUi";

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

  it("names the wallet preparation tools", () => {
    expect(toolLabel("prepare_deposit", "running")).toBe("Preparing your deposit…");
    expect(toolLabel("prepare_withdrawal", "ok")).toBe("Prepared your withdrawal");
    expect(toolLabel("prepare_statement", "ok")).toBe("Prepared your statement");
  });

  it("suggests questions about the page the user has open", () => {
    const member = pageStarters("/property/eval-tower", "", true);
    expect(member?.en).toContain("Prepare 10 units of this property");
    const visitor = pageStarters("/property/eval-tower", "", false);
    expect(visitor?.en.some((q) => /prepare/i.test(q))).toBe(false); // visitors cannot buy yet
    expect(pageStarters("/dashboard", "?tab=wallet", true)?.en).toContain(
      "Statement for the last 3 months (PDF)",
    );
    expect(pageStarters("/dashboard", "?tab=wallet", false)).toBeNull();
    expect(pageStarters("/dashboard", "?tab=returns", true)).toBeNull();
    expect(pageStarters("/marketplace", "", true)).toBeNull();
    const all = [member, visitor, pageStarters("/dashboard", "?tab=wallet", true)];
    for (const s of all) expect(s?.ar).toHaveLength(s?.en.length ?? -1);
  });

  it("greets by time of day and name", () => {
    expect(greeting("Sara", new Date(2026, 8, 24, 9))).toBe("Good morning, Sara");
    expect(greeting("Sara", new Date(2026, 8, 24, 15))).toBe("Good afternoon, Sara");
    expect(greeting(null, new Date(2026, 8, 24, 21))).toBe("Welcome to Capimax PropShare");
  });
});
