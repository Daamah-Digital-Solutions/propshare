import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Download, FileText, MapPin, QrCode, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { certificateApi } from "@/lib/api";
import { saveBlob } from "@/lib/certificates";
import {
  TrustCapabilities,
  TrustGatewayCard,
  TrustScopeNote,
} from "@/components/verification/CapimaxTrustGateway";
import { VerificationPartners } from "@/components/verification/VerificationPartners";

/**
 * Verification Center, inside the investor dashboard.
 *
 * Same verification services and hand-off to Capimax Trust as the public page, plus the one
 * thing only a signed-in investor has: every certificate they hold, with its number and the
 * verification code printed beside its QR code, ready to copy, the PDF and the link to the
 * certificate's own verification page (client, 2026-10-28, as on Capimax BRX). The numbers and
 * codes are the server's, as printed on the certificates, never made up here.
 */
export const VerificationTab = () => {
  const queryClient = useQueryClient();
  const [copied, setCopied] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["my-certificates"],
    queryFn: () => certificateApi.mine(),
  });
  const certs = data?.items ?? [];

  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(value);
      window.setTimeout(() => setCopied((c) => (c === value ? null : c)), 2000);
    } catch {
      toast.error("Could not copy. Select the code and copy it manually.");
    }
  };

  const download = async (propertyId: string, title: string) => {
    setBusy(propertyId);
    try {
      saveBlob(await certificateApi.download(propertyId), `certificate-${title}.pdf`);
      // a download issues a new certificate when the units changed since the list was read
      queryClient.invalidateQueries({ queryKey: ["my-certificates"] });
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
            Your investment certificates are verified here: each one carries a QR code that opens
            its verification page on Capimax PropShare. Other documents are verified with the
            designated partner for their kind of record below, or through Capimax Trust, the
            central verification gateway of the Capimax ecosystem.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" /> Your certificates
          </CardTitle>
          <CardDescription>
            Each certificate has a number and a verification code, printed beside its QR code.
            Scanning the QR code, or entering the code on the Verification Center, opens the
            certificate's verification page, which shows that it is authentic and current. A
            certificate states the units you hold when it is issued: when they change, your next
            certificate states the new count.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading your certificates…</p>
          ) : certs.length === 0 ? (
            <div className="rounded-lg bg-muted/50 p-4 text-sm text-muted-foreground" data-testid="no-certificates">
              You will have a certificate for each property once you hold units in it.{" "}
              <Link to="/marketplace" className="text-primary underline underline-offset-4">
                Browse the marketplace
              </Link>
            </div>
          ) : (
            <ul className="divide-y divide-border" data-testid="certificate-refs">
              {certs.map((c) => (
                <li key={c.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-foreground">{c.property_title}</p>
                    {c.location && (
                      <p className="flex items-center gap-1 text-sm text-muted-foreground">
                        <MapPin className="h-3 w-3" /> {c.location}
                      </p>
                    )}
                    <p className="text-sm text-muted-foreground">
                      {c.units.toLocaleString()} units · {c.ownership} of the property
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Certificate <span className="font-medium text-foreground">{c.number}</span>
                    </p>
                  </div>
                  <div className="flex flex-col items-start gap-2 sm:items-end">
                    <div className="flex flex-wrap items-center gap-2">
                      <code
                        className="break-all rounded-md bg-muted px-2 py-1 font-mono text-sm text-foreground"
                        title="Verification code"
                      >
                        {c.verification_code}
                      </code>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => copy(c.verification_code)}
                        aria-label={`Copy verification code of ${c.number}`}
                      >
                        {copied === c.verification_code ? (
                          <Check className="h-4 w-4" />
                        ) : (
                          <Copy className="h-4 w-4" />
                        )}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => download(c.property_id, c.property_title)}
                        disabled={busy === c.property_id}
                        aria-label={`Download certificate for ${c.property_title}`}
                      >
                        <Download className="h-4 w-4" />
                        <span className="ml-1 hidden sm:inline">PDF</span>
                      </Button>
                    </div>
                    <Link
                      to={c.verify_path}
                      aria-label={`Verify certificate ${c.number}`}
                      className="inline-flex items-center gap-1 text-sm font-medium text-primary underline underline-offset-4 hover:text-primary/80"
                    >
                      <QrCode className="h-3.5 w-3.5" /> Open its verification page
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <VerificationPartners compact />
      <TrustGatewayCard compact />
      <TrustCapabilities />
      <TrustScopeNote />
    </div>
  );
};
