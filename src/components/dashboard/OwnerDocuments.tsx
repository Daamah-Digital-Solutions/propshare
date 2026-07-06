import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { propertyApi, documentsApi, apiUrl, ApiError } from "@/lib/api";
import { FileText, Download, Upload } from "lucide-react";

/** Owner Documents tab — REAL, storage-backed. Lists each of the owner's properties with
 *  its documents (public download links) and lets the owner upload new ones. */
function PropertyDocs({ propId, title }: { propId: string; title: string }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [docTitle, setDocTitle] = useState("");
  const [busy, setBusy] = useState(false);

  const { data: docs } = useQuery({
    queryKey: ["prop-docs", propId],
    queryFn: () => documentsApi.listForProperty(propId),
  });

  const upload = async () => {
    if (!file || !docTitle.trim()) {
      toast({ title: "Pick a file and enter a title first.", variant: "destructive" });
      return;
    }
    setBusy(true);
    try {
      await documentsApi.upload(propId, file, docTitle.trim());
      toast({ title: "Document uploaded" });
      setFile(null);
      setDocTitle("");
      qc.invalidateQueries({ queryKey: ["prop-docs", propId] });
    } catch (e) {
      toast({
        title: "Upload failed",
        description: e instanceof ApiError ? e.message : "Please try again.",
        variant: "destructive",
      });
    } finally {
      setBusy(false);
    }
  };

  const list = docs ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {list.length === 0 ? (
          <p className="text-sm text-muted-foreground">No documents uploaded yet.</p>
        ) : (
          <div className="space-y-2">
            {list.map((d) => (
              <div
                key={d.id}
                className="flex items-center justify-between rounded-md border border-border p-3"
              >
                <div className="flex items-center gap-3">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium text-foreground">{d.title}</p>
                    <p className="text-xs uppercase text-muted-foreground">{d.type}</p>
                  </div>
                </div>
                <a href={apiUrl(d.download_url)} target="_blank" rel="noopener noreferrer">
                  <Button variant="ghost" size="sm">
                    <Download className="mr-1 h-4 w-4" /> Download
                  </Button>
                </a>
              </div>
            ))}
          </div>
        )}
        <div className="flex flex-col gap-2 border-t border-border pt-4 sm:flex-row sm:items-center">
          <Input
            placeholder="Document title"
            value={docTitle}
            onChange={(e) => setDocTitle(e.target.value)}
            className="sm:max-w-[220px]"
          />
          <Input
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="sm:max-w-[260px]"
          />
          <Button onClick={upload} disabled={busy}>
            <Upload className="mr-2 h-4 w-4" /> {busy ? "Uploading…" : "Upload"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function OwnerDocuments() {
  const { data } = useQuery({ queryKey: ["owner-props-docs"], queryFn: () => propertyApi.listOwner() });
  const properties: { id: string; title: string }[] = Array.isArray(data)
    ? (data as { id: string; title: string }[])
    : ((data as { items?: { id: string; title: string }[] } | undefined)?.items ?? []);

  if (properties.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          List a property first — its documents (agreements, valuations, statements) will appear here.
        </CardContent>
      </Card>
    );
  }
  return (
    <div className="space-y-4">
      {properties.map((p) => (
        <PropertyDocs key={p.id} propId={p.id} title={p.title} />
      ))}
    </div>
  );
}
