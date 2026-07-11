// Canonical property-document categories (Task 4 — Documents Center).
// The backend stores a free-form `doc_type` on each document; these are the standard
// values owners pick when uploading, and the labels the Documents Center groups under.
// An unknown/legacy doc_type (e.g. the old default "document") falls into "Other".

export interface DocCategory {
  value: string;
  label: string;
}

export const DOC_CATEGORIES: DocCategory[] = [
  { value: "spv", label: "SPV Documents" },
  { value: "valuation", label: "Valuation Reports" },
  { value: "financial", label: "Financial & Investment Studies" },
  { value: "agreement", label: "Agreements" },
  { value: "legal", label: "Legal Documents" },
  { value: "insurance", label: "Insurance Certificates" },
  { value: "audit", label: "Smart Contract Audit Reports" },
  { value: "other", label: "Other Documents" },
];

const LABEL_BY_VALUE = new Map(DOC_CATEGORIES.map((c) => [c.value, c.label]));

/** Display label for a document's stored doc_type; unknown types collapse into "Other". */
export const docCategoryLabel = (docType: string | null | undefined): string =>
  LABEL_BY_VALUE.get((docType ?? "").toLowerCase()) ?? "Other Documents";

/** Stable sort key so categories always render in the canonical order (Other last). */
export const docCategoryOrder = (label: string): number => {
  const idx = DOC_CATEGORIES.findIndex((c) => c.label === label);
  return idx === -1 ? DOC_CATEGORIES.length : idx;
};
