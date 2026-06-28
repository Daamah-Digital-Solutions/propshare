import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ArrowRightLeft,
  Zap,
  Clock,
  CheckCircle2,
  XCircle,
  ListChecks,
  History,
  Activity,
  LogOut,
} from "lucide-react";
import { useCancelExitRequest, useExitRequests, type ExitRequest } from "./exitStore";
import { ExitButton } from "./ExitButton";
import { cn } from "@/lib/utils";

const STATUS_META: Record<
  ExitRequest["status"],
  { label: string; color: string; icon: typeof Clock }
> = {
  listed: { label: "Listed · awaiting buyer", color: "text-primary border-primary/30 bg-primary/5", icon: ListChecks },
  matching: { label: "Matching", color: "text-primary border-primary/30 bg-primary/5", icon: Activity },
  settling: { label: "Settling", color: "text-amber-600 border-amber-500/30 bg-amber-500/5", icon: Clock },
  completed: { label: "Completed", color: "text-emerald-600 border-emerald-500/30 bg-emerald-500/5", icon: CheckCircle2 },
  cancelled: { label: "Cancelled", color: "text-muted-foreground border-border bg-muted/30", icon: XCircle },
};

export function ExitRequestsPanel() {
  const items = useExitRequests();

  const pending = items.filter((i) => i.status === "listed" || i.status === "matching");
  const active = items.filter((i) => i.status === "settling");
  const completed = items.filter((i) => i.status === "completed");
  const all = items;

  const totals = {
    requests: all.length,
    listed: pending.length,
    settling: active.length,
    completed: completed.length,
  };

  return (
    <div className="space-y-5">
      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SummaryCard icon={ListChecks} label="Pending exits" value={totals.listed} />
        <SummaryCard icon={Clock} label="Settling" value={totals.settling} />
        <SummaryCard icon={CheckCircle2} label="Completed" value={totals.completed} />
        <SummaryCard icon={History} label="Total requests" value={totals.requests} />
      </div>

      <Card className="border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-3 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <LogOut className="h-5 w-5 text-primary" /> Exit Requests
            </CardTitle>
            <p className="text-sm text-muted-foreground mt-1">
              Track pending listings, liquidity provider requests, settlements and history.
            </p>
          </div>
          <ExitButton variant="default" label="New Exit" />
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="all">
            <TabsList className="bg-muted/50 flex-wrap h-auto">
              <TabsTrigger value="all">All ({all.length})</TabsTrigger>
              <TabsTrigger value="pending">Pending ({pending.length})</TabsTrigger>
              <TabsTrigger value="settling">Settling ({active.length})</TabsTrigger>
              <TabsTrigger value="completed">Completed ({completed.length})</TabsTrigger>
            </TabsList>
            <TabsContent value="all" className="mt-4"><ExitList items={all} /></TabsContent>
            <TabsContent value="pending" className="mt-4"><ExitList items={pending} /></TabsContent>
            <TabsContent value="settling" className="mt-4"><ExitList items={active} /></TabsContent>
            <TabsContent value="completed" className="mt-4"><ExitList items={completed} /></TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}

function SummaryCard({ icon: Icon, label, value }: { icon: typeof Clock; label: string; value: number }) {
  return (
    <Card className="border-border">
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="text-2xl font-bold mt-0.5">{value}</div>
          </div>
          <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
            <Icon className="h-5 w-5 text-primary" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ExitList({ items }: { items: ExitRequest[] }) {
  const cancelExitRequest = useCancelExitRequest();
  if (items.length === 0) {
    return (
      <div className="text-center py-10 text-sm text-muted-foreground">
        No exit requests in this category.
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {items.map((r) => {
        const meta = STATUS_META[r.status];
        const Icon = meta.icon;
        const MethodIcon = r.method === "secondary" ? ArrowRightLeft : Zap;
        return (
          <div key={r.id} className="flex flex-col md:flex-row md:items-center gap-3 p-3 rounded-xl border bg-card">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              {r.propertyImage ? (
                <img src={r.propertyImage} alt={r.propertyName} className="w-12 h-12 rounded-md object-cover" />
              ) : (
                <div className="w-12 h-12 rounded-md bg-primary/10 flex items-center justify-center">
                  <MethodIcon className="h-5 w-5 text-primary" />
                </div>
              )}
              <div className="min-w-0">
                <div className="font-semibold text-sm truncate">{r.propertyName}</div>
                <div className="text-xs text-muted-foreground truncate">
                  {r.id} · {new Date(r.createdAt).toLocaleDateString()}
                </div>
                <div className="flex items-center gap-2 mt-1 text-[11px] text-muted-foreground">
                  <MethodIcon className="h-3 w-3 text-primary" />
                  {r.method === "secondary" ? "Secondary market" : "Liquidity provider"}
                  <span>· {r.units} units @ ${r.pricePerUnit.toFixed(2)}</span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-3 md:grid-cols-3 gap-3 md:gap-6 text-xs md:text-sm">
              <div>
                <div className="text-[11px] text-muted-foreground">Net proceeds</div>
                <div className="font-semibold text-primary">${r.netProceeds.toLocaleString()}</div>
              </div>
              <div>
                <div className="text-[11px] text-muted-foreground">Settlement</div>
                <div className="font-semibold">{r.settlementEta}</div>
              </div>
              <div>
                <div className="text-[11px] text-muted-foreground">Remaining</div>
                <div className="font-semibold">{r.remainingUnits} units</div>
              </div>
            </div>

            <div className="flex items-center gap-2 md:flex-col md:items-end">
              <Badge variant="outline" className={cn("gap-1", meta.color)}>
                <Icon className="h-3 w-3" /> {meta.label}
              </Badge>
              {(r.status === "listed" || r.status === "matching") && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2 text-xs text-destructive hover:text-destructive"
                  onClick={() => cancelExitRequest(r.id)}
                >
                  Cancel
                </Button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
