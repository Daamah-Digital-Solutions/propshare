import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Blocks,
  ExternalLink,
  FileCheck2,
  LineChart,
  QrCode,
  Scale,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  INDEPENDENT_VERIFICATION,
  VERIFICATION_PARTNERS,
  VERIFY_INTRO,
  displayUrl,
} from "@/lib/verificationPartners";

/**
 * "Verify Your Documents": where each kind of record is verified, with what to do. The first,
 * investment certificates, is checked here: its QR code opens /verify/{code}, and the form
 * below takes the code for anyone who cannot scan it (as on Capimax BRX). The others link to
 * their partner's own site. Shared by the public Verification Center page and the dashboard's
 * Verification tab, like the Capimax Trust card.
 */

const ICONS: Record<string, LucideIcon> = {
  capimax_certificates: QrCode,
  valuation_financial: LineChart,
  insurance: ShieldCheck,
  legal: Scale,
  blockchain: Blocks,
};

/** The verification code printed beside a certificate's QR code -> its page. */
function CertificateCheck() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const value = code.trim();
  return (
    <form
      className="mt-4 flex flex-col gap-2 sm:flex-row"
      data-testid="certificate-check"
      onSubmit={(e) => {
        e.preventDefault();
        if (value) navigate(`/verify/${encodeURIComponent(value)}`);
      }}
    >
      <Input
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="Verification code on the certificate"
        aria-label="Verification code on the certificate"
        dir="ltr"
        autoComplete="off"
        spellCheck={false}
        className="font-mono sm:flex-1"
      />
      <Button type="submit" className="gap-2" disabled={!value}>
        <QrCode className="h-4 w-4" /> Verify Certificate
      </Button>
    </form>
  );
}

export function VerificationPartners({ compact = false }: { compact?: boolean }) {
  return (
    <section aria-labelledby="verify-your-documents" className="space-y-6" data-testid="verification-partners">
      <div className={compact ? "" : "text-center"}>
        <h2
          id="verify-your-documents"
          className={`font-bold text-foreground ${compact ? "text-xl" : "text-2xl md:text-3xl"}`}
        >
          {VERIFY_INTRO.title}
        </h2>
        <p className={`mt-2 text-muted-foreground ${compact ? "" : "mx-auto max-w-2xl"}`}>
          {VERIFY_INTRO.text}
        </p>
      </div>

      <ol className="space-y-4">
        {VERIFICATION_PARTNERS.map((p, i) => {
          const Icon = ICONS[p.key] ?? FileCheck2;
          return (
            <li key={p.key} data-testid={`verification-partner-${p.key}`}>
              <Card className="overflow-hidden">
                <CardContent className="p-5 md:p-6">
                  <div className="flex items-start gap-4">
                    <div className="hidden h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 sm:flex">
                      <Icon className="h-5 w-5 text-primary" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="text-lg font-semibold leading-snug text-foreground">
                        <span className="text-primary">{i + 1}.</span> {p.title}
                      </h3>
                      <p className="mt-0.5 text-sm font-medium text-primary">{p.providerLine}</p>
                      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{p.description}</p>
                      <p className="mt-3 rounded-lg bg-muted/50 px-3 py-2 text-sm leading-relaxed text-foreground">
                        {p.howTo}
                      </p>
                      {p.internal ? (
                        <CertificateCheck />
                      ) : (
                        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                          <Button asChild className="gap-2 self-start">
                            <a href={p.url} target="_blank" rel="noopener noreferrer">
                              {p.action} <ExternalLink className="h-4 w-4" />
                            </a>
                          </Button>
                          <a
                            href={p.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="min-w-0 text-sm sm:text-right"
                          >
                            <span className="block font-medium text-primary underline underline-offset-4 hover:text-primary/80">
                              {p.linkLabel}
                            </span>
                            <span className="block break-all text-xs text-muted-foreground">{displayUrl(p.url)}</span>
                          </a>
                        </div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </li>
          );
        })}
      </ol>

      <div className={`rounded-xl border border-border bg-muted/30 p-5 ${compact ? "" : "text-center"}`}>
        <h3 className="font-semibold text-foreground">{INDEPENDENT_VERIFICATION.title}</h3>
        <p className={`mt-2 text-sm leading-relaxed text-muted-foreground ${compact ? "" : "mx-auto max-w-2xl"}`}>
          {INDEPENDENT_VERIFICATION.text}
        </p>
      </div>
    </section>
  );
}
