import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy, Download, FileText, MapPin, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/contexts/AuthContext";
import { certificateApi, holdingsApi } from "@/lib/api";
import { certificateRef, saveBlob } from "@/lib/certificates";
import {
  TrustCapabilities,
  TrustGatewayCard,
  TrustScopeNote,
} from "@/components/verification/CapimaxTrustGateway";

/**
 * Verification Center, inside the investor dashboard.
 *
 * Same hand-off to Capimax Trust as the public page, plus the one thing only a signed-in
 * investor has: the reference of every certificate they hold, ready to copy, and the PDF
 * that carries it. The references are the stable ids printed on the certificates, never
 * made up here. Verification itself happens on Capimax Trust, not on this platform.
 */
export const VerificationTab = () => {
  const { user } = useAuth();
  const [copied, setCopied] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["verification-holdings"],
    queryFn: () => holdingsApi.mine(),
  });
  const held = (data?.items ?? []).filter((h) => h.units > 0);

  const copy = async (ref: string) => {
    try {
      await navigator.clipboard.writeText(ref);
      setCopied(ref);
      window.setTimeout(() => setCopied((c) => (c === ref ? null : c)), 2000);
    } catch {
      toast.error("Could not copy. Select the reference and copy it manually.");
    }
  };

  const download = async (propertyId: string, title: string | null) => {
    setBusy(propertyId);
    try {
      saveBlob(await certificateApi.download(propertyId), `certificate-${title ?? propertyId}.pdf`);
    } catch {
      toast.error("Could not download the certificate. Please try again.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-8" data-testid="verification-tab">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <ShieldCheck className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h2 className="text-2xl font-bold text-foreground">Verification Center</h2>
          <p className="mt-1 max-w-3xl text-muted-foreground">
            Every certificate and document issued through Capimax PropShare can be verified, its
            status reviewed, and an official copy downloaded through Capimax Trust, the central
            verification gateway of the Capimax ecosystem.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" /> Your certificates
          </CardTitle>
          <CardDescription>
            Each certificate carries a reference. Keep it at hand when you verify a certificate
            or request an official copy through Capimax Trust.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading your certificates…</p>
          ) : held.length === 0 ? (
            <div className="rounded-lg bg-muted/50 p-4 text-sm text-muted-foreground" data-testid="no-certificates">
              You will have a certificate for each property once you hold units in it.{" "}
              <Link to="/marketplace" className="text-primary underline underline-offset-4">
                Browse the marketplace
              </Link>
            </div>
          ) : (
            <ul className="divide-y divide-border" data-testid="certificate-refs">
              {held.map((h) => {
                const ref = certificateRef(h.property_id, user?.id);
                return (
                  <li
                    key={h.property_id}
                    className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-foreground">{h.title ?? "Property"}</p>
                      {h.location && (
                        <p className="flex items-center gap-1 text-sm text-muted-foreground">
                          <MapPin className="h-3 w-3" /> {h.location}
                        </p>
                      )}
                      <p className="text-sm text-muted-foreground">
                        {h.units.toLocaleString()} units
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <code className="rounded-md bg-muted px-2 py-1 font-mono text-sm text-foreground">
                        {ref}
                      </code>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => copy(ref)}
                        aria-label={`Copy reference ${ref}`}
                      >
                        {copied === ref ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => download(h.property_id, h.title)}
                        disabled={busy === h.property_id}
                        aria-label={`Download certificate for ${h.title ?? "property"}`}
                      >
                        <Download className="h-4 w-4" />
                        <span className="ml-1 hidden sm:inline">PDF</span>
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      <TrustGatewayCard compact />
      <TrustCapabilities />
      <TrustScopeNote />
    </div>
  );
};
