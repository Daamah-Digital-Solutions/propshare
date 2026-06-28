import { FileText, Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useQuery } from "@tanstack/react-query";
import { apiUrl, documentsApi } from "@/lib/api";

// Group 2: real property documents from the storage seam (replaces the hardcoded mock
// list). Downloads hit the public document route. DELETE NOTHING — component kept, the
// data source is now live; honest empty state when an owner hasn't uploaded any yet.
const PropertyDocuments = ({ propertyId }: { propertyId?: string }) => {
  const { data: docs, isLoading } = useQuery({
    queryKey: ["property-documents", propertyId],
    queryFn: () => documentsApi.listForProperty(propertyId as string),
    enabled: !!propertyId,
  });

  const rows = docs ?? [];

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
      ) : rows.length === 0 ? (
        <div className="bg-card rounded-2xl border border-border border-dashed p-8 text-center">
          <FileText className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">
            No documents have been published for this property yet.
          </p>
        </div>
      ) : (
        <div className="bg-card rounded-2xl border border-border overflow-hidden">
          <div className="divide-y divide-border">
            {rows.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between p-4 hover:bg-secondary/30 transition-colors"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center">
                    <FileText size={20} className="text-primary" />
                  </div>
                  <div>
                    <h4 className="font-medium text-foreground">{doc.title}</h4>
                    <div className="flex items-center gap-3 text-sm text-muted-foreground">
                      <span className="uppercase">{doc.type}</span>
                      <span>•</span>
                      <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                </div>
                <a href={apiUrl(doc.download_url)} target="_blank" rel="noopener noreferrer" download>
                  <Button variant="ghost" size="sm">
                    <Download size={16} className="mr-1" />
                    Download
                  </Button>
                </a>
              </div>
            ))}
          </div>
        </div>
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
