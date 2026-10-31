import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { saveBlob } from "@/lib/certificates";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  Download,
  Eye,
  FileArchive,
  FileText,
  Loader2,
  MapPin,
  QrCode,
  Shield,
} from "lucide-react";
import {
  certificateApi,
  documentsApi,
  holdingsApi,
  returnsApi,
  type Holding,
} from "@/lib/api";

/**
 * Investor certificates — the rich documents surface, wired to REAL data (DELETE NOTHING /
 * no fabricated data). Each certificate is issued from the ownership ledger and kept (client,
 * 2026-10-28): its number, issue date, SPV and status are the server's, and its QR code opens
 * its own verification page on the platform. Value is units at today's unit price.
 */


const usd0 = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export const InvestmentCertificates = () => {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);

  const { data: holdingsResp, isLoading } = useQuery({
    queryKey: ["cert-holdings"],
    queryFn: () => holdingsApi.mine(),
  });
  const { data: returns } = useQuery({ queryKey: ["cert-returns"], queryFn: returnsApi.getMine });
  // the certificate stating each holding (number, issue date, SPV, verification page)
  const { data: certsResp } = useQuery({
    queryKey: ["my-certificates"],
    queryFn: () => certificateApi.mine(),
  });
  const certFor = useMemo(
    () => new Map((certsResp?.items ?? []).map((c) => [c.property_id, c])),
    [certsResp],
  );

  const rows = useMemo(
    () => (holdingsResp?.items ?? []).filter((h) => h.units > 0),
    [holdingsResp],
  );
  const propIds = useMemo(() => rows.map((r) => r.property_id), [rows]);

  // Real document count across the held properties (best-effort; a failed one counts 0).
  const { data: docsCount } = useQuery({
    queryKey: ["cert-docs", propIds],
    enabled: propIds.length > 0,
    queryFn: async () => {
      const lists = await Promise.all(
        propIds.map((id) => documentsApi.listForProperty(id).catch(() => [])),
      );
      return lists.reduce((sum, l) => sum + l.length, 0);
    },
  });
  const taxYears = useMemo(
    () =>
      new Set(
        (returns?.items ?? []).map((i) => (i.period_end || "").slice(0, 4)).filter(Boolean),
      ).size,
    [returns],
  );

  const issuedOn = (iso: string | undefined) =>
    iso
      ? new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" })
      : "—";
  const refreshCertificates = () =>
    queryClient.invalidateQueries({ queryKey: ["my-certificates"] });

  const view = async (h: Holding) => {
    setBusy("view-" + h.property_id);
    try {
      const url = URL.createObjectURL(await certificateApi.download(h.property_id));
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
      refreshCertificates();
    } catch {
      toast.error("Could not open the certificate. Please try again.");
    } finally {
      setBusy(null);
    }
  };
  const download = async (h: Holding) => {
    setBusy("dl-" + h.property_id);
    try {
      saveBlob(await certificateApi.download(h.property_id), `certificate-${h.title ?? h.property_id}.pdf`);
      refreshCertificates();
    } catch {
      toast.error("Could not download the certificate. Please try again.");
    } finally {
      setBusy(null);
    }
  };
  const downloadAll = async () => {
    setBusy("all");
    try {
      saveBlob(await certificateApi.downloadAllZip(), "capimax-certificates.zip");
    } catch {
      toast.error("Could not build the archive. Please try again.");
    } finally {
      setBusy(null);
    }
  };
  const bundle = async (h: Holding) => {
    setBusy("bundle-" + h.property_id);
    try {
      saveBlob(
        await certificateApi.downloadPropertyBundle(h.property_id),
        `${h.title ?? h.property_id}-documents.zip`,
      );
    } catch {
      toast.error("Could not build the document archive. Please try again.");
    } finally {
      setBusy(null);
    }
  };

  const summary = [
    { label: "Investment Certificates", value: rows.length },
    { label: "SPV Agreements", value: rows.length },
    { label: "Property Documents", value: docsCount ?? 0 },
    { label: "Tax Statements", value: taxYears },
  ];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {summary.map((c) => (
          <Card key={c.label} className="bg-card border-border">
            <CardContent className="p-6 text-center">
              <FileText className="h-6 w-6 text-primary mx-auto mb-3" />
              <div className="text-3xl font-bold text-foreground">{c.value}</div>
              <p className="text-sm text-muted-foreground mt-1">{c.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Download-all banner */}
      <Card className="bg-primary/5 border-primary/20">
        <CardContent className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="h-11 w-11 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
              <Shield className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground">All Investment Documents</h3>
              <p className="text-sm text-muted-foreground">
                Download all your ownership certificates in one archive.
              </p>
            </div>
          </div>
          <Button onClick={downloadAll} disabled={busy === "all" || rows.length === 0} className="gap-2">
            {busy === "all" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FileArchive className="h-4 w-4" />
            )}
            Download All (.zip)
          </Button>
        </CardContent>
      </Card>

      {/* Certificates list */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle>Investment Certificates</CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <div className="py-12 flex flex-col items-center text-center gap-3">
              <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
                <FileText className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-semibold">No certificates yet</h3>
              <p className="text-sm text-muted-foreground max-w-md">
                Once you hold units in a property, a downloadable ownership certificate appears
                here, with a QR code that anyone can scan to verify it.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {rows.map((h) => {
                const value = h.units * Number(h.unit_price || 0);
                const cert = certFor.get(h.property_id);
                // the listing's registered SPV, as on the certificate; never made up
                const spv = cert?.spv_name ?? null;
                const current = cert?.status === "valid" && cert.units === h.units;
                return (
                  <div key={h.property_id} className="rounded-xl border border-border p-4">
                    <div className="flex flex-col lg:flex-row lg:items-center gap-4">
                      <div className="flex items-center gap-4 flex-1 min-w-[220px]">
                        <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                          <FileText className="h-6 w-6 text-primary" />
                        </div>
                        <div>
                          <h4 className="font-semibold text-foreground">{h.title ?? "Property"}</h4>
                          <p className="text-sm text-muted-foreground flex items-center gap-1">
                            <MapPin className="h-3 w-3" /> {h.location ?? "—"}
                          </p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {cert?.number ?? "Certificate issued on download"}
                          </p>
                          {cert && (
                            <Link
                              to={cert.verify_path}
                              aria-label={`Verify certificate ${cert.number}`}
                              className="mt-0.5 inline-flex items-center gap-1 text-xs font-medium text-primary underline underline-offset-4 hover:text-primary/80"
                            >
                              <QrCode className="h-3 w-3" /> Verify this certificate
                            </Link>
                          )}
                        </div>
                      </div>
                      <div className="grid grid-cols-3 gap-6 text-sm flex-1">
                        <div>
                          <p className="text-xs text-muted-foreground">Investment</p>
                          <p className="font-semibold text-foreground">{usd0(value)}</p>
                          <p className="text-xs text-muted-foreground">{h.units} units</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Ownership</p>
                          {/* the share as the certificate prints it: never rounded to 0.00% */}
                          <p className="font-semibold text-foreground">{h.ownership_pct ?? "—"}</p>
                          {spv && <p className="text-xs text-muted-foreground truncate">{spv}</p>}
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Issued</p>
                          <p className="font-medium text-foreground">{issuedOn(cert?.issued_at)}</p>
                          {current ? (
                            <Badge className="mt-1 text-[10px] border-0 bg-green-500/10 text-green-700">
                              <CheckCircle2 className="h-3 w-3 mr-1" /> Valid
                            </Badge>
                          ) : (
                            <Badge className="mt-1 text-[10px] border-0 bg-amber-500/10 text-amber-700">
                              <AlertTriangle className="h-3 w-3 mr-1" /> New one on download
                            </Badge>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => view(h)}
                          disabled={busy === "view-" + h.property_id}
                        >
                          {busy === "view-" + h.property_id ? (
                            <Loader2 className="h-4 w-4 animate-spin mr-1" />
                          ) : (
                            <Eye className="h-4 w-4 mr-1" />
                          )}
                          View
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => download(h)}
                          disabled={busy === "dl-" + h.property_id}
                        >
                          {busy === "dl-" + h.property_id ? (
                            <Loader2 className="h-4 w-4 animate-spin mr-1" />
                          ) : (
                            <Download className="h-4 w-4 mr-1" />
                          )}
                          Download
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => bundle(h)}
                          disabled={busy === "bundle-" + h.property_id}
                          title="Download the certificate + all property documents (.zip)"
                        >
                          {busy === "bundle-" + h.property_id ? (
                            <Loader2 className="h-4 w-4 animate-spin mr-1" />
                          ) : (
                            <FileArchive className="h-4 w-4 mr-1" />
                          )}
                          All docs
                        </Button>
                      </div>
                    </div>
                    <div className="mt-3 pt-3 border-t border-border/70 flex items-center gap-2 text-xs text-muted-foreground">
                      <Building2 className="h-3.5 w-3.5" />
                      Issued by <span className="font-medium text-foreground">Capimax PropShare</span>
                      {spv ? <span>· SPV {spv}</span> : null}
                      {h.location ? <span>· {h.location}</span> : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Important notice — honest legal framing */}
      <Card className="bg-muted/30 border-border">
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <Shield className="h-6 w-6 text-primary flex-shrink-0" />
            <div>
              <h4 className="font-semibold text-foreground mb-2">Important Notice</h4>
              <p className="text-sm text-muted-foreground">
                Your investment certificates state the fractional units recorded in the Capimax
                PropShare ownership ledger on their issue date; each one's QR code lets anyone
                confirm it is authentic and still current. They are not transferable securities or
                a substitute for the offering documents and SPV agreements governing each property.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
