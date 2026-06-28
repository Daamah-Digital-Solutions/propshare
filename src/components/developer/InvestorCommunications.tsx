import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Eye, FileText, Loader2, Mail, Users } from "lucide-react";
import { ownerUpdatesApi, type DeveloperUpdate } from "@/lib/api";

type ProjectRef = { id: string; name: string };

const fmtDate = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

export const InvestorCommunications = ({ projects }: { projects: ProjectRef[] }) => {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [propertyId, setPropertyId] = useState<string>(projects[0]?.id ?? "");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");

  const { data: updates, isLoading } = useQuery({
    queryKey: ["owner-updates"],
    queryFn: () => ownerUpdatesApi.list(),
  });

  const nameOf = (pid: string) => projects.find((p) => p.id === pid)?.name ?? "Property";

  const sendMutation = useMutation({
    mutationFn: () => ownerUpdatesApi.send(propertyId, { subject: subject.trim(), body: body.trim() }),
    onSuccess: (u) => {
      toast.success(`Update sent to ${u.recipient_count} investor${u.recipient_count === 1 ? "" : "s"}`);
      setOpen(false);
      setSubject("");
      setBody("");
      qc.invalidateQueries({ queryKey: ["owner-updates"] });
    },
    onError: (e: unknown) =>
      toast.error(e instanceof Error ? e.message : "Could not send the update"),
  });

  const canSend =
    !!propertyId && subject.trim().length > 0 && body.trim().length > 0 && !sendMutation.isPending;
  const rows = updates ?? [];

  return (
    <Card className="bg-card border-border">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Investor Communications</CardTitle>
        <Button
          className="gap-2"
          disabled={projects.length === 0}
          onClick={() => setOpen(true)}
        >
          <FileText className="h-4 w-4" />
          Send Update
        </Button>
      </CardHeader>
      <CardContent>
        {projects.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Create a project first — updates are sent to a property's investors.
          </p>
        ) : isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : rows.length === 0 ? (
          <div className="py-8 flex flex-col items-center text-center gap-2">
            <Mail className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium text-foreground">No updates sent yet</p>
            <p className="text-xs text-muted-foreground max-w-md">
              Send your investors a project update — they receive it in their notifications
              (and by email, if they've opted in).
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {rows.map((u: DeveloperUpdate) => (
              <div key={u.id} className="p-4 rounded-lg bg-muted/30">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <h4 className="font-semibold">{u.subject}</h4>
                    <p className="text-xs text-muted-foreground">
                      {nameOf(u.property_id)} · {fmtDate(u.created_at)}
                    </p>
                    <p className="text-sm text-muted-foreground mt-2 line-clamp-2">{u.body}</p>
                  </div>
                  <div className="flex items-center gap-4 text-sm whitespace-nowrap">
                    <span className="flex items-center gap-1 text-muted-foreground" title="Recipients">
                      <Users className="h-4 w-4" />
                      {u.recipient_count}
                    </span>
                    <span className="flex items-center gap-1 text-muted-foreground" title="In-app reads">
                      <Eye className="h-4 w-4" />
                      {u.read_count}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Send investor update</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Project</Label>
              <Select value={propertyId} onValueChange={setPropertyId}>
                <SelectTrigger aria-label="Select project">
                  <SelectValue placeholder="Select a project" />
                </SelectTrigger>
                <SelectContent>
                  {projects.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">
                Sends to everyone who currently holds units in this property.
              </p>
            </div>
            <div>
              <Label htmlFor="uc-subject">Subject</Label>
              <Input
                id="uc-subject"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="e.g. Q2 construction progress"
              />
            </div>
            <div>
              <Label htmlFor="uc-body">Message</Label>
              <Textarea
                id="uc-body"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Share an update with your investors…"
                rows={5}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button disabled={!canSend} onClick={() => sendMutation.mutate()}>
              {sendMutation.isPending ? "Sending…" : "Send update"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
};

export default InvestorCommunications;
