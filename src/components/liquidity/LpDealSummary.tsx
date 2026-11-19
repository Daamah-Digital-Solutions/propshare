import { useQuery } from "@tanstack/react-query";
import { liquidityApi } from "@/lib/api";
import { liquidityFees } from "@/lib/marketFees";
import { money } from "@/lib/money";

/**
 * What a liquidity provider's purchase comes to, before it confirms (client, 2026-11-18): the
 * value of the units, no purchase fee, and its share of the seller's fee, credited to its
 * wallet with the deal. Also what the seller receives.
 */
export default function LpDealSummary({ deal }: { deal: number }) {
  const { data: rates } = useQuery({ queryKey: ["liquidity", "settings"], queryFn: () => liquidityApi.settings() });
  if (!rates || !(deal > 0)) return null;
  const feePct = Number(rates.fee_pct);
  const sharePct = Number(rates.fee_share_pct ?? 0);
  const f = liquidityFees({ deal, feePct, sharePct });
  return (
    <div className="space-y-1.5 rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm" data-testid="lp-deal-summary">
      <div className="flex justify-between">
        <span className="text-muted-foreground">Value of the units (you pay)</span>
        <span className="font-semibold">{money(f.deal)}</span>
      </div>
      <div className="flex justify-between">
        <span className="text-muted-foreground">Purchase fee</span>
        <span className="font-medium">{money(0)}</span>
      </div>
      <div className="flex justify-between">
        <span className="text-muted-foreground">{`Your share of the seller's fee (${sharePct}%), credited with the deal`}</span>
        <span className="font-semibold text-primary" data-testid="lp-share">+{money(f.lpFeeShare)}</span>
      </div>
      <div className="flex justify-between border-t border-border pt-1.5 text-xs text-muted-foreground">
        <span>{`The seller receives the value less a ${feePct}% fee`}</span>
        <span>{money(f.sellerNet)}</span>
      </div>
    </div>
  );
}
