import { Card, CardContent } from "@/components/ui/card";
import { FileText, Shield } from "lucide-react";

/**
 * Investment certificates / documents are deferred to a standalone phase (needs app
 * document storage + generation). Per DELETE NOTHING, this surface is kept but
 * honest-disabled — no fabricated certificates, no dead View/Download buttons.
 * Real ownership is always readable from the live portfolio/holdings APIs.
 */
export const InvestmentCertificates = () => {
  return (
    <div className="space-y-6">
      <Card className="bg-card border-border border-dashed">
        <CardContent className="py-12 flex flex-col items-center text-center gap-3">
          <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
            <FileText className="h-6 w-6 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold">Investment documents are not available yet</h3>
          <p className="text-sm text-muted-foreground max-w-md">
            Downloadable certificates, SPV agreements and tax statements are planned for a
            future release once secure document storage is provisioned. Your live ownership
            is always shown in the Portfolio and Investments tabs.
          </p>
        </CardContent>
      </Card>

      {/* Legal Notice — informational only (no fabricated documents). */}
      <Card className="bg-muted/30 border-border">
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <Shield className="h-6 w-6 text-primary flex-shrink-0" />
            <div>
              <h4 className="font-semibold text-foreground mb-2">Important Notice</h4>
              <p className="text-sm text-muted-foreground">
                When available, your investment certificates will be legally binding
                documents representing your ownership stake in the respective Special Purpose
                Vehicle (SPV), usable for tax reporting and ownership verification. For any
                legal inquiries, please contact our support team.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
