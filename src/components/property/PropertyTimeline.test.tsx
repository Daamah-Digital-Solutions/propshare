/**
 * Phase 15b: PropertyTimeline is driven by REAL per-property milestones. The
 * fully-hardcoded 8-event mock ("Property Listed" / "Oct 15, 2024" …) is gone —
 * this is the audit-missed fake surface the sub-group fixes.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PropertyTimeline from "./PropertyTimeline";
import type { PropertyMilestone } from "@/lib/api";

const M = (over: Partial<PropertyMilestone>): PropertyMilestone => ({
  id: "x",
  property_id: "p",
  title: "T",
  description: null,
  status: "planned",
  progress_pct: null,
  value_index: null,
  target_date: null,
  completed_at: null,
  sort_index: 0,
  ...over,
});

describe("PropertyTimeline (real milestones)", () => {
  it("renders the real milestones, not the old hardcoded events", () => {
    render(
      <PropertyTimeline
        milestones={[
          M({ id: "1", title: "Foundation", status: "completed", sort_index: 0, target_date: "2026-01-15" }),
          M({
            id: "2",
            title: "Structure",
            status: "in_progress",
            progress_pct: 40,
            sort_index: 1,
            target_date: "2026-06-15",
          }),
        ]}
      />,
    );
    expect(screen.getByText("Foundation")).toBeInTheDocument();
    expect(screen.getByText("Structure")).toBeInTheDocument();
    expect(screen.getByText("40% complete")).toBeInTheDocument();
    // the retired hardcoded mock must be gone
    expect(screen.queryByText("Property Listed")).toBeNull();
    expect(screen.queryByText(/Oct 15, 2024/)).toBeNull();
    expect(screen.queryByText("SPV Formation")).toBeNull();
  });

  it("shows an honest empty state when there are no milestones", () => {
    render(<PropertyTimeline milestones={[]} />);
    expect(
      screen.getByText(/No project milestones have been published yet/i),
    ).toBeInTheDocument();
  });
});
