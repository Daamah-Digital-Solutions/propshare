import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Download, FileText, Loader2, Shield } from "lucide-react";
import { certificateApi, holdingsApi, type Holding } from "@/lib/api";

/**
 * Group 2: real per-holding ownership certificates. Each property the investor currently
 * net-holds has a downloadable PDF generated live from the ownership ledger (no fabricated
 * certificates). DELETE NOTHING — the surface is now real, not honest-disabled.
 */
export const InvestmentCertificates = () => {
  const { data: holdings, isLoading } = useQuery({
    queryKey: ["secondary", "holdings"],
    queryFn: () => holdingsApi.mine(),
  });
  const [downloading, setDownloading] = useState<string | null>(null);

  const rows = (holdings ?? []).filter((h: Holding) => h.units > 0);

  const download = async (h: Holding) => {
    setDownloading(h.property_id);
    try {
      const blob = await certificateApi.download(h.property_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `certificate-${h.title ?? h.property_id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Could not download the certificate. Please try again.");
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="space-y-6">
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : rows.length === 0 ? (
        <Card className="bg-card border-border border-dashed">
          <CardContent className="py-12 flex flex-col items-center text-center gap-3">
            <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
              <FileText className="h-6 w-6 text-muted-foreground" />
            </div>
            <h3 className="text-lg font-semibold">No certificates yet</h3>
            <p className="text-sm text-muted-foreground max-w-md">
              Once you hold units in a property, a downloadable ownership certificate appears
              here, generated from your live holdings.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {rows.map((h) => (
            <Card key={h.property_id} className="bg-card border-border">
              <CardContent className="p-4 flex items-center justify-between gap-4">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center">
                    <FileText className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h4 className="font-medium text-foreground">{h.title ?? "Property"}</h4>
                    <p className="text-sm text-muted-foreground">
                      {h.units} unit{h.units === 1 ? "" : "s"} held
                    </p>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={downloading === h.property_id}
                  onClick={() => download(h)}
                >
                  {downloading === h.property_id ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-1" />
                  ) : (
                    <Download className="h-4 w-4 mr-1" />
                  )}
                  Certificate
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Honest notice — matches the generated document's wording. */}
      <Card className="bg-muted/30 border-border">
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <Shield className="h-6 w-6 text-primary flex-shrink-0" />
            <div>
              <h4 className="font-semibold text-foreground mb-2">About these certificates</h4>
              <p className="text-sm text-muted-foreground">
                Each certificate reflects the fractional units recorded in the CapiMax ownership
                ledger as of its generation date. It is generated from live data and is not a
                transferable security or a substitute for the offering documents and SPV
                agreements governing each property.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
