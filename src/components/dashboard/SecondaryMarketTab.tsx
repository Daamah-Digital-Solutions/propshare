import { Link } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowRightLeft } from "lucide-react";

/**
 * The dashboard's Secondary Market tab. The full, live buy/sell order book lives on the
 * dedicated `/secondary-market` page (wired in Phase 8) — this tab routes there rather
 * than duplicating a second (previously mock) order book. DELETE NOTHING: the tab stays,
 * it just points at the real feature.
 */
export const SecondaryMarketTab = () => {
  return (
    <Card className="bg-card border-border">
      <CardContent className="py-12 flex flex-col items-center text-center gap-4">
        <div className="h-14 w-14 rounded-full bg-success/15 flex items-center justify-center">
          <ArrowRightLeft className="h-7 w-7 text-success" />
        </div>
        <div>
          <h3 className="text-lg font-semibold">Secondary Market</h3>
          <p className="text-sm text-muted-foreground max-w-md mt-1">
            Buy and sell ownership units with other investors on the live secondary market.
          </p>
        </div>
        <Link to="/secondary-market">
          <Button className="gap-2">
            <ArrowRightLeft className="h-4 w-4" />
            Open Secondary Market
          </Button>
        </Link>
      </CardContent>
    </Card>
  );
};

export default SecondaryMarketTab;
