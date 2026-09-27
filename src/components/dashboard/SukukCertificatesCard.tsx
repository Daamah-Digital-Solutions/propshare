import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { FileText } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { investApi } from "@/lib/api";

/**
 * The investor's Nova Sukuk certificates — purchases and installment down payments paid with
 * one — and where each review stands: under review (units held), approved (units theirs,
 * pledged to Nova Finance), not accepted (with our team's reason) or pledge released.
 */
const STATUS: Record<
  string,
  { label: string; variant: "default" | "secondary" | "outline" | "destructive"; hint?: string }
> = {
  pending: {
    label: "Under review",
    variant: "secondary",
    hint: "The units are held for you while our team reviews the certificate.",
  },
  approved: {
    label: "Approved — pledged to Nova",
    variant: "default",
    hint: "The units are yours; they stay pledged to Nova Finance until it releases them.",
  },
  rejected: { label: "Not accepted", variant: "destructive" },
  released: {
    label: "Pledge released",
    variant: "outline",
    hint: "Nova Finance released the pledge: the units are free to sell or transfer.",
  },
};

const usd = (v: string) =>
  Number(v).toLocaleString("en-US", { style: "currency", currency: "USD" });

export function SukukCertificatesCard() {
  const { data } = useQuery({ queryKey: ["sukuk", "mine"], queryFn: investApi.mySukuk });
  const rows = data ?? [];
  if (rows.length === 0) return null;
  return (
    <Card className="bg-card border-border" data-testid="sukuk-certificates">
      <CardContent className="p-5 space-y-3">
        <p className="text-sm font-semibold text-foreground flex items-center gap-2">
          <FileText className="h-4 w-4 text-primary" /> Nova Sukuk certificates
        </p>
        {rows.map((c) => {
          const st = STATUS[c.status] ?? { label: c.status, variant: "outline" as const };
          return (
            <div key={c.certificate_id} className="rounded-lg bg-muted/50 p-3 text-sm space-y-1">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <span className="font-medium">
                  {c.kind === "purchase"
                    ? `${c.units} unit(s) of ${c.property_title}`
                    : `Installment plan down payment — ${c.property_title}`}{" "}
                  · {usd(c.amount_due)}
                </span>
                <Badge variant={st.variant}>{st.label}</Badge>
              </div>
              {c.status === "rejected" && c.review_note ? (
                <p className="text-xs text-muted-foreground">
                  Reason: {c.review_note} The units were released — you can submit a new
                  certificate or pay another way.
                </p>
              ) : (
                st.hint && <p className="text-xs text-muted-foreground">{st.hint}</p>
              )}
              <Link to={`/property/${c.property_id}`} className="text-xs text-primary underline">
                View property
              </Link>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

export default SukukCertificatesCard;
