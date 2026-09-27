/**
 * How an owner reads the state of a listing they submitted.
 *
 * The server keeps the real lifecycle (draft → under_review → active / funded / closed) plus
 * the last review decision; an owner must never see a submission still being reviewed as
 * "Funding".
 */
export type OwnerStatusTone = "live" | "waiting" | "action" | "done" | "stopped";

export interface OwnerStatusInput {
  status: string;
  submitted_at?: string | null;
  review_outcome?: string | null;
}

export interface OwnerStatus {
  label: string;
  tone: OwnerStatusTone;
  /** one line on what happens next / what the owner should do */
  hint: string;
}

export function ownerListingStatus(p: OwnerStatusInput): OwnerStatus {
  switch (p.status) {
    case "under_review":
      return {
        label: "Under review",
        tone: "waiting",
        hint: "Our team is reviewing it. You will hear the outcome here and by email.",
      };
    case "draft":
      if (p.review_outcome === "changes_requested") {
        return {
          label: "Changes requested",
          tone: "action",
          hint: "Update it as asked below, then send it back for review.",
        };
      }
      return {
        label: "Draft — not submitted",
        tone: "action",
        hint: "Not sent to our team yet. Submit it when it is ready.",
      };
    case "active":
      return { label: "Live — open for investment", tone: "live", hint: "Investors can buy units now." };
    case "funded":
      return { label: "Fully funded", tone: "done", hint: "Every unit is sold." };
    case "closed":
      if (p.review_outcome === "declined") {
        return { label: "Not approved", tone: "stopped", hint: "See the message from our team below." };
      }
      return { label: "Closed", tone: "stopped", hint: "No longer visible to investors." };
    default:
      return { label: p.status, tone: "waiting", hint: "" };
  }
}

/** Badge classes for each tone (Tailwind tokens used across the dashboards). */
export const OWNER_STATUS_BADGE: Record<OwnerStatusTone, string> = {
  live: "bg-primary text-primary-foreground",
  waiting: "bg-warning text-warning-foreground",
  action: "bg-accent text-accent-foreground",
  done: "bg-success text-success-foreground",
  stopped: "bg-destructive text-destructive-foreground",
};

/** Funding figures only mean something once a listing is on the market. */
export const isOnMarket = (status: string) => status === "active" || status === "funded";
