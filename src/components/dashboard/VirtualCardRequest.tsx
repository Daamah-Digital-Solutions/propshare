import { CreditCard, Plus, Sparkles, Clock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export type VirtualCardRole = "developer" | "owner" | "broker" | "liquidity";

const ROLE_COPY: Record<VirtualCardRole, { title: string; subtitle: string }> = {
  developer: {
    title: "Developer Virtual Cards",
    subtitle: "Fund operations, milestones and team spending directly from your project wallet.",
  },
  owner: {
    title: "Property Owner Virtual Cards",
    subtitle: "Spend rental income and distributions to manage and operate your properties.",
  },
  broker: {
    title: "Broker Virtual Cards",
    subtitle: "Spend commissions and platform earnings instantly through dedicated broker cards.",
  },
  liquidity: {
    title: "Liquidity Provider Virtual Cards",
    subtitle: "Access platform returns and liquidity allocations through institutional cards.",
  },
};

interface Props {
  role: VirtualCardRole;
}

/**
 * Virtual cards are deferred out of v1 (D9). This surface degrades honestly to a
 * "not yet available" state across ALL roles — it never fakes a successful card
 * issuance. The real feature (issuance, funding, spend controls) is a later phase.
 */
export function VirtualCardRequest({ role }: Props) {
  const copy = ROLE_COPY[role];
  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <CreditCard className="w-5 h-5 text-primary" />
            <h2 className="text-2xl font-bold">{copy.title}</h2>
            <Badge variant="outline" className="border-amber-500/30 text-amber-600">
              <Clock className="w-3 h-3 mr-1" /> Coming soon
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground max-w-2xl">{copy.subtitle}</p>
        </div>
        <Button className="gap-2" disabled>
          <Plus className="w-4 h-4" /> Request Virtual Card
        </Button>
      </div>

      <Card className="border-dashed">
        <CardContent className="py-12 flex flex-col items-center text-center gap-3">
          <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
            <Sparkles className="h-6 w-6 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold">Virtual cards are not yet available</h3>
          <p className="text-sm text-muted-foreground max-w-md">
            Virtual card issuance and spend controls are planned for a future release. This
            feature is not enabled yet — no cards can be issued at this time.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

export default VirtualCardRequest;
