import { Card, CardContent } from "@/components/ui/card";
import { Calendar, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";

/**
 * Installment plans (down payment + N dated installments for under-construction
 * properties) are deferred to their own phase. This surface degrades honestly to a
 * "not yet available" state — kept in the tree (DELETE NOTHING), shows no mock schedule.
 */
export const InstallmentSchedule = () => {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Calendar className="h-5 w-5 text-primary" />
        <h2 className="text-2xl font-bold">Installment Plans</h2>
        <Badge variant="outline" className="border-amber-500/30 text-amber-600">
          <Clock className="w-3 h-3 mr-1" /> Coming soon
        </Badge>
      </div>

      <Card className="border-dashed">
        <CardContent className="py-12 flex flex-col items-center text-center gap-3">
          <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
            <Calendar className="h-6 w-6 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold">Installment plans are not available yet</h3>
          <p className="text-sm text-muted-foreground max-w-md">
            Paying for under-construction properties in scheduled installments is planned for a
            future release. Lump-sum investment is available today on the marketplace.
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default InstallmentSchedule;
