import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BadgeCheck,
  Building2,
  FileText,
  Fingerprint,
  Loader2,
  ShieldCheck,
  ShieldX,
  User,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, certificateApi, type CertificateVerification } from "@/lib/api";

/**
 * Certificate Verification (client, 2026-10-28, as on Capimax BRX): the page an investment
 * certificate's QR code opens, /verify/{code}. Anyone holding the paper sees, without an
 * account, whether it is authentic and current, and what it states. A certificate states the
 * units held when it was issued: once they change it shows as superseded by a newer one.
 */

const SUPPORT_EMAIL = "support@capimaxpropshare.com";

const day = (iso: string | null | undefined) =>
  iso
    ? new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })
    : "—";
const money = (v: string) =>
  Number(v).toLocaleString("en-US", { style: "currency", currency: "USD" });

const STATUS: Record<
  CertificateVerification["status"],
  { label: string; icon: LucideIcon; tone: string; badge: string }
> = {
  valid: {
    label: "Valid — Verified",
    icon: ShieldCheck,
    tone: "text-primary bg-primary/10",
    badge: "bg-primary text-primary-foreground",
  },
  superseded: {
    label: "Superseded",
    icon: AlertTriangle,
    tone: "text-amber-600 bg-amber-500/10",
    badge: "bg-amber-500 text-white",
  },
  revoked: {
    label: "Revoked",
    icon: ShieldX,
    tone: "text-destructive bg-destructive/10",
    badge: "bg-destructive text-destructive-foreground",
  },
};

function statusLine(c: CertificateVerification): string {
  if (c.status === "valid")
    return "This certificate is authentic and current: it was issued by Capimax PropShare and states the units its holder holds today.";
  if (c.status === "superseded")
    return `This certificate was issued by Capimax PropShare but no longer states the holder's current units${
      c.superseded_at ? ` (since ${day(c.superseded_at)})` : ""
    }. A newer certificate replaces it.`;
  return `This certificate was revoked by Capimax PropShare${
    c.revoked_at ? ` on ${day(c.revoked_at)}` : ""
  }.${c.revocation_reason ? ` Reason: ${c.revocation_reason}.` : ""}`;
}

function Section({ icon: Icon, title, rows }: { icon: LucideIcon; title: string; rows: [string, string][] }) {
  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        <Icon className="h-4 w-4 text-primary" /> {title}
      </h2>
      <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="break-words font-medium text-foreground">{value || "—"}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export default function VerifyCertificate() {
  const { code = "" } = useParams();
  const { data, error, isLoading } = useQuery({
    queryKey: ["verify-certificate", code],
    queryFn: () => certificateApi.verify(code),
    retry: false,
    refetchOnWindowFocus: false,
  });

  const header = (
    <div className="text-center">
      <img src="/capimax-logo.png" alt="Capimax PropShare" className="mx-auto mb-6 h-14 w-auto" />
      <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/5 px-4 py-1.5 text-sm font-medium text-primary">
        <BadgeCheck className="h-4 w-4" /> Certificate Verification
      </div>
    </div>
  );

  if (isLoading) {
    return (
      <div className="container mx-auto max-w-3xl px-4 py-16" data-testid="verify-loading">
        {header}
        <p className="mt-10 flex items-center justify-center gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" /> Verifying certificate…
        </p>
      </div>
    );
  }

  if (error || !data) {
    const status = error instanceof ApiError ? error.status : 0;
    const tooMany = status === 429;
    // only a 404 says the code matches no certificate; anything else is "try again"
    const unknown = status === 404;
    return (
      <div className="container mx-auto max-w-3xl px-4 py-16" data-testid="verify-not-found">
        {header}
        <Card className="mt-8">
          <CardContent className="space-y-4 p-8 text-center">
            <ShieldX className="mx-auto h-12 w-12 text-destructive" />
            <h1 className="text-2xl font-bold text-foreground">
              {unknown ? "Certificate Not Found" : tooMany ? "Too many checks" : "Could not verify right now"}
            </h1>
            <p className="text-muted-foreground">
              {tooMany ? (
                "Please wait a minute and try again."
              ) : !unknown ? (
                "The verification service did not answer. This says nothing about the certificate: please try again in a moment."
              ) : (
                <>
                  The verification code <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-sm">{code}</code>{" "}
                  does not match any certificate in our system. Check the code printed beside the
                  certificate's QR code, or contact {SUPPORT_EMAIL}.
                </>
              )}
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <Button asChild>
                <Link to="/verification-center">Enter another code</Link>
              </Button>
              <Button asChild variant="outline">
                <Link to="/">Return to Home</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const st = STATUS[data.status];
  return (
    <div className="container mx-auto max-w-3xl space-y-6 px-4 py-16" data-testid="verify-result">
      {header}

      <Card>
        <CardContent className="flex flex-col items-center gap-4 p-8 text-center">
          <div className={`flex h-16 w-16 items-center justify-center rounded-full ${st.tone}`}>
            <st.icon className="h-8 w-8" />
          </div>
          <Badge className={`border-0 px-3 py-1 text-sm ${st.badge}`} data-testid="verify-status">
            {st.label}
          </Badge>
          <h1 className="text-2xl font-bold text-foreground">{data.number}</h1>
          <p className="max-w-xl text-muted-foreground">{statusLine(data)}</p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-8 p-6 md:p-8">
          <Section
            icon={FileText}
            title="Certificate"
            rows={[
              ["Certificate number", data.number],
              ["Issue date", day(data.issued_at)],
              ["Issued by", data.issuer],
              ["Type", "Certificate of Ownership — fractional real-estate units"],
            ]}
          />
          <Section
            icon={User}
            title="Holder"
            rows={[
              ["Registered holder", data.holder_name],
              ["Investor ID", data.holder_ref],
            ]}
          />
          <Section
            icon={Building2}
            title="Property & SPV"
            rows={[
              ["Property", data.property_title],
              ["Location", data.location ?? "—"],
              ["Issuing SPV", data.spv_name ?? "—"],
              ["Jurisdiction", data.jurisdiction ?? "—"],
            ]}
          />
          <Section
            icon={BadgeCheck}
            title="Holding stated"
            rows={[
              ["Units", data.units.toLocaleString("en-US")],
              ["Share of the property", data.ownership],
              ["Unit price on the issue date", money(data.unit_price)],
              ["Recorded value on the issue date", money(data.value)],
            ]}
          />
          <Section
            icon={Fingerprint}
            title="Verification"
            rows={[
              ["Verification code", data.verification_code],
              ["Digital signature", data.signature],
            ]}
          />
        </CardContent>
      </Card>

      <p className="text-center text-sm text-muted-foreground">
        This verification was performed on{" "}
        {new Date(data.verified_at).toLocaleString("en-US", { dateStyle: "long", timeStyle: "short" })}.
        Questions: {SUPPORT_EMAIL}.{" "}
        <Link to="/verification-center" className="text-primary underline underline-offset-4">
          Verification Center
        </Link>
      </p>
    </div>
  );
}
