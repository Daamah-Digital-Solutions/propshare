import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowDown, ArrowUp, Loader2, Megaphone, Pencil, Plus, Target, Trash2 } from "lucide-react";
import {
  ownerMilestonesApi,
  ownerUpdatesApi,
  type MilestonePayload,
  type PropertyMilestone,
} from "@/lib/api";

// 15c bridge — pre-fill an investor update from a milestone (developer reviews + sends; never auto).
const milestoneToUpdate = (m: PropertyMilestone): { subject: string; body: string } => {
  const headline =
    m.status === "completed"
      ? `We've completed "${m.title}".`
      : m.status === "in_progress"
        ? `"${m.title}" is now underway${m.progress_pct != null ? ` (${m.progress_pct}% complete)` : ""}.`
        : `Upcoming milestone: "${m.title}".`;
  return {
    subject: `Project update: ${m.title}`,
    body: [headline, m.description ?? ""].filter(Boolean).join(" "),
  };
};

type ProjectRef = { id: string; name: string };

const STATUS_LABEL: Record<PropertyMilestone["status"], string> = {
  planned: "Planned",
  in_progress: "In Progress",
  completed: "Completed",
};
const STATUS_TONE: Record<PropertyMilestone["status"], string> = {
  planned: "bg-muted text-muted-foreground",
  in_progress: "bg-primary text-primary-foreground",
  completed: "bg-success text-success-foreground",
};

type FormState = {
  title: string;
  description: string;
  status: PropertyMilestone["status"];
  progress_pct: string;
  target_date: string;
  value_index: string;
};

const EMPTY_FORM: FormState = {
  title: "",
  description: "",
  status: "planned",
  progress_pct: "",
  target_date: "",
  value_index: "",
};

const toForm = (m: PropertyMilestone): FormState => ({
  title: m.title,
  description: m.description ?? "",
  status: m.status,
  progress_pct: m.progress_pct != null ? String(m.progress_pct) : "",
  target_date: m.target_date ?? "",
  value_index: m.value_index != null ? String(m.value_index) : "",
});

const toPayload = (f: FormState): MilestonePayload => ({
  title: f.title.trim(),
  description: f.description.trim() || null,
  status: f.status,
  progress_pct: f.progress_pct === "" ? null : Number(f.progress_pct),
  target_date: f.target_date || null,
  value_index: f.value_index === "" ? null : Number(f.value_index),
});

export const MilestonesManager = ({ projects }: { projects: ProjectRef[] }) => {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<string>(projects[0]?.id ?? "");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<PropertyMilestone | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  // 15c bridge dialog (manual notify investors about a milestone)
  const [notifyOpen, setNotifyOpen] = useState(false);
  const [notifyForm, setNotifyForm] = useState({ subject: "", body: "" });

  // Keep a valid selection as the project list resolves.
  useEffect(() => {
    if (!selectedId && projects[0]) setSelectedId(projects[0].id);
  }, [projects, selectedId]);

  const { data: milestones, isLoading } = useQuery({
    queryKey: ["owner-milestones", selectedId],
    queryFn: () => ownerMilestonesApi.list(selectedId),
    enabled: !!selectedId,
  });

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["owner-milestones", selectedId] });

  const saveMutation = useMutation({
    mutationFn: (f: FormState) =>
      editing
        ? ownerMilestonesApi.update(selectedId, editing.id, toPayload(f))
        : ownerMilestonesApi.create(selectedId, toPayload(f)),
    onSuccess: () => {
      toast.success(editing ? "Milestone updated" : "Milestone added");
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) =>
      toast.error(e instanceof Error ? e.message : "Could not save the milestone"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => ownerMilestonesApi.remove(selectedId, id),
    onSuccess: () => {
      toast.success("Milestone removed");
      invalidate();
    },
    onError: (e: unknown) =>
      toast.error(e instanceof Error ? e.message : "Could not remove the milestone"),
  });

  const reorderMutation = useMutation({
    mutationFn: (orderedIds: string[]) => ownerMilestonesApi.reorder(selectedId, orderedIds),
    onSuccess: () => invalidate(),
    onError: (e: unknown) =>
      toast.error(e instanceof Error ? e.message : "Could not reorder"),
  });

  const notifyMutation = useMutation({
    mutationFn: () =>
      ownerUpdatesApi.send(selectedId, {
        subject: notifyForm.subject.trim(),
        body: notifyForm.body.trim(),
      }),
    onSuccess: (u) => {
      toast.success(
        `Update sent to ${u.recipient_count} investor${u.recipient_count === 1 ? "" : "s"}`,
      );
      setNotifyOpen(false);
    },
    onError: (e: unknown) =>
      toast.error(e instanceof Error ? e.message : "Could not send the update"),
  });

  const openNotify = (m: PropertyMilestone) => {
    setNotifyForm(milestoneToUpdate(m));
    setNotifyOpen(true);
  };

  const openAdd = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  };
  const openEdit = (m: PropertyMilestone) => {
    setEditing(m);
    setForm(toForm(m));
    setDialogOpen(true);
  };

  const move = (index: number, dir: -1 | 1) => {
    const rows = [...(milestones ?? [])];
    const target = index + dir;
    if (target < 0 || target >= rows.length) return;
    [rows[index], rows[target]] = [rows[target], rows[index]];
    reorderMutation.mutate(rows.map((m) => m.id));
  };

  if (projects.length === 0) {
    return (
      <Card className="bg-card border-border">
        <CardContent className="py-16 text-center text-muted-foreground">
          Create a project first — milestones are tracked per property.
        </CardContent>
      </Card>
    );
  }

  const rows = milestones ?? [];
  const canSubmit = form.title.trim().length > 0 && !saveMutation.isPending;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="w-full sm:w-72">
          <Label className="text-sm text-muted-foreground">Project</Label>
          <Select value={selectedId} onValueChange={setSelectedId}>
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
        </div>
        <Button className="gap-2" onClick={openAdd}>
          <Plus className="h-4 w-4" />
          Add Milestone Update
        </Button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : rows.length === 0 ? (
        <Card className="bg-card border-border border-dashed">
          <CardContent className="py-12 flex flex-col items-center text-center gap-3">
            <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
              <Target className="h-6 w-6 text-muted-foreground" />
            </div>
            <h3 className="text-lg font-semibold">No milestones yet</h3>
            <p className="text-sm text-muted-foreground max-w-md">
              Add construction or project milestones — investors see them on the property page.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {rows.map((m, i) => (
            <Card key={m.id} className="bg-card border-border">
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className="font-semibold">{m.title}</h4>
                      <Badge className={STATUS_TONE[m.status]}>{STATUS_LABEL[m.status]}</Badge>
                      {m.value_index != null && (
                        <span className="text-xs text-muted-foreground">NAV {m.value_index}</span>
                      )}
                    </div>
                    {m.description && (
                      <p className="text-sm text-muted-foreground mt-1">{m.description}</p>
                    )}
                    <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                      {m.target_date && <span>Target: {m.target_date}</span>}
                      {m.progress_pct != null && <span>{m.progress_pct}% complete</span>}
                    </div>
                    {m.progress_pct != null && (
                      <Progress value={m.progress_pct} className="h-1.5 mt-2 max-w-xs" />
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Move up"
                      disabled={i === 0 || reorderMutation.isPending}
                      onClick={() => move(i, -1)}
                    >
                      <ArrowUp className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Move down"
                      disabled={i === rows.length - 1 || reorderMutation.isPending}
                      onClick={() => move(i, 1)}
                    >
                      <ArrowDown className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Notify investors"
                      title="Notify investors about this milestone"
                      onClick={() => openNotify(m)}
                    >
                      <Megaphone className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Edit milestone"
                      onClick={() => openEdit(m)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Delete milestone"
                      disabled={deleteMutation.isPending}
                      onClick={() => deleteMutation.mutate(m.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? "Edit milestone" : "Add milestone update"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="ms-title">Title</Label>
              <Input
                id="ms-title"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="e.g. Foundation complete"
              />
            </div>
            <div>
              <Label htmlFor="ms-desc">Description</Label>
              <Textarea
                id="ms-desc"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Optional details for investors"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Status</Label>
                <Select
                  value={form.status}
                  onValueChange={(v) =>
                    setForm({ ...form, status: v as PropertyMilestone["status"] })
                  }
                >
                  <SelectTrigger aria-label="Status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="planned">Planned</SelectItem>
                    <SelectItem value="in_progress">In Progress</SelectItem>
                    <SelectItem value="completed">Completed</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="ms-progress">Progress %</Label>
                <Input
                  id="ms-progress"
                  type="number"
                  min={0}
                  max={100}
                  value={form.progress_pct}
                  onChange={(e) => setForm({ ...form, progress_pct: e.target.value })}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="ms-date">Target date</Label>
                <Input
                  id="ms-date"
                  type="date"
                  value={form.target_date}
                  onChange={(e) => setForm({ ...form, target_date: e.target.value })}
                />
              </div>
              <div>
                <Label htmlFor="ms-nav">NAV index (advanced)</Label>
                <Input
                  id="ms-nav"
                  type="number"
                  min={0}
                  value={form.value_index}
                  onChange={(e) => setForm({ ...form, value_index: e.target.value })}
                  placeholder="100 = entry"
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button disabled={!canSubmit} onClick={() => saveMutation.mutate(form)}>
              {saveMutation.isPending ? "Saving…" : editing ? "Save changes" : "Add milestone"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 15c bridge — manual "notify investors about this milestone" (pre-filled, never auto). */}
      <Dialog open={notifyOpen} onOpenChange={setNotifyOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Notify investors</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-xs text-muted-foreground">
              Sends to everyone who currently holds units in this property. Review before sending.
            </p>
            <div>
              <Label htmlFor="ms-notify-subject">Subject</Label>
              <Input
                id="ms-notify-subject"
                value={notifyForm.subject}
                onChange={(e) => setNotifyForm({ ...notifyForm, subject: e.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="ms-notify-body">Message</Label>
              <Textarea
                id="ms-notify-body"
                rows={5}
                value={notifyForm.body}
                onChange={(e) => setNotifyForm({ ...notifyForm, body: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNotifyOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={
                !notifyForm.subject.trim() ||
                !notifyForm.body.trim() ||
                notifyMutation.isPending
              }
              onClick={() => notifyMutation.mutate()}
            >
              {notifyMutation.isPending ? "Sending…" : "Send update"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MilestonesManager;
