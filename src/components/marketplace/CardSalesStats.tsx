import { Users } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { fundingBar, fundingText } from "@/lib/funding";

/**
 * On every property card: how many people hold the property and how much of it is sold
 * (client letter, 2026-11-18, as on Capimax BRX). Both come from the server and update by
 * themselves: the investors are the people holding units or paying a plan now, the share sold
 * is the funded share the admin panel shows.
 */
export default function CardSalesStats({ investors: raw, sold }: { investors: number; sold: number }) {
  const investors = Number(raw ?? 0);
  return (
    <div className="mb-4 grid grid-cols-[auto_1fr] items-center gap-3" data-testid="card-sales">
      <div className="rounded-lg bg-secondary/60 px-3 py-2 text-center">
        <div className="flex items-center justify-center gap-1 font-bold text-foreground">
          <Users className="h-3.5 w-3.5 text-primary" />
          <span data-testid="card-investors">{investors.toLocaleString("en-US")}</span>
        </div>
        <p className="text-[11px] text-muted-foreground">{investors === 1 ? "investor" : "investors"}</p>
      </div>
      <div className="min-w-0">
        <div className="mb-1.5 flex justify-between text-sm">
          <span className="text-muted-foreground">Sold</span>
          <span className="font-semibold text-primary" data-testid="card-sold">
            {fundingText(sold)}
          </span>
        </div>
        <Progress value={fundingBar(sold)} className="h-2" />
      </div>
    </div>
  );
}
