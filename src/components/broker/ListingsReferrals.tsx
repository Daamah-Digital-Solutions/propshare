/**
 * The broker's "Listings & Referrals" (client feedback #2): one table of everything the broker
 * brought — clients who joined through their link, clients they invited, and properties /
 * projects they introduced for listing — with "Add client", "Add property" and "Add project".
 *
 * Referred clients stay masked (privacy); an invited client shows what the broker typed.
 * Nothing here moves money: commissions still come only from referred clients.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Copy, HardHat, Loader2, UserPlus, X } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, brokerApi, type BrokerLead } from "@/lib/api";

const STATUS: Record<string, { label: string; className: string }> = {
  linked: { label: "Linked to you", className: "bg-success text-success-foreground" },
  invited: { label: "Invited", className: "bg-warning text-warning-foreground" },
  joined: { label: "Joined through your link", className: "bg-success text-success-foreground" },
  cancelled: { label: "Cancelled", className: "bg-muted text-muted-foreground" },
  new: { label: "Received — under review", className: "bg-warning text-warning-foreground" },
  contacted: { label: "Owner contacted", className: "bg-accent text-accent-foreground" },
  listed: { label: "Listed", className: "bg-success text-success-foreground" },
  declined: { label: "Not listed", className: "bg-destructive text-destructive-foreground" },
  withdrawn: { label: "Withdrawn", className: "bg-muted text-muted-foreground" },
};

const TYPE_LABEL: Record<string, string> = { client: "Client", property: "Property", project: "Project" };

interface Row {
  key: string;
  type: string;
  name: string;
  contact: string;
  status: string;
  date: string | null;
  detail: string;
  lead?: BrokerLead;
}

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : "—");

export function ListingsReferrals({ shareLink }: { shareLink?: string }) {
  const queryClient = useQueryClient();
  const { data: referrals } = useQuery({ queryKey: ["broker", "referrals"], queryFn: brokerApi.referrals });
  const { data: leads } = useQuery({ queryKey: ["broker", "leads"], queryFn: brokerApi.leads });
  const [dialog, setDialog] = useState<null | "client" | "property" | "project">(null);

  const cancel = useMutation({
    mutationFn: (id: string) => brokerApi.cancelLead(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["broker", "leads"] }),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not withdraw it."),
  });

  const rows: Row[] = [
    ...(referrals?.items ?? []).map((r) => ({
      key: `ref-${r.referral_id}`,
      type: "client",
      name: r.client_masked,
      contact: "—",
      status: "linked",
      date: r.created_at,
      detail: `$${Number(r.commission_to_date).toLocaleString()} commission to date`,
    })),
    // a joined invitation is already listed above as a linked client
    ...(leads?.items ?? [])
      .filter((l) => !(l.kind === "client" && l.status === "joined"))
      .map((l) => ({
        key: `lead-${l.id}`,
        type: l.kind,
        name: l.name,
        contact:
          l.kind === "client"
            ? [l.email, l.phone].filter(Boolean).join(" · ") || "—"
            : [l.details.owner_name, l.email, l.phone].filter(Boolean).join(" · ") || "—",
        status: l.status,
        date: l.created_at,
        detail:
          l.admin_note ||
          (l.kind === "client"
            ? "Invitation sent with your link"
            : [l.details.location, l.documents.length ? `${l.documents.length} document(s)` : ""]
                .filter(Boolean)
                .join(" · ")),
        lead: l,
      })),
  ].sort((a, b) => (b.date || "").localeCompare(a.date || ""));

  const copyLink = async () => {
    if (!shareLink) return;
    await navigator.clipboard.writeText(shareLink);
    toast.success("Referral link copied");
  };

  return (
    <div className="space-y-6">
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 space-y-0">
          <div>
            <CardTitle>Listings &amp; Referrals</CardTitle>
            <CardDescription>
              Everyone and everything you brought to Capimax PropShare, and where each one stands.
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" className="gap-2" onClick={() => setDialog("client")}>
              <UserPlus className="h-4 w-4" />
              Add client
            </Button>
            <Button size="sm" variant="outline" className="gap-2" onClick={() => setDialog("property")}>
              <Building2 className="h-4 w-4" />
              Add property
            </Button>
            <Button size="sm" variant="outline" className="gap-2" onClick={() => setDialog("project")}>
              <HardHat className="h-4 w-4" />
              Add project
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {shareLink && (
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 rounded-lg bg-muted/40 p-3">
              <code className="flex-1 text-xs break-all">{shareLink}</code>
              <Button size="sm" variant="outline" className="gap-2" onClick={copyLink}>
                <Copy className="h-4 w-4" />
                Copy your link
              </Button>
            </div>
          )}
          {rows.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              Nothing yet. Add a client or introduce a property or project — or share your link.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table data-testid="listings-referrals-table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Type</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Contact</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead>Details</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((r) => {
                    const st = STATUS[r.status] ?? { label: r.status, className: "bg-muted" };
                    const canWithdraw =
                      r.lead && ((r.lead.kind === "client" && r.lead.status === "invited") || r.lead.status === "new");
                    return (
                      <TableRow key={r.key}>
                        <TableCell>{TYPE_LABEL[r.type] ?? r.type}</TableCell>
                        <TableCell className="font-medium">{r.name}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">{r.contact}</TableCell>
                        <TableCell>
                          <Badge className={st.className}>{st.label}</Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground whitespace-nowrap">{day(r.date)}</TableCell>
                        <TableCell className="text-sm text-muted-foreground max-w-[280px]">{r.detail}</TableCell>
                        <TableCell>
                          {canWithdraw && r.lead && (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 px-2 text-xs text-destructive hover:text-destructive"
                              onClick={() => cancel.mutate(r.lead!.id)}
                            >
                              <X className="h-3 w-3 mr-1" />
                              Withdraw
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <AddClientDialog open={dialog === "client"} onClose={() => setDialog(null)} />
      <AddListingDialog
        kind={dialog === "project" ? "project" : "property"}
        open={dialog === "property" || dialog === "project"}
        onClose={() => setDialog(null)}
      />
    </div>
  );
}

function AddClientDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ name: "", email: "", phone: "", notes: "" });
  const invite = useMutation({
    mutationFn: () =>
      brokerApi.inviteClient({
        name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || undefined,
        notes: form.notes.trim() || undefined,
      }),
    onSuccess: () => {
      toast.success("Invitation sent", {
        description: "They get your link by email and join your clients when they sign up through it.",
      });
      queryClient.invalidateQueries({ queryKey: ["broker", "leads"] });
      setForm({ name: "", email: "", phone: "", notes: "" });
      onClose();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not send the invitation."),
  });
  const valid = form.name.trim().length > 0 && /.+@.+\..+/.test(form.email.trim());
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add a client</DialogTitle>
          <DialogDescription>
            We email them your referral link. They join your clients when they create their account
            through it.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="client-name">Full name *</Label>
            <Input id="client-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="client-email">Email *</Label>
            <Input
              id="client-email"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="client-phone">Phone</Label>
            <Input id="client-phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="client-notes">Notes (only you see them)</Label>
            <Textarea id="client-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => invite.mutate()} disabled={!valid || invite.isPending}>
            {invite.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Send invitation
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const EMPTY_LISTING = {
  title: "",
  location: "",
  property_type: "",
  estimated_value: "",
  expected_completion: "",
  owner_name: "",
  owner_email: "",
  owner_phone: "",
  notes: "",
};

function AddListingDialog({
  kind,
  open,
  onClose,
}: {
  kind: "property" | "project";
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_LISTING);
  const [files, setFiles] = useState<File[]>([]);
  const set = (k: keyof typeof EMPTY_LISTING) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value });
  const submit = useMutation({
    mutationFn: () =>
      brokerApi.introduceListing(
        kind,
        Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim()]).filter(([, v]) => v)),
        files,
      ),
    onSuccess: () => {
      toast.success(kind === "project" ? "Project sent" : "Property sent", {
        description: "Our team reviews it; its status updates in your table.",
      });
      queryClient.invalidateQueries({ queryKey: ["broker", "leads"] });
      setForm(EMPTY_LISTING);
      setFiles([]);
      onClose();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not send it."),
  });
  const valid = form.title.trim() && form.location.trim() && form.owner_name.trim();
  const noun = kind === "project" ? "project" : "property";
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{kind === "project" ? "Add a project (off-plan)" : "Add a property"}</DialogTitle>
          <DialogDescription>
            Introduce the {noun} and its owner or developer. Our team reviews it and contacts them;
            nothing is published until it is approved.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="space-y-1 md:col-span-2">
            <Label htmlFor="lead-title">{kind === "project" ? "Project name *" : "Property name *"}</Label>
            <Input id="lead-title" value={form.title} onChange={set("title")} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="lead-location">Location *</Label>
            <Input id="lead-location" value={form.location} onChange={set("location")} placeholder="e.g. Dubai Marina, UAE" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="lead-type">Type</Label>
            <Input id="lead-type" value={form.property_type} onChange={set("property_type")} placeholder="e.g. apartment, villa, office" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="lead-value">Estimated value (USD)</Label>
            <Input id="lead-value" value={form.estimated_value} onChange={set("estimated_value")} />
          </div>
          {kind === "project" && (
            <div className="space-y-1">
              <Label htmlFor="lead-completion">Expected completion</Label>
              <Input id="lead-completion" type="date" value={form.expected_completion} onChange={set("expected_completion")} />
            </div>
          )}
          <div className="space-y-1">
            <Label htmlFor="lead-owner">{kind === "project" ? "Developer name *" : "Owner name *"}</Label>
            <Input id="lead-owner" value={form.owner_name} onChange={set("owner_name")} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="lead-owner-email">Their email</Label>
            <Input id="lead-owner-email" type="email" value={form.owner_email} onChange={set("owner_email")} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="lead-owner-phone">Their phone</Label>
            <Input id="lead-owner-phone" value={form.owner_phone} onChange={set("owner_phone")} />
          </div>
          <div className="space-y-1 md:col-span-2">
            <Label htmlFor="lead-notes">Notes for our team</Label>
            <Textarea id="lead-notes" value={form.notes} onChange={set("notes")} />
          </div>
          <div className="space-y-1 md:col-span-2">
            <Label htmlFor="lead-files">Documents (up to 6: title deed, brochure, valuation…)</Label>
            <Input
              id="lead-files"
              type="file"
              multiple
              onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, 6))}
            />
            {files.length > 0 && (
              <p className="text-xs text-muted-foreground">{files.map((f) => f.name).join(", ")}</p>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => submit.mutate()} disabled={!valid || submit.isPending}>
            {submit.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Send to our team
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
