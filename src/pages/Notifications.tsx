import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, Check, CheckCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { notificationApi } from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  kyc: "Identity",
  investment: "Investment",
  return: "Returns",
  withdrawal: "Withdrawal",
  deposit: "Deposit",
  secondary: "Secondary market",
  liquidity: "Liquidity",
  family: "Family",
  broker: "Broker",
  info: "Notice",
};

const Notifications = () => {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: () => notificationApi.list(),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["notifications", "list"] });
    qc.invalidateQueries({ queryKey: ["notifications", "unread-count"] });
  };
  const markRead = useMutation({ mutationFn: notificationApi.markRead, onSuccess: invalidate });
  const markAll = useMutation({ mutationFn: notificationApi.markAllRead, onSuccess: invalidate });

  const items = data?.items ?? [];

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Bell className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">Notifications</h1>
          {(data?.unread_count ?? 0) > 0 && (
            <Badge className="bg-primary text-primary-foreground">{data?.unread_count} unread</Badge>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          disabled={(data?.unread_count ?? 0) === 0 || markAll.isPending}
          onClick={() => markAll.mutate()}
        >
          <CheckCheck className="h-4 w-4" />
          Mark all read
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Loading…</p>
          ) : items.length === 0 ? (
            <p className="text-sm text-muted-foreground py-12 text-center">
              You're all caught up — no notifications yet.
            </p>
          ) : (
            <div className="divide-y divide-border">
              {items.map((n) => (
                <div
                  key={n.id}
                  className={`flex items-start justify-between gap-4 py-4 ${
                    n.read ? "" : "bg-primary/5 -mx-6 px-6"
                  }`}
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs">
                        {TYPE_LABEL[n.type] ?? n.type}
                      </Badge>
                      <span className="font-medium">{n.title}</span>
                      {!n.read && <span className="h-2 w-2 rounded-full bg-primary" />}
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">{n.message}</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {n.created_at ? new Date(n.created_at).toLocaleString() : ""}
                    </p>
                  </div>
                  {!n.read && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="gap-1 shrink-0"
                      onClick={() => markRead.mutate(n.id)}
                    >
                      <Check className="h-4 w-4" />
                      <span className="hidden sm:inline">Mark read</span>
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default Notifications;
