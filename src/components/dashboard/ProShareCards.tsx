import { CreditCard, Plus, Clock, Sparkles } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

/**
 * Investor virtual cards ("ProShare Cards"). Virtual cards are deferred out of v1 (D9),
 * across ALL roles. This surface degrades honestly to a "not yet available" state — it
 * never fakes a card issuance. Kept in the tree (DELETE NOTHING); the real feature
 * (issuance, funding, spend controls) lands in a future phase.
 */
export const ProShareCards = () => {
  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <CreditCard className="w-5 h-5 text-primary" />
            <h2 className="text-2xl font-bold">ProShare Cards</h2>
            <Badge variant="outline" className="border-amber-500/30 text-amber-600">
              <Clock className="w-3 h-3 mr-1" /> Coming soon
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Spend rental income and returns directly through dedicated virtual cards.
          </p>
        </div>
        <Button className="gap-2" disabled>
          <Plus className="w-4 h-4" /> Request Card
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
};

export default ProShareCards;
