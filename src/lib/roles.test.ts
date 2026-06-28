import { describe, it, expect } from "vitest";
import { requestableRoles, roleLabel } from "@/lib/roles";

describe("requestableRoles (self-serve role acquisition, D12)", () => {
  it("offers owner + broker + liquidity_provider to a brand-new investor", () => {
    const opts = requestableRoles(["investor"]);
    expect(opts.map((o) => o.role)).toEqual(["owner", "broker", "liquidity_provider"]);
  });

  it("marks owner self-serve and broker/LP approval", () => {
    const opts = requestableRoles(["investor"]);
    expect(opts.find((o) => o.role === "owner")?.kind).toBe("self-serve");
    expect(opts.find((o) => o.role === "broker")?.kind).toBe("approval");
    expect(opts.find((o) => o.role === "liquidity_provider")?.kind).toBe("approval");
  });

  it("drops roles already held", () => {
    expect(requestableRoles(["investor", "owner"]).map((o) => o.role)).toEqual([
      "broker",
      "liquidity_provider",
    ]);
  });

  it("never offers admin and returns empty when all roles are held", () => {
    const opts = requestableRoles(["investor", "owner", "broker", "liquidity_provider", "admin"]);
    expect(opts).toEqual([]);
  });

  it("roleLabel humanizes known roles and passes through unknowns", () => {
    expect(roleLabel("liquidity_provider")).toBe("Liquidity Provider");
    expect(roleLabel("owner")).toBe("Property Owner");
    expect(roleLabel("weird")).toBe("weird");
  });
});
