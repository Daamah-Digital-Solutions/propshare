import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowDownLeft, ArrowUpRight, ArrowRightLeft, Coins, UserPlus, Users } from "lucide-react";
import { familyApi, type FamilyActivityItem } from "@/lib/api";
import { activityNote, activitySentence, shortDay as day } from "@/lib/familyActivity";

// What the family feature did with this member, on either side (client, 2026-10-07: "it
// does the whole job but leaves no trace, and the receiver does not see that it came to
// him"). Read back from the server's own records, so it is here whether or not a
// notification was read. A member who was only ever on the receiving side has no group of
// their own: this is the only place on the page they see what reached them.

const STATUS: Record<string, { label: string; tone: string }> = {
  completed: { label: "Completed", tone: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30" },
  pending: { label: "Pending", tone: "bg-amber-500/10 text-amber-600 border-amber-500/30" },
  cancelled: { label: "Cancelled", tone: "bg-muted text-muted-foreground" },
  recorded: { label: "Held", tone: "bg-amber-500/10 text-amber-600 border-amber-500/30" },
  verified: { label: "Verified", tone: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30" },
};

const Icon = ({ item }: { item: FamilyActivityItem }) => {
  if (item.kind === "member") return <UserPlus className="h-5 w-5 text-primary" />;
  if (item.kind === "returns") return <Coins className="h-5 w-5 text-emerald-600" />;
  if (item.direction === "in") return <ArrowDownLeft className="h-5 w-5 text-emerald-600" />;
  if (item.direction === "out") return <ArrowUpRight className="h-5 w-5 text-primary" />;
  return <ArrowRightLeft className="h-5 w-5 text-primary" />;
};

export const FamilyActivity = ({ hideWhenEmpty = false }: { hideWhenEmpty?: boolean }) => {
  const { data, isLoading } = useQuery({ queryKey: ["family", "activity"], queryFn: () => familyApi.activity() });
  const items = data?.items ?? [];
  const memberships = data?.memberships ?? [];
  if (hideWhenEmpty && items.length === 0 && memberships.length === 0) return null;

  return (
    <div className="space-y-4" data-testid="family-activity">
      {memberships.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base flex items-center gap-2"><Users className="h-4 w-4 text-primary" />Family groups you belong to</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {memberships.map((m, i) => (
              <div key={`${m.owner_name}-${i}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted/50 p-3 text-sm">
                <div>
                  <p className="font-medium">{m.owner_name}'s family group</p>
                  <p className="text-xs text-muted-foreground">
                    You are their {m.relationship}{m.since ? ` · since ${day(m.since)}` : ""}
                  </p>
                </div>
                {m.is_verified ? (
                  <Badge variant="outline" className={STATUS.verified.tone}>Verified</Badge>
                ) : (
                  <Link to="/kyc" className="text-xs text-primary underline">
                    Verify your identity to receive what they allocate to you
                  </Link>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Family Activity</CardTitle>
          <p className="text-sm text-muted-foreground">
            Members added, and units and returns transferred or allocated: by you, and to you.
          </p>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="py-8 text-center text-sm text-muted-foreground">Loading…</div>
          ) : items.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">No family activity yet.</div>
          ) : (
            <div className="space-y-3">
              {items.map((i) => {
                const status = STATUS[i.status];
                const note = activityNote(i);
                return (
                  <div key={i.id} className="flex items-center justify-between gap-3 py-3 border-b border-border last:border-0" data-testid="activity-row">
                    <div className="flex items-center gap-4 min-w-0">
                      <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0"><Icon item={i} /></div>
                      <div className="min-w-0">
                        <p className="font-medium text-sm">{activitySentence(i)}</p>
                        <p className="text-xs text-muted-foreground">
                          {day(i.at)}{note ? ` · ${note}` : ""}
                        </p>
                      </div>
                    </div>
                    {status && <Badge variant="outline" className={status.tone}>{status.label}</Badge>}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default FamilyActivity;
