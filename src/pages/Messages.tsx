import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCheck, Loader2, Mail, MailOpen } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, messagesApi } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Messages: what the Capimax PropShare team writes to members from the admin panel (client,
 * 2026-10-28, as on Capimax BRX), to one member or to everyone holding a role. Every role has
 * this inbox. Opening a message marks it read; the notification and the email link here, to
 * /messages?id={message}.
 */

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });

export default function Messages() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const openId = params.get("id");

  const list = useQuery({ queryKey: ["messages", "list"], queryFn: () => messagesApi.list() });
  const open = useQuery({
    queryKey: ["messages", "one", openId],
    queryFn: () => messagesApi.get(openId as string),
    enabled: !!openId,
    retry: false,
  });

  // opening a message marks it read on the server: show it in the list and the badge
  useEffect(() => {
    if (open.data) qc.invalidateQueries({ queryKey: ["messages", "list"] });
  }, [open.data, qc]);

  const readAll = useMutation({
    mutationFn: () => messagesApi.readAll(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["messages", "list"] }),
  });

  const items = list.data?.items ?? [];
  const unread = list.data?.unread ?? 0;
  const notFound = open.error instanceof ApiError && open.error.status === 404;
  const show = (id: string) => setParams({ id });
  const back = () => setParams({});

  return (
    <div className="container mx-auto max-w-5xl space-y-6 px-4 py-8">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
            <Mail className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="flex items-center gap-3 text-2xl font-bold text-foreground">
              Messages
              {unread > 0 && (
                <Badge className="bg-primary text-primary-foreground" data-testid="unread-count">
                  {unread} unread
                </Badge>
              )}
            </h1>
            <p className="mt-1 text-muted-foreground">Messages from the Capimax PropShare team</p>
          </div>
        </div>
        {unread > 0 && (
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            disabled={readAll.isPending}
            onClick={() => readAll.mutate()}
          >
            <CheckCheck className="h-4 w-4" /> Mark all read
          </Button>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className={cn("min-w-0 lg:col-span-2", openId && "hidden lg:block")}>
          <CardContent className="divide-y divide-border p-0" data-testid="message-list">
            {list.isLoading ? (
              <div className="flex justify-center p-10">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : items.length === 0 ? (
              <div className="flex flex-col items-center px-6 py-16 text-center">
                <Mail className="mb-4 h-12 w-12 text-muted-foreground/50" />
                <p className="font-semibold text-foreground">No messages yet</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Messages the Capimax PropShare team sends you will appear here.
                </p>
              </div>
            ) : (
              items.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => show(m.id)}
                  aria-current={openId === m.id ? "true" : undefined}
                  className={cn(
                    "w-full p-4 text-start transition-colors hover:bg-muted/40",
                    openId === m.id && "bg-primary/5",
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className={cn("truncate text-foreground", !m.read && "font-semibold")}>
                      {!m.read && (
                        <span
                          className="me-2 inline-block h-2 w-2 rounded-full bg-primary align-middle"
                          aria-label="Unread"
                        />
                      )}
                      {m.subject}
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground">{when(m.created_at)}</span>
                  </div>
                  <p className="mt-1 truncate text-sm text-muted-foreground">{m.preview}</p>
                </button>
              ))
            )}
          </CardContent>
        </Card>

        <Card className={cn("min-w-0 lg:col-span-3", !openId && "hidden lg:block")}>
          <CardContent className="p-6" data-testid="message-view">
            {openId && open.isLoading ? (
              <div className="flex justify-center py-16">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : openId && notFound ? (
              <p className="py-16 text-center text-muted-foreground">
                This message is not in your inbox.
              </p>
            ) : openId && open.data ? (
              <article className="space-y-4">
                <Button variant="ghost" size="sm" className="-ms-2 gap-2 lg:hidden" onClick={back}>
                  <ArrowLeft className="h-4 w-4 rtl:rotate-180" /> All messages
                </Button>
                <div>
                  <h2 className="text-xl font-semibold text-foreground">{open.data.subject}</h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    From the Capimax PropShare team · {when(open.data.created_at)}
                  </p>
                </div>
                <div
                  className="whitespace-pre-wrap border-t border-border pt-4 leading-relaxed text-foreground"
                  dir="auto"
                >
                  {open.data.body}
                </div>
              </article>
            ) : (
              <div className="flex flex-col items-center py-16 text-center text-muted-foreground">
                <MailOpen className="mb-3 h-10 w-10 opacity-50" />
                Choose a message to read it
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
