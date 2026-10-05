import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PriceHistory } from "@/lib/api";
import { signedPct, unitPrice } from "@/lib/money";

const day = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
const DAY_MS = 86_400_000;

/** Round axis values around the prices shown: [95, 100, 105, 110, 115] for a move from 100 to 110. */
function priceTicks(values: number[]): number[] {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const rough = Math.max(max - min, max * 0.02, 0.03) / 3;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const norm = rough / magnitude;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * magnitude;
  const low = Math.max(0, Math.floor(min / step) * step - step);
  const high = Math.ceil(max / step) * step + step;
  const ticks: number[] = [];
  for (let v = low; v <= high + step / 2; v += step) ticks.push(Math.round(v * 100) / 100);
  return ticks;
}

/**
 * A listing's unit price over time: a step line (the price holds until the next change is
 * recorded) and the latest changes under it. Every figure is the server's
 * (propertyApi.prices); nothing here projects a price forward.
 */
export default function UnitPriceHistory({
  history,
  averageCost = null,
  rows = 5,
  height = 200,
}: {
  history: PriceHistory;
  /** what the viewer paid per unit on average: drawn as a reference line */
  averageCost?: number | null;
  /** how many of the latest changes to list under the chart */
  rows?: number;
  height?: number;
}) {
  const changes = history.points.slice(1);
  if (changes.length === 0) {
    return (
      <p className="text-xs text-muted-foreground" data-testid="unit-price-history">
        The unit price has not changed since launch ({unitPrice(history.launch_price)}).
      </p>
    );
  }
  const line = history.points.map((p) => ({ t: new Date(p.at).getTime(), price: Number(p.price) }));
  // the last price holds until today
  const last = line[line.length - 1];
  const now = Date.now();
  if (now > last.t) line.push({ t: now, price: last.price });
  const latest = [...changes].reverse().slice(0, rows);
  // a short history is dated by the day, a long one by the month; one tick per distinct label
  const first = line[0].t;
  const end = line[line.length - 1].t;
  const byDay = end - first < 90 * DAY_MS;
  const dateTick = (t: number) =>
    new Date(t).toLocaleDateString("en-US", byDay ? { month: "short", day: "numeric" } : { month: "short", year: "numeric" });
  const seen = new Set<string>();
  const dateTicks = line.map((p) => p.t).filter((t) => !seen.has(dateTick(t)) && Boolean(seen.add(dateTick(t))));
  const yTicks = priceTicks([
    ...line.map((p) => p.price),
    ...(averageCost != null && averageCost > 0 ? [averageCost] : []),
  ]);

  return (
    <div className="space-y-3" data-testid="unit-price-history">
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={line} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              ticks={dateTicks}
              tickFormatter={dateTick}
              stroke="hsl(var(--muted-foreground))"
              fontSize={12}
            />
            <YAxis
              domain={[yTicks[0], yTicks[yTicks.length - 1]]}
              ticks={yTicks}
              tickFormatter={(v: number) => unitPrice(v)}
              stroke="hsl(var(--muted-foreground))"
              fontSize={12}
              width={56}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "8px",
              }}
              labelFormatter={(t: number) => day(new Date(t).toISOString())}
              formatter={(value: number) => [unitPrice(value), "Unit price"]}
            />
            {averageCost != null && averageCost > 0 && (
              <ReferenceLine
                y={averageCost}
                stroke="hsl(var(--muted-foreground))"
                strokeDasharray="4 4"
                label={{ value: "Your average cost", position: "insideBottomRight", fontSize: 11 }}
              />
            )}
            <Line
              type="stepAfter"
              dataKey="price"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              dot={{ r: 3 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <ul className="divide-y divide-border rounded-lg border border-border text-xs">
        {latest.map((p) => (
          <li key={p.at} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 px-3 py-2">
            <span className="text-muted-foreground">
              {day(p.at)}
              {p.label ? <span className="ml-2 font-medium text-foreground">{p.label}</span> : null}
              {p.note ? <span className="ml-2">{p.note}</span> : null}
            </span>
            <span className="font-semibold text-foreground">
              {unitPrice(p.price)}{" "}
              <span className={Number(p.change_pct) < 0 ? "text-destructive" : "text-success"}>
                {signedPct(p.change_pct)}
              </span>
            </span>
          </li>
        ))}
      </ul>
      {changes.length > latest.length && (
        <p className="text-[11px] text-muted-foreground">
          Showing the latest {latest.length} of {changes.length} changes.
        </p>
      )}
    </div>
  );
}
