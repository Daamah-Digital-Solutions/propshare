import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileSearch, Scale, ShieldCheck, type LucideIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { documentsApi, type PropertyDocument } from "@/lib/api";
import { DocumentRow } from "@/components/property/PropertyDocuments";
import { docDay } from "@/lib/documentCategories";
import { textDir } from "@/lib/textDir";

type Dict = Record<string, unknown>;
const obj = (v: unknown): Dict => (v && typeof v === "object" && !Array.isArray(v) ? (v as Dict) : {});
const str = (v: unknown): string => (typeof v === "string" ? v.trim() : "");
const num = (v: unknown): number | null => {
  const n = typeof v === "number" ? v : typeof v === "string" && v.trim() ? Number(v) : NaN;
  return Number.isFinite(n) ? n : null;
};
const usd = (n: number) => `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

/** Newest first: the date on the document, else its upload date. */
function newestFirst(a: PropertyDocument, b: PropertyDocument): number {
  return (b.issued_on ?? b.created_at).localeCompare(a.issued_on ?? a.created_at);
}

interface Fact {
  label: string;
  value: ReactNode;
}

function AssuranceCard({
  icon: Icon,
  title,
  explanation,
  standard,
  facts,
  docs,
  docsTitle,
  withPreview,
  testId,
}: {
  icon: LucideIcon;
  title: string;
  /** what the admin wrote, else null: then the standard explanation below is shown */
  explanation: string | null;
  /** shown when the admin wrote nothing but the card has facts or documents */
  standard: string;
  facts: Fact[];
  docs: PropertyDocument[];
  docsTitle: string;
  withPreview: (p: string) => string;
  testId: string;
}) {
  const published = Boolean(explanation) || facts.length > 0 || docs.length > 0;
  return (
    <Card className="border-border" data-testid={testId}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon className="h-5 w-5 text-primary" /> {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {!published ? (
          <p className="text-muted-foreground" data-testid={`${testId}-empty`}>
            Not published yet for this property.
          </p>
        ) : (
          <>
            {explanation ? (
              <p translate="no" dir={textDir(explanation)} className="whitespace-pre-line leading-relaxed text-muted-foreground">
                {explanation}
              </p>
            ) : (
              <p className="leading-relaxed text-muted-foreground">{standard}</p>
            )}
            {facts.length > 0 && (
              <div className="grid gap-3 sm:grid-cols-2">
                {facts.map((f) => (
                  <div key={f.label} className="rounded-lg border border-border bg-secondary/40 p-3">
                    <p className="text-xs text-muted-foreground">{f.label}</p>
                    <p className="mt-0.5 font-semibold text-foreground">{f.value}</p>
                  </div>
                ))}
              </div>
            )}
            {docs.length > 0 && (
              <div className="overflow-hidden rounded-xl border border-border">
                <p className="border-b border-border bg-secondary/40 px-4 py-2 text-xs font-semibold text-foreground">
                  {docsTitle}
                </p>
                <div className="divide-y divide-border">
                  {docs.map((d) => (
                    <DocumentRow key={d.id} doc={d} withPreview={withPreview} />
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** A name as written (a valuer, an insurer, a law firm, a policy number): never translated. */
function name(v: string) {
  return <span translate="no">{v}</span>;
}

/**
 * The property page's Due Diligence tab (client letter, 2026-11-18): the valuation, the
 * insurance and the legal due diligence, each with who issued it, its date, an explanation and
 * its documents to view or download. What the admin left empty is not shown; a card with
 * nothing at all says so.
 */
export default function DueDiligenceTab({
  content,
  propertyId,
  preview,
}: {
  content: unknown;
  propertyId: string;
  preview?: string | null;
}) {
  const c = obj(content);
  const valuation = obj(c.valuation);
  const insurance = obj(c.insurance);
  const legal = obj(c.legalDueDiligence);
  const { data: docs } = useQuery({
    queryKey: ["property-documents", propertyId, preview ?? null],
    queryFn: () => documentsApi.listForProperty(propertyId, preview),
    enabled: !!propertyId,
  });
  const withPreview = (path: string) =>
    preview ? `${path}${path.includes("?") ? "&" : "?"}preview=${encodeURIComponent(preview)}` : path;
  const ofType = (...types: string[]) => (docs ?? []).filter((d) => types.includes(d.type)).sort(newestFirst);

  const valuationFacts: Fact[] = [];
  if (str(valuation.provider)) valuationFacts.push({ label: "Valuer", value: name(str(valuation.provider)) });
  if (num(valuation.value) != null) valuationFacts.push({ label: "Latest valuation", value: usd(num(valuation.value)!) });
  if (str(valuation.reportDate)) valuationFacts.push({ label: "Report date", value: str(valuation.reportDate) });
  if (str(valuation.impactNote))
    valuationFacts.push({ label: "Development impact", value: <span translate="no" dir={textDir(str(valuation.impactNote))}>{str(valuation.impactNote)}</span> });

  const insuranceFacts: Fact[] = [];
  if (str(insurance.provider)) insuranceFacts.push({ label: "Insurer", value: name(str(insurance.provider)) });
  if (str(insurance.policyNumber)) insuranceFacts.push({ label: "Policy number", value: name(str(insurance.policyNumber)) });
  if (num(insurance.coverage) != null) insuranceFacts.push({ label: "Coverage", value: usd(num(insurance.coverage)!) });

  const legalFacts: Fact[] = [];
  if (str(legal.provider)) legalFacts.push({ label: "Law firm", value: name(str(legal.provider)) });
  if (str(legal.date)) legalFacts.push({ label: "Review date", value: docDay(str(legal.date)) });

  return (
    <div className="space-y-6" data-testid="due-diligence">
      <div>
        <h3 className="text-xl font-semibold text-foreground">Due Diligence</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          The valuation, insurance and legal review of this property: who issued each, when, and the documents.
        </p>
      </div>
      <AssuranceCard
        icon={Scale}
        title="Valuation"
        testId="dd-valuation"
        explanation={str(valuation.summary) || null}
        standard="An independent valuer assesses the property's market value. The latest valuation is the reference for the unit price and for pricing exits."
        facts={valuationFacts}
        docs={ofType("valuation")}
        docsTitle="Valuation reports"
        withPreview={withPreview}
      />
      <AssuranceCard
        icon={ShieldCheck}
        title="Insurance"
        testId="dd-insurance"
        explanation={str(insurance.summary) || null}
        standard="The insurance that covers this property: the insurer, the policy and what it covers."
        facts={insuranceFacts}
        docs={ofType("insurance")}
        docsTitle="Insurance documents"
        withPreview={withPreview}
      />
      <AssuranceCard
        icon={FileSearch}
        title="Legal Due Diligence"
        testId="dd-legal"
        explanation={str(legal.summary) || null}
        standard="The independent legal review of this property: its title, its SPV and its offering documents."
        facts={legalFacts}
        docs={ofType("due_diligence", "legal")}
        docsTitle="Legal documents"
        withPreview={withPreview}
      />
      <div className="rounded-xl bg-secondary/50 p-4 text-sm text-muted-foreground">
        A valuation is issued every three months; the latest one is the reference for the unit price and for pricing exits.
      </div>
    </div>
  );
}
