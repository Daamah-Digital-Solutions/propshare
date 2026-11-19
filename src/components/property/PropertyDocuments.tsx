import { Download, Eye, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useQuery } from "@tanstack/react-query";
import { apiUrl, documentsApi, type PropertyDocument } from "@/lib/api";
import { docDay, groupDocuments } from "@/lib/documentCategories";

/** One document: its title, who issued it, its date, and View / Download. */
export const DocumentRow = ({ doc, withPreview }: { doc: PropertyDocument; withPreview: (p: string) => string }) => {
  const href = apiUrl(withPreview(doc.download_url));
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 p-4 hover:bg-secondary/30 transition-colors" data-testid="doc-row">
      <div className="flex min-w-0 items-center gap-4">
        <div className="w-10 h-10 shrink-0 bg-primary/10 rounded-lg flex items-center justify-center">
          <FileText size={20} className="text-primary" />
        </div>
        <div className="min-w-0">
          <h4 className="font-medium text-foreground break-words">{doc.title}</h4>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm text-muted-foreground">
            {doc.issuer && (
              <span>
                Issued by <span translate="no" className="text-foreground">{doc.issuer}</span>
              </span>
            )}
            <span>{docDay(doc.issued_on ?? doc.created_at)}</span>
          </div>
        </div>
      </div>
      <div className="flex shrink-0 gap-1">
        <a href={href} target="_blank" rel="noopener noreferrer">
          <Button variant="ghost" size="sm">
            <Eye size={16} className="me-1" />
            View
          </Button>
        </a>
        <a href={href} target="_blank" rel="noopener noreferrer" download>
          <Button variant="ghost" size="sm">
            <Download size={16} className="me-1" />
            Download
          </Button>
        </a>
      </div>
    </div>
  );
};

// Group 2: real property documents from the storage seam. Client letter (2026-11-18, as on
// Capimax BRX): grouped by category, each with who issued it and its date.
const PropertyDocuments = ({
  propertyId,
  preview,
}: {
  propertyId?: string;
  /** Admin preview token for an unpublished listing (passed through to list + downloads). */
  preview?: string | null;
}) => {
  const { data: docs, isLoading } = useQuery({
    queryKey: ["property-documents", propertyId, preview ?? null],
    queryFn: () => documentsApi.listForProperty(propertyId as string, preview),
    enabled: !!propertyId,
  });
  const withPreview = (path: string) =>
    preview ? `${path}${path.includes("?") ? "&" : "?"}preview=${encodeURIComponent(preview)}` : path;

  const groups = groupDocuments(docs ?? []);

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-xl font-semibold text-foreground">Property Documents</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Offering and legal documents published for this property
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : groups.length === 0 ? (
        <div className="bg-card rounded-2xl border border-border border-dashed p-8 text-center">
          <FileText className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">
            No documents have been published for this property yet.
          </p>
        </div>
      ) : (
        groups.map((g) => (
          <div key={g.label} className="bg-card rounded-2xl border border-border overflow-hidden" data-testid="doc-group">
            <div className="flex items-center justify-between border-b border-border bg-secondary/40 px-4 py-2.5">
              <h4 className="text-sm font-semibold text-foreground">{g.label}</h4>
              <span className="text-xs text-muted-foreground">{g.docs.length}</span>
            </div>
            <div className="divide-y divide-border">
              {g.docs.map((doc) => (
                <DocumentRow key={doc.id} doc={doc} withPreview={withPreview} />
              ))}
            </div>
          </div>
        ))
      )}

      <div className="bg-secondary/50 rounded-xl p-4 text-sm text-muted-foreground">
        <p>
          <strong className="text-foreground">Disclaimer:</strong> These documents are provided for
          informational purposes only. Please review all materials carefully and consult with your
          financial advisor before making investment decisions.
        </p>
      </div>
    </div>
  );
};

export default PropertyDocuments;
