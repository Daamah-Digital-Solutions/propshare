import { useState } from "react";
import { FileSpreadsheet, FileText } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, walletApi, type StatementFormat } from "@/lib/api";
import { saveBlob } from "@/lib/certificates";

/** Server rule mirrored for instant feedback: whole UTC days, up to three years, not future. */
const MAX_DAYS = 3 * 366;

const iso = (d: Date) => d.toISOString().slice(0, 10);

function utcToday(): Date {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
}

type Preset = { id: string; label: string; range: () => [Date, Date] };

const PRESETS: Preset[] = [
  {
    id: "this-month",
    label: "This month",
    range: () => {
      const t = utcToday();
      return [new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), 1)), t];
    },
  },
  {
    id: "last-month",
    label: "Last month",
    range: () => {
      const t = utcToday();
      return [
        new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth() - 1, 1)),
        new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), 0)),
      ];
    },
  },
  {
    id: "last-3-months",
    label: "Last 3 months",
    range: () => {
      const t = utcToday();
      return [new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth() - 3, t.getUTCDate() + 1)), t];
    },
  },
  {
    id: "this-year",
    label: "This year",
    range: () => {
      const t = utcToday();
      return [new Date(Date.UTC(t.getUTCFullYear(), 0, 1)), t];
    },
  },
];

export function validatePeriod(start: string, end: string, today = iso(utcToday())): string | null {
  if (!start || !end) return "Choose both dates.";
  if (start > end) return "The start date must be on or before the end date.";
  if (end > today) return "The end date cannot be in the future.";
  const days = (Date.parse(end) - Date.parse(start)) / 86_400_000 + 1;
  if (days > MAX_DAYS) return "A statement can cover up to three years. Choose a shorter period.";
  return null;
}

export function AccountStatementCard() {
  const [initialStart, initialEnd] = PRESETS[0].range();
  const [start, setStart] = useState(iso(initialStart));
  const [end, setEnd] = useState(iso(initialEnd));
  const [busy, setBusy] = useState<StatementFormat | null>(null);
  const problem = validatePeriod(start, end);

  const download = async (format: StatementFormat) => {
    if (problem) return;
    setBusy(format);
    try {
      const blob = await walletApi.downloadStatement(start, end, format);
      saveBlob(blob, `capimax-statement-${start}-to-${end}.${format}`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not create the statement. Please try again.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card data-testid="account-statement">
      <CardHeader>
        <CardTitle className="text-lg">Account statement</CardTitle>
        <CardDescription>
          Every wallet movement in the period you choose, with opening and closing balances and
          your holdings at the end of the period. Dates are in UTC and both days are included.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <Button
              key={p.id}
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                const [s, e] = p.range();
                setStart(iso(s));
                setEnd(iso(e));
              }}
            >
              {p.label}
            </Button>
          ))}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="statement-start">From</Label>
            <Input id="statement-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="statement-end">To</Label>
            <Input id="statement-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </div>
        </div>
        {problem && (
          <p role="alert" className="text-sm text-destructive">
            {problem}
          </p>
        )}
        <div className="flex flex-col sm:flex-row gap-2">
          <Button className="gap-2" disabled={!!problem || busy !== null} onClick={() => download("pdf")}>
            <FileText className="h-4 w-4" />
            {busy === "pdf" ? "Preparing PDF…" : "Download PDF"}
          </Button>
          <Button
            variant="outline"
            className="gap-2"
            disabled={!!problem || busy !== null}
            onClick={() => download("xlsx")}
          >
            <FileSpreadsheet className="h-4 w-4" />
            {busy === "xlsx" ? "Preparing Excel…" : "Download Excel"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
