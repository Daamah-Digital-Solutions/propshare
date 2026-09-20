import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { LifeBuoy, ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ticketsApi } from "@/lib/assistantApi";

const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  waiting_user: "Waiting for you",
  resolved: "Resolved",
  closed: "Closed",
};

export function statusVariant(status: string): "default" | "secondary" | "outline" | "destructive" {
  if (status === "waiting_user") return "destructive";
  if (status === "resolved" || status === "closed") return "secondary";
  return "default";
}

const MyTickets = () => {
  const { data, isLoading, isError } = useQuery({ queryKey: ["tickets"], queryFn: ticketsApi.list });
  return (
    <div className="container mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="flex items-center gap-2 text-2xl font-bold">
          <LifeBuoy className="h-6 w-6 text-primary" /> My support tickets
        </h1>
        <Button asChild variant="outline">
          <Link to="/support">New request</Link>
        </Button>
      </div>
      {isLoading && <p className="text-muted-foreground">Loading…</p>}
      {isError && <p className="text-destructive">Could not load your tickets.</p>}
      {data && data.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            No tickets yet. Ask the assistant or use the support form when you need a person.
          </CardContent>
        </Card>
      )}
      <div className="space-y-3">
        {data?.map((t) => (
          <Link key={t.id} to={`/support/tickets/${t.id}`} className="block">
            <Card className="transition-colors hover:bg-muted/40">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 py-4">
                <div className="min-w-0">
                  <CardTitle className="truncate text-base">
                    <span className="me-2 font-mono text-xs text-muted-foreground">{t.ticket_no}</span>
                    {t.subject ?? "Support request"}
                  </CardTitle>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {t.category ?? "other"} · {new Date(t.created_at).toLocaleDateString()}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={statusVariant(t.status)}>{STATUS_LABEL[t.status] ?? t.status}</Badge>
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </div>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
};

export default MyTickets;
