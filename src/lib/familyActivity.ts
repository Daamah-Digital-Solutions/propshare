/**
 * The family activity feed and the unit movements, in words. Kept apart from the components
 * that draw them so the sentences can be tested on their own.
 */
import type { FamilyActivityItem, UnitMovement } from "@/lib/api";

export const shortDay = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }) : "";

const units = (n: number | null) => `${n ?? 0} unit${n === 1 ? "" : "s"}`;
const money = (amount: string | null) =>
  `$${Number(amount ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** One line of the family feed: who did what for whom. */
export function activitySentence(i: FamilyActivityItem): string {
  const what = `${units(i.units)}${i.property_title ? ` of ${i.property_title}` : ""}`;
  if (i.kind === "transfer") {
    const verb = i.status === "completed" ? "transferred" : "allocated";
    if (i.direction === "out") return `You ${verb} ${what} to ${i.counterparty}`;
    if (i.direction === "in") return `${i.counterparty} ${verb} ${what} to you`;
    return `${i.from_name ?? "A family member"} ${verb} ${what} to ${i.counterparty}`;
  }
  if (i.kind === "returns") {
    // recorded: a share of a distribution the platform kept for a member not verified yet
    const recorded = i.status === "recorded";
    if (i.direction === "out") {
      return recorded
        ? `${money(i.amount)} of a distribution was kept for ${i.counterparty}`
        : `You allocated ${money(i.amount)} to ${i.counterparty}`;
    }
    return recorded
      ? `${i.counterparty} keeps ${money(i.amount)} of a distribution for you`
      : `${i.counterparty} allocated ${money(i.amount)} to you`;
  }
  if (i.direction === "in") {
    return `${i.counterparty} added you to their family group${i.relationship ? ` as ${i.relationship}` : ""}`;
  }
  return `You added ${i.counterparty}${i.relationship ? ` (${i.relationship})` : ""} to your family group`;
}

/** What a line still waits for, or what else there is to say about it. */
export function activityNote(i: FamilyActivityItem): string | null {
  if (i.kind === "transfer" && i.status === "pending") {
    return i.direction === "in"
      ? "Moves to your account once your identity is verified"
      : "Held in your account until they register and verify";
  }
  if (i.kind === "transfer" && i.status === "completed") {
    const parts: string[] = [];
    if (i.completed_at && shortDay(i.completed_at) !== shortDay(i.at)) parts.push(`received ${shortDay(i.completed_at)}`);
    if (i.fee) parts.push(`transfer fee $${Number(i.fee).toLocaleString()}`);
    return parts.length ? parts.join(" · ") : null;
  }
  if (i.kind === "returns" && i.status === "recorded") return "Released when their identity is verified";
  return null;
}

/** A unit movement with the other person named: "Received from a family member · from Ahmed". */
export function movementText(m: UnitMovement): string {
  return m.counterparty ? `${m.label} · ${m.direction === "in" ? "from" : "to"} ${m.counterparty}` : m.label;
}
