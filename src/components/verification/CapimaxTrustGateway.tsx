import { ExternalLink, FileCheck2, ListChecks, Download, ScrollText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

/**
 * The Capimax Trust hand-off, shared by the public Verification Center page and the
 * Verification tab of the investor dashboard so the two can never drift apart. No
 * verification logic lives here: every document is verified on Capimax Trust.
 */

// The central Capimax Trust verification gateway. Single source of truth for the destination.
export const CAPIMAX_TRUST_URL = "https://www.capimax.pro";

const CAPABILITIES = [
  { icon: FileCheck2, title: "Verify authenticity", text: "Confirm that a document or certificate is genuine and was officially issued." },
  { icon: ListChecks, title: "Review status", text: "See the current status of any registered document or record." },
  { icon: Download, title: "Download the official copy", text: "Obtain the authoritative, official version of the document." },
  { icon: ScrollText, title: "View verification data", text: "Inspect the verification details attached to each document." },
];

export function TrustGatewayCard({ compact = false }: { compact?: boolean }) {
  return (
    <Card className="border-primary/20 overflow-hidden">
      <div
        className={`bg-gradient-to-br from-primary/10 to-transparent text-center ${
          compact ? "p-6 md:p-8" : "p-8 md:p-12"
        }`}
      >
        {/* Official Capimax Trust logo on a clean white plate (the artwork has a light ground). */}
        <div
          className={`mx-auto inline-flex items-center justify-center rounded-2xl bg-white shadow-sm ring-1 ring-border ${
            compact ? "mb-4 p-4" : "mb-6 p-6"
          }`}
        >
          <img
            src="/capimax-trust-logo.png"
            alt="Capimax Trust — Verified · Secured · Connected"
            className={compact ? "h-16 w-auto" : "h-24 md:h-28 w-auto"}
          />
        </div>
        <h2 className="sr-only">Capimax Trust</h2>
        <p className="mt-1 text-sm font-medium tracking-wide text-primary uppercase">
          Central Verification Gateway
        </p>
        <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
          Continue to Capimax Trust to verify a document, review its status, and download the
          official copy.
        </p>
        <div className={compact ? "mt-5" : "mt-7"}>
          <Button asChild size="lg" className="gap-2 text-base">
            <a href={CAPIMAX_TRUST_URL} target="_blank" rel="noopener noreferrer">
              Go to Capimax Trust <ExternalLink className="h-4 w-4" />
            </a>
          </Button>
        </div>
        <a
          href={CAPIMAX_TRUST_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 inline-block text-sm text-primary underline underline-offset-4 hover:text-primary/80"
        >
          www.capimax.pro
        </a>
      </div>
    </Card>
  );
}

export function TrustCapabilities() {
  return (
    <div>
      <h3 className="text-center text-xl font-semibold text-foreground mb-6">
        On Capimax Trust you can
      </h3>
      <div className="grid gap-4 sm:grid-cols-2">
        {CAPABILITIES.map((c) => (
          <Card key={c.title}>
            <CardContent className="flex items-start gap-4 p-5">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                <c.icon className="h-5 w-5 text-primary" />
              </div>
              <div>
                <div className="font-semibold text-foreground">{c.title}</div>
                <p className="mt-1 text-sm text-muted-foreground">{c.text}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function TrustScopeNote() {
  return (
    <p className="text-center text-sm text-muted-foreground max-w-2xl mx-auto">
      To keep verification consistent and trustworthy across the group, all document
      verification for the Capimax ecosystem is handled exclusively by Capimax Trust. This page
      is a secure gateway to that central service.
    </p>
  );
}
