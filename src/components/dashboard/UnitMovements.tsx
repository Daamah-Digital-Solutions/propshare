import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowDownLeft, ArrowUpRight, FileText } from "lucide-react";
import { investApi } from "@/lib/api";
import { StatementPeriodForm } from "./AccountStatementCard";
import { movementText, shortDay as day } from "@/lib/familyActivity";

// How the units in "Active Investments" got there, and where units that left went: every
// line of the member's ownership ledger, with the other person named for a family transfer
// or an inheritance (client, 2026-10-07: a transfer "left no trace" on this page).

const FIRST = 8;

export const UnitMovements = () => {
  const { data } = useQuery({ queryKey: ["unit-movements"], queryFn: () => investApi.movements(100) });
  const [all, setAll] = useState(false);
  const [statement, setStatement] = useState(false);
  const items = data?.items ?? [];
  if (items.length === 0) return null;
  const shown = all ? items : items.slice(0, FIRST);

  return (
    <Card className="bg-card border-border" data-testid="unit-movements">
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="text-lg">Unit Movements</CardTitle>
          <p className="text-sm text-muted-foreground mt-1.5">
            Every purchase, sale and transfer of your units, newest first.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          aria-expanded={statement}
          onClick={() => setStatement((v) => !v)}
        >
          <FileText className="h-4 w-4" /> Download statement
        </Button>
      </CardHeader>
      <CardContent>
        {statement && (
          <div className="mb-4 rounded-lg border border-border bg-muted/30 p-4 space-y-3" data-testid="unit-statement">
            <p className="text-sm text-muted-foreground">
              Every unit movement in the period you choose, with the units held in each property
              after it, and per property the units held at the start and at the end. Dates are in
              UTC and both days are included.
            </p>
            <StatementPeriodForm
              download={investApi.downloadMovementsStatement}
              filePrefix="capimax-unit-statement"
              idPrefix="unit-statement"
            />
          </div>
        )}
        <div className="divide-y divide-border">
          {shown.map((m) => (
            <div key={m.id} className="flex items-center justify-between gap-3 py-3" data-testid="movement-row">
              <div className="flex items-center gap-3 min-w-0">
                <div
                  className={`h-9 w-9 rounded-full flex items-center justify-center shrink-0 ${
                    m.direction === "in" ? "bg-primary/10" : "bg-muted"
                  }`}
                >
                  {m.direction === "in" ? (
                    <ArrowDownLeft className="h-4 w-4 text-primary" />
                  ) : (
                    <ArrowUpRight className="h-4 w-4 text-muted-foreground" />
                  )}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{movementText(m)}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {m.property_title ?? "Property"}{m.at ? ` · ${day(m.at)}` : ""}
                  </p>
                </div>
              </div>
              <p className={`text-sm font-semibold shrink-0 ${m.units >= 0 ? "text-primary" : "text-foreground"}`}>
                {m.units >= 0 ? "+" : "−"}
                {Math.abs(m.units)} unit{Math.abs(m.units) === 1 ? "" : "s"}
              </p>
            </div>
          ))}
        </div>
        {items.length > FIRST && (
          <div className="pt-3 text-center">
            <Button variant="ghost" size="sm" onClick={() => setAll((v) => !v)}>
              {all ? "Show fewer" : `Show all ${items.length}`}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default UnitMovements;
