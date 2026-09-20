import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Send, Star } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { ticketsApi } from "@/lib/assistantApi";
import { statusVariant } from "@/pages/MyTickets";
import { cn } from "@/lib/utils";

const TicketDetail = () => {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const { toast } = useToast();
  const [body, setBody] = useState("");
  const { data: t, isLoading, isError } = useQuery({
    queryKey: ["ticket", id],
    queryFn: () => ticketsApi.get(id),
    enabled: !!id,
  });
  const reply = useMutation({
    mutationFn: () => ticketsApi.reply(id, body),
    onSuccess: (updated) => {
      qc.setQueryData(["ticket", id], updated);
      setBody("");
    },
    onError: (e: Error) => toast({ title: "Could not send", description: e.message, variant: "destructive" }),
  });
  const rate = useMutation({
    mutationFn: (score: number) => ticketsApi.rate(id, score),
    onSuccess: (updated) => {
      qc.setQueryData(["ticket", id], updated);
      toast({ title: "Thanks for your rating" });
    },
    onError: (e: Error) => toast({ title: "Could not rate", description: e.message, variant: "destructive" }),
  });

  if (isLoading) return <div className="container mx-auto max-w-3xl px-4 py-8 text-muted-foreground">Loading…</div>;
  if (isError || !t) return <div className="container mx-auto max-w-3xl px-4 py-8 text-destructive">Ticket not found.</div>;
  const closed = t.status === "closed";
  const ratable = t.status === "resolved" || t.status === "closed";

  return (
    <div className="container mx-auto max-w-3xl px-4 py-8">
      <Link to="/support/tickets" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> My tickets
      </Link>
      <Card>
        <CardHeader className="flex flex-row items-start justify-between space-y-0">
          <div>
            <CardTitle className="text-lg">
              <span className="me-2 font-mono text-xs text-muted-foreground">{t.ticket_no}</span>
              {t.subject ?? "Support request"}
            </CardTitle>
            <div className="mt-1 text-xs text-muted-foreground">
              {t.category ?? "other"} · {t.priority} priority · opened {new Date(t.created_at).toLocaleString()}
            </div>
          </div>
          <Badge variant={statusVariant(t.status)}>{t.status.replace("_", " ")}</Badge>
        </CardHeader>
        <CardContent className="space-y-3">
          {t.messages.length === 0 && (
            <p className="text-sm text-muted-foreground">
              This ticket was opened from the assistant; the team has your account context and will reply here.
            </p>
          )}
          {t.messages.map((m) => (
            <div key={m.id} className={cn("flex", m.author_type === "user" ? "justify-end" : "justify-start")}>
              <div
                dir="auto"
                className={cn(
                  "max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm",
                  m.author_type === "user" ? "rounded-br-sm bg-primary text-primary-foreground" : "rounded-bl-sm border border-border bg-muted/40",
                )}
              >
                <div className="mb-1 text-[10px] opacity-70">
                  {m.author_type === "user" ? "You" : "Support"} · {new Date(m.created_at).toLocaleString()}
                </div>
                {m.body}
              </div>
            </div>
          ))}
          {!closed && (
            <form
              className="flex items-end gap-2 pt-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (body.trim()) reply.mutate();
              }}
            >
              <Textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write a reply…" rows={2} dir="auto" />
              <Button type="submit" disabled={reply.isPending || !body.trim()} aria-label="Send reply">
                <Send className="h-4 w-4" />
              </Button>
            </form>
          )}
          {ratable && (
            <div className="flex items-center gap-1 border-t border-border pt-3 text-sm">
              <span className="me-2 text-muted-foreground">{t.csat ? "Your rating:" : "How did we do?"}</span>
              {[1, 2, 3, 4, 5].map((s) => (
                <button
                  key={s}
                  type="button"
                  aria-label={`Rate ${s}`}
                  disabled={rate.isPending}
                  onClick={() => rate.mutate(s)}
                  className={cn("rounded p-1", (t.csat ?? 0) >= s ? "text-amber-500" : "text-muted-foreground hover:text-amber-500")}
                >
                  <Star className="h-4 w-4" fill={(t.csat ?? 0) >= s ? "currentColor" : "none"} />
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default TicketDetail;
