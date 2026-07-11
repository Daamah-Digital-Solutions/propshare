import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Building2,
  Download,
  FileArchive,
  FileText,
  FolderOpen,
  Loader2,
  MapPin,
  ShieldCheck,
} from "lucide-react";
import {
  apiUrl,
  certificateApi,
  documentsApi,
  holdingsApi,
  type PropertyDocument,
} from "@/lib/api";
import { docCategoryLabel, docCategoryOrder } from "@/lib/documentCategories";

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/**
 * Documents Center (Task 4) — every document of the properties the investor holds, organised
 * by property and grouped by category (SPV, valuation, financial, agreements, legal, insurance,
 * smart-contract audit, other). Wired to REAL data: the per-property document list + public
 * download come straight from the storage-backed documents API (no fabricated entries).
 */

interface PropertyDocs {
  propertyId: string;
  title: string;
  location: string | null;
  docs: PropertyDocument[];
}

const groupByCategory = (docs: PropertyDocument[]): [string, PropertyDocument[]][] => {
  const byLabel = new Map<string, PropertyDocument[]>();
  for (const d of docs) {
    const label = docCategoryLabel(d.type);
    (byLabel.get(label) ?? byLabel.set(label, []).get(label)!).push(d);
  }
  return [...byLabel.entries()].sort((a, b) => docCategoryOrder(a[0]) - docCategoryOrder(b[0]));
};

export const InvestorDocuments = () => {
  const { data: holdingsResp, isLoading } = useQuery({
    queryKey: ["docs-holdings"],
    queryFn: () => holdingsApi.mine(),
  });

  const properties = useMemo(() => {
    const seen = new Map<string, { title: string; location: string | null }>();
    for (const h of holdingsResp?.items ?? []) {
      if (h.units > 0 && !seen.has(h.property_id)) {
        seen.set(h.property_id, { title: h.title ?? "Property", location: h.location ?? null });
      }
    }
    return [...seen.entries()].map(([propertyId, meta]) => ({ propertyId, ...meta }));
  }, [holdingsResp]);

  const propIds = useMemo(() => properties.map((p) => p.propertyId), [properties]);

  const { data: docsByProperty, isLoading: docsLoading } = useQuery({
    queryKey: ["docs-by-property", propIds],
    enabled: propIds.length > 0,
    queryFn: async (): Promise<PropertyDocs[]> => {
      const lists = await Promise.all(
        properties.map((p) =>
          documentsApi
            .listForProperty(p.propertyId)
            .catch(() => [] as PropertyDocument[])
            .then((docs) => ({ ...p, docs })),
        ),
      );
      return lists;
    },
  });

  const totalDocs = (docsByProperty ?? []).reduce((s, p) => s + p.docs.length, 0);

  const [busy, setBusy] = useState<string | null>(null);
  const downloadBundle = async (propertyId: string, title: string) => {
    setBusy(propertyId);
    try {
      saveBlob(await certificateApi.downloadPropertyBundle(propertyId), `${title}-documents.zip`);
    } catch {
      toast.error("Could not build the document archive — please try again.");
    } finally {
      setBusy(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <FolderOpen className="h-5 w-5 text-primary" /> Documents Center
          </h2>
          <p className="text-sm text-muted-foreground">
            All the documents of the properties you own — organised by property and category.
          </p>
        </div>
        {totalDocs > 0 && (
          <Badge variant="secondary" className="text-sm">
            {totalDocs} document{totalDocs === 1 ? "" : "s"}
          </Badge>
        )}
      </div>

      {properties.length === 0 ? (
        <Card className="bg-card border-border">
          <CardContent className="py-14 flex flex-col items-center text-center gap-3">
            <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
              <FolderOpen className="h-6 w-6 text-muted-foreground" />
            </div>
            <h3 className="text-lg font-semibold">No property documents yet</h3>
            <p className="text-sm text-muted-foreground max-w-md">
              Once you own units in a property, its documents — SPV agreements, valuation reports,
              legal papers, insurance certificates and more — appear here.
            </p>
          </CardContent>
        </Card>
      ) : docsLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : (
        <div className="space-y-5">
          {(docsByProperty ?? []).map((p) => {
            const groups = groupByCategory(p.docs);
            return (
              <Card key={p.propertyId} className="bg-card border-border">
                <CardHeader className="border-b border-border/60">
                  <div className="flex items-center gap-3">
                    <div className="h-11 w-11 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <Building2 className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <CardTitle className="text-base">{p.title}</CardTitle>
                      <p className="text-sm text-muted-foreground flex items-center gap-1">
                        <MapPin className="h-3 w-3" /> {p.location ?? "—"}
                      </p>
                    </div>
                    <div className="ml-auto flex items-center gap-2 flex-shrink-0">
                      <Badge variant="outline">
                        {p.docs.length} file{p.docs.length === 1 ? "" : "s"}
                      </Badge>
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1.5"
                        disabled={busy === p.propertyId}
                        onClick={() => downloadBundle(p.propertyId, p.title)}
                      >
                        {busy === p.propertyId ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <FileArchive className="h-4 w-4" />
                        )}
                        <span className="hidden sm:inline">Download all</span>
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-4">
                  {p.docs.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-4 text-center">
                      No documents have been published for this property yet.
                    </p>
                  ) : (
                    <div className="space-y-5">
                      {groups.map(([label, docs]) => (
                        <div key={label}>
                          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1.5">
                            <ShieldCheck className="h-3.5 w-3.5 text-primary" /> {label}
                          </p>
                          <div className="space-y-2">
                            {docs.map((d) => (
                              <div
                                key={d.id}
                                className="flex items-center justify-between gap-3 rounded-lg border border-border p-3"
                              >
                                <div className="flex items-center gap-3 min-w-0">
                                  <FileText className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                                  <div className="min-w-0">
                                    <p className="text-sm font-medium text-foreground truncate">
                                      {d.title}
                                    </p>
                                    <p className="text-xs text-muted-foreground">
                                      {new Date(d.created_at).toLocaleDateString()}
                                    </p>
                                  </div>
                                </div>
                                <a
                                  href={apiUrl(d.download_url)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline flex-shrink-0"
                                >
                                  <Download className="h-4 w-4" /> Download
                                </a>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};
