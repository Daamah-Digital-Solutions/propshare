import { Blocks, ExternalLink, FileCheck2, LineChart, Scale, ShieldCheck, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  INDEPENDENT_VERIFICATION,
  VERIFICATION_PARTNERS,
  VERIFY_INTRO,
  displayUrl,
} from "@/lib/verificationPartners";

/**
 * "Verify Your Documents": the five designated verification partners, each for one kind of
 * record, with what to enter there and the link to their own site. Shared by the public
 * Verification Center page and the dashboard's Verification tab, like the Capimax Trust card.
 */

const ICONS: Record<string, LucideIcon> = {
  capimax_documents: FileCheck2,
  valuation_financial: LineChart,
  insurance: ShieldCheck,
  legal: Scale,
  blockchain: Blocks,
};

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
