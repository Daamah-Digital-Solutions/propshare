/**
 * The family feed and the unit movements, in words: each line says who did what for whom,
 * from the side of the member reading it.
 */
import { describe, expect, it } from "vitest";
import type { FamilyActivityItem, UnitMovement } from "@/lib/api";
import { activityNote, activitySentence, movementText } from "./familyActivity";

const item = (over: Partial<FamilyActivityItem>): FamilyActivityItem => ({
  id: "x",
  kind: "transfer",
  direction: "out",
  at: "2026-10-02T10:00:00Z",
  counterparty: "Omar",
  from_name: null,
  property_id: "p1",
  property_title: "Marina Heights",
  units: 10,
  amount: null,
  fee: null,
  status: "completed",
  completed_at: "2026-10-02T10:00:00Z",
  relationship: null,
  ...over,
});

describe("activitySentence", () => {
  it("a transfer, from each side", () => {
    expect(activitySentence(item({}))).toBe("You transferred 10 units of Marina Heights to Omar");
    expect(activitySentence(item({ direction: "in", counterparty: "Ahmed Mansouri" }))).toBe(
      "Ahmed Mansouri transferred 10 units of Marina Heights to you",
    );
    expect(activitySentence(item({ units: 1 }))).toBe("You transferred 1 unit of Marina Heights to Omar");
  });

  it("an allocation that has not moved yet is not called a transfer", () => {
    expect(activitySentence(item({ status: "pending" }))).toBe("You allocated 10 units of Marina Heights to Omar");
    expect(activitySentence(item({ status: "cancelled" }))).toBe("You allocated 10 units of Marina Heights to Omar");
    expect(activityNote(item({ status: "pending" }))).toBe("Held in your account until they register and verify");
    expect(activityNote(item({ status: "pending", direction: "in" }))).toBe(
      "Moves to your account once your identity is verified",
    );
  });

  it("returns, allocated by the owner or kept from a distribution", () => {
    const returns = { kind: "returns" as const, units: null, property_title: null, amount: "300.00" };
    expect(activitySentence(item({ ...returns, status: "allocated" }))).toBe("You allocated $300.00 to Omar");
    expect(activitySentence(item({ ...returns, status: "allocated", direction: "in", counterparty: "Ahmed" }))).toBe(
      "Ahmed allocated $300.00 to you",
    );
    expect(activitySentence(item({ ...returns, status: "recorded" }))).toBe(
      "$300.00 of a distribution was kept for Omar",
    );
    expect(activityNote(item({ ...returns, status: "recorded" }))).toBe("Released when their identity is verified");
  });

  it("a member added, from each side", () => {
    const member = { kind: "member" as const, units: null, property_title: null, relationship: "Son" };
    expect(activitySentence(item({ ...member }))).toBe("You added Omar (Son) to your family group");
    expect(activitySentence(item({ ...member, direction: "in", counterparty: "Ahmed" }))).toBe(
      "Ahmed added you to their family group as Son",
    );
  });

  it("says when an allocation was received later, and what a transfer cost", () => {
    expect(activityNote(item({}))).toBeNull();
    expect(activityNote(item({ completed_at: "2026-10-09T08:00:00Z", fee: "12.50" }))).toBe(
      "received Oct 9, 2026 · transfer fee $12.5",
    );
  });
});

describe("movementText", () => {
  const movement = (over: Partial<UnitMovement>): UnitMovement => ({
    id: "m",
    at: "2026-10-02T10:00:00Z",
    property_id: "p1",
    property_title: "Marina Heights",
    units: 10,
    direction: "in",
    reason: "family_transfer_in",
    label: "Received from a family member",
    counterparty: "Ahmed Mansouri",
    ...over,
  });

  it("names the other person, on the right side of the movement", () => {
    expect(movementText(movement({}))).toBe("Received from a family member · from Ahmed Mansouri");
    expect(
      movementText(movement({ units: -10, direction: "out", label: "Transferred to a family member", counterparty: "Omar" })),
    ).toBe("Transferred to a family member · to Omar");
    expect(movementText(movement({ label: "Purchase", counterparty: null }))).toBe("Purchase");
  });
});
