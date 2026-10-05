import { useQueries, useQuery } from "@tanstack/react-query";
import { LineChart as LineChartIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { holdingsApi, propertyApi, type InstallmentPlan } from "@/lib/api";
import UnitPriceHistory from "@/components/property/UnitPriceHistory";
import { signedPct, unitPrice } from "@/lib/money";

const day = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });

/**
 * Reports: the unit price over time of every property the investor holds or is paying for by
 * installments. A property under construction earns by its price going up, so this is where
 * its return shows; the dashed line is what the investor paid per unit on average.
 */
export default function UnitPriceReport({ plans }: { plans: InstallmentPlan[] }) {
  const { data: holdings } = useQuery({ queryKey: ["holdings", "mine"], queryFn: holdingsApi.mine });

  const tracked = new Map<string, { id: string; title: string; averageCost: number | null }>();
  for (const h of holdings?.items ?? []) {
    tracked.set(h.property_id, {
      id: h.property_id,
      title: h.title ?? "Property",
      averageCost: h.average_cost != null ? Number(h.average_cost) : null,
    });
  }
  // a plan with no unit paid for yet is not a holding: its property still counts, at the
  // price the plan locked
  for (const plan of plans) {
    if (plan.status === "active" && !tracked.has(plan.property_id)) {
      tracked.set(plan.property_id, {
        id: plan.property_id,
        title: plan.property_title,
        // the price its holder got in at: the plan's own, or what they bought the position at
        averageCost: Number(plan.position?.entry_price ?? plan.unit_price),
      });
    }
  }
  const list = [...tracked.values()];
  const results = useQueries({
    queries: list.map((t) => ({
      queryKey: ["property-prices", t.id],
      queryFn: () => propertyApi.prices(t.id),
      retry: false,
    })),
  });
  if (list.length === 0) return null;
  const moved = list
    .map((t, i) => ({ ...t, history: results[i]?.data }))
    .filter((t) => t.history && t.history.points.length > 1);

  return (
    <Card className="bg-card border-border" data-testid="unit-price-report">
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <LineChartIcon className="h-5 w-5 text-primary" />
          Unit Price of Your Properties
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          The price your units are valued at and can be sold at. A property under construction pays no
          rent before handover: the change in its unit price is its return.
        </p>
      </CardHeader>
      <CardContent>
        {moved.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            The unit price of your properties has not changed since launch. A change appears here as
            soon as it is recorded.
          </p>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {moved.map((t) => {
              const history = t.history!;
              const now = Number(history.current_price);
              const onCost =
                t.averageCost != null && t.averageCost > 0 ? ((now - t.averageCost) / t.averageCost) * 100 : null;
              return (
                <div key={t.id} className="rounded-lg border border-border p-4 space-y-3" data-testid="unit-price-chart">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold text-foreground truncate">{t.title}</p>
                      <p className="text-xs text-muted-foreground">
                        Launched at {unitPrice(history.launch_price)}
                        {history.phase ? ` · ${history.phase}` : ""}
                        {history.updated_at ? ` · updated ${day(history.updated_at)}` : ""}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-lg font-bold text-foreground">{unitPrice(now)}</p>
                      <p
                        className={`text-xs font-medium ${
                          Number(history.change_pct) < 0 ? "text-destructive" : "text-primary"
                        }`}
                      >
                        {signedPct(history.change_pct)} since launch
                      </p>
                    </div>
                  </div>
                  <UnitPriceHistory history={history} averageCost={t.averageCost} rows={3} height={180} />
                  {t.averageCost != null && onCost != null && (
                    <p className="text-xs text-muted-foreground">
                      You paid {unitPrice(t.averageCost)} a unit on average:{" "}
                      <span className={onCost < 0 ? "text-destructive" : "text-primary"}>{signedPct(onCost)}</span> at
                      the price now.
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
