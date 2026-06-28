/**
 * Phase 15b: the sample/advanced construction pages get their timeline from the
 * real property_milestones (via toSampleProperty), NOT the legacy content.timeline
 * blob — and the NAV (value_index) is preserved so those surfaces don't regress.
 */
import { describe, it, expect } from "vitest";
import { toSampleProperty } from "@/lib/properties";
import type { PropertyDetail, PropertyMilestone } from "@/lib/api";

const ms = (over: Partial<PropertyMilestone>): PropertyMilestone => ({
  id: "x",
  property_id: "p1",
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

const base = (over: Partial<PropertyDetail>): PropertyDetail => ({
  id: "p1",
  slug: "demo-x",
  title: "T",
  subtitle: null,
  location: "Dubai",
  country: null,
  city: null,
  model: "future",
  property_type: "residential",
  status: "active",
  image: null,
  total_value: 1_000_000,
  minimum_investment: 100,
  unit_price: 100,
  target_yield: null,
  expected_yield: null,
  capital_appreciation: null,
  total_return: null,
  funded_amount: 0,
  funding_progress: 0,
  total_units: 100,
  available_units: 100,
  investors_count: 0,
  developer_name: null,
  description: null,
  images: [],
  expected_completion: null,
  spv_name: null,
  spv_registration: null,
  legal_structure: null,
  fees: null,
  content: {},
  owner_id: null,
  created_at: "",
  updated_at: "",
  milestones: [],
  construction_progress: 0,
  ...over,
});

describe("toSampleProperty timeline from real milestones", () => {
  it("maps milestones into the SampleMilestone timeline, carrying value_index (NAV)", () => {
    const d = base({
      milestones: [
        ms({ id: "1", title: "Foundation", status: "completed", progress_pct: 100, value_index: 105, sort_index: 0 }),
        ms({ id: "2", title: "Structure", status: "in_progress", progress_pct: 60, value_index: 112, sort_index: 1 }),
      ],
    });
    const s = toSampleProperty(d);
    expect(s.timeline.map((t) => t.label)).toEqual(["Foundation", "Structure"]);
    expect(s.timeline.map((t) => t.valueIndex)).toEqual([105, 112]); // NAV preserved
    expect(s.timeline.map((t) => t.status)).toEqual(["done", "active"]);
    expect(s.timeline[1].progress).toBe(60);
  });

  it("sorts by sort_index regardless of array order", () => {
    const d = base({
      milestones: [
        ms({ id: "2", title: "B", sort_index: 1 }),
        ms({ id: "1", title: "A", sort_index: 0 }),
      ],
    });
    expect(toSampleProperty(d).timeline.map((t) => t.label)).toEqual(["A", "B"]);
  });
});
