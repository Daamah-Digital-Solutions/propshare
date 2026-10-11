import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Slider } from "@/components/ui/slider";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Download,
  ExternalLink,
  Eye,
  FileText,
  IdCard,
  Lock,
  Pencil,
  ScrollText,
  Shield,
  Trash2,
  Upload,
  UserPlus,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { saveBlob } from "@/lib/certificates";
import { PHOTO_OR_PDF_ACCEPT, photoOrPdfProblem } from "@/lib/uploads";
import {
  ApiError,
  estateApi,
  type BeneficiaryDocument,
  type EstateBeneficiary as ApiBeneficiary,
} from "@/lib/api";

// The holder's beneficiary register (client, 2026-10-07): each person carries a copy of
// their identity document, can be edited at any time, and has a certificate to download —
// what they present, with their own identity document, when they claim.

type BeneficiaryRole = "beneficiary" | "heir" | "authorized" | "legal";
type TransferTrigger = "death" | "inactivity_1y" | "authorized" | "manual";
type CoverageScope = "ownership" | "passive_income" | "rental_returns" | "wallet" | "portfolio";

interface Beneficiary {
  id: string;
  fullName: string;
  relationship: string;
  role: BeneficiaryRole;
  email: string;
  phone: string;
  idType: string;
  idNumber: string;
  allocationPct: number;
  notes: string;
  trigger: TransferTrigger;
  scope: CoverageScope[];
  status: "active" | "pending";
  certificateNo: string;
  version: number;
  documents: BeneficiaryDocument[];
  locked: boolean;
}

type BeneficiaryForm = Omit<
  Beneficiary,
  "id" | "status" | "certificateNo" | "version" | "documents" | "locked"
>;

const EMPTY_FORM: BeneficiaryForm = {
  fullName: "",
  relationship: "",
  role: "beneficiary",
  email: "",
  phone: "",
  idType: "Passport",
  idNumber: "",
  allocationPct: 10,
  notes: "",
  trigger: "death",
  scope: ["ownership"],
};

// The UI's extra fields (role/idType/idNumber/scope/trigger) round-trip via `meta`.
const fromApi = (r: ApiBeneficiary): Beneficiary => {
  const meta = (r.meta ?? {}) as Record<string, unknown>;
  return {
    id: r.id,
    fullName: r.full_name,
    relationship: r.relationship ?? "",
    role: (meta.role as BeneficiaryRole) ?? "beneficiary",
    email: r.email ?? "",
    phone: r.phone ?? "",
    idType: (meta.idType as string) ?? "Passport",
    idNumber: (meta.idNumber as string) ?? "",
    allocationPct: r.allocation_pct,
    notes: r.notes ?? "",
    trigger: (meta.trigger as TransferTrigger) ?? "death",
    scope: (meta.scope as CoverageScope[]) ?? ["ownership"],
    status: r.status === "active" ? "active" : "pending",
    certificateNo: r.certificate_no ?? "",
    version: r.version ?? 1,
    documents: r.documents ?? [],
    locked: Boolean(r.locked),
  };
};

const toPayload = (f: BeneficiaryForm) => ({
  full_name: f.fullName.trim(),
  relationship: f.relationship.trim(),
  email: f.email.trim() || null,
  phone: f.phone.trim() || null,
  allocation_pct: f.allocationPct,
  notes: f.notes.trim() || null,
  meta: {
    role: f.role,
    idType: f.idType,
    idNumber: f.idNumber.trim(),
    scope: f.scope,
    trigger: f.trigger,
  },
});

const roleMeta: Record<BeneficiaryRole, { label: string; tone: string }> = {
  beneficiary: { label: "Beneficiary", tone: "bg-primary/10 text-primary" },
  heir: { label: "Heir", tone: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  authorized: { label: "Authorized Person", tone: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  legal: { label: "Legal Representative", tone: "bg-slate-500/10 text-slate-600 dark:text-slate-400" },
};

const triggerMeta: Record<TransferTrigger, { label: string; icon: typeof Lock }> = {
  death: { label: "On verified death", icon: Shield },
  inactivity_1y: { label: "After 12 months inactivity", icon: Clock },
  authorized: { label: "Authorized transfer event", icon: ScrollText },
  manual: { label: "Manual / on request", icon: Pencil },
};

const scopeMeta: Record<CoverageScope, string> = {
  ownership: "Ownership Rights",
  passive_income: "Passive Income",
  rental_returns: "Rental Returns",
  wallet: "Wallet Balance",
  portfolio: "Full Portfolio",
};

// copies of one person's identity document (the server's own limit)
const MAX_ID_FILES = 4;

const errorText = (e: unknown, fallback: string) =>
  e instanceof ApiError || e instanceof Error ? e.message || fallback : fallback;

export const BeneficiaryRegister = () => {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { data: apiBeneficiaries } = useQuery({
    queryKey: ["estate-beneficiaries"],
    queryFn: estateApi.list,
  });
  const beneficiaries: Beneficiary[] = useMemo(
    () => (apiBeneficiaries ?? []).map(fromApi),
    [apiBeneficiaries],
  );
  const locked = beneficiaries.some((b) => b.locked);
  const totalAllocated = useMemo(
    () => beneficiaries.reduce((s, b) => s + b.allocationPct, 0),
    [beneficiaries],
  );
  const refetch = () => queryClient.invalidateQueries({ queryKey: ["estate-beneficiaries"] });

  // ── add / edit dialog ──────────────────────────────────────────────────────
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<BeneficiaryForm>(EMPTY_FORM);
  const [queued, setQueued] = useState<File[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const editing = beneficiaries.find((b) => b.id === editingId) ?? null;
  // the share the others already hold: this person can take what is left
  const othersAllocated = totalAllocated - (editing?.allocationPct ?? 0);
  const savedDocs = editing?.documents ?? [];

  const openAdd = () => {
    setEditingId(null);
    setForm({ ...EMPTY_FORM, allocationPct: Math.min(10, Math.max(0, 100 - totalAllocated)) });
    setQueued([]);
    setOpen(true);
  };
  const openEdit = (b: Beneficiary) => {
    setEditingId(b.id);
    setForm({
      fullName: b.fullName,
      relationship: b.relationship,
      role: b.role,
      email: b.email,
      phone: b.phone,
      idType: b.idType,
      idNumber: b.idNumber,
      allocationPct: b.allocationPct,
      notes: b.notes,
      trigger: b.trigger,
      scope: b.scope,
    });
    setQueued([]);
    setOpen(true);
  };
  const close = () => {
    setOpen(false);
    setEditingId(null);
    setQueued([]);
  };

  const toggleScope = (s: CoverageScope) =>
    setForm((f) => ({
      ...f,
      scope: f.scope.includes(s) ? f.scope.filter((x) => x !== s) : [...f.scope, s],
    }));

  const chooseFiles = (list: FileList | null) => {
    const chosen = Array.from(list ?? []);
    if (fileInput.current) fileInput.current.value = ""; // the same file can be chosen again
    const room = MAX_ID_FILES - savedDocs.length - queued.length;
    const accepted: File[] = [];
    for (const file of chosen) {
      const problem = photoOrPdfProblem(file);
      if (problem) {
        toast({ title: "File not added", description: problem, variant: "destructive" });
      } else if (accepted.length >= room) {
        toast({
          title: "File not added",
          description: `At most ${MAX_ID_FILES} files per person.`,
          variant: "destructive",
        });
        break;
      } else {
        accepted.push(file);
      }
    }
    if (accepted.length) setQueued((q) => [...q, ...accepted]);
  };

  const save = useMutation({
    mutationFn: async () => {
      const saved = editingId
        ? await estateApi.update(editingId, toPayload(form))
        : await estateApi.add(toPayload(form));
      // the record is saved; its files follow one by one, so one bad file loses nothing else
      const failed: string[] = [];
      for (const file of queued) {
        try {
          await estateApi.addDocument(saved.id, file);
        } catch (e) {
          failed.push(`${file.name}: ${errorText(e, "could not be uploaded")}`);
        }
      }
      return { failed };
    },
    onSuccess: ({ failed }) => {
      const wasEditing = Boolean(editingId);
      close();
      refetch();
      if (failed.length) {
        toast({
          title: "Saved, but a file was not uploaded",
          description: failed.join(" "),
          variant: "destructive",
        });
      } else {
        toast({
          title: wasEditing ? "Beneficiary updated" : "Beneficiary added",
          description: wasEditing
            ? "Download their certificate again: an earlier copy shows the previous version."
            : "You can download their certificate from their card.",
        });
      }
    },
    onError: (e: unknown) =>
      toast({
        title: "Could not save beneficiary",
        description: errorText(e, "Please try again."),
        variant: "destructive",
      }),
  });

  const submit = () => {
    if (!form.fullName.trim() || !form.relationship.trim()) {
      toast({ title: "Missing info", description: "Add full name and relationship.", variant: "destructive" });
      return;
    }
    if (form.email.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) {
      toast({
        title: "Check the email",
        description: "Enter a valid email address, or leave it empty.",
        variant: "destructive",
      });
      return;
    }
    const remaining = 100 - othersAllocated;
    if (form.allocationPct > remaining) {
      toast({
        title: "Allocation exceeds 100%",
        description: `Only ${remaining}% remaining to allocate.`,
        variant: "destructive",
      });
      return;
    }
    save.mutate();
  };

  // ── documents already saved (edit dialog) ──────────────────────────────────
  const removeDocument = useMutation({
    mutationFn: ({ id, docId }: { id: string; docId: string }) => estateApi.removeDocument(id, docId),
    onSuccess: refetch,
    onError: (e: unknown) =>
      toast({ title: "Could not remove the file", description: errorText(e, "Please try again."), variant: "destructive" }),
  });

  const viewDocument = async (id: string, doc: BeneficiaryDocument) => {
    try {
      const url = URL.createObjectURL(await estateApi.fetchDocument(id, doc.id));
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) {
      toast({ title: "Could not open the file", description: errorText(e, "Please try again."), variant: "destructive" });
    }
  };

  // ── certificate ─────────────────────────────────────────────────────────────
  const [issuing, setIssuing] = useState<string | null>(null);
  const downloadCertificate = async (b: Beneficiary) => {
    setIssuing(b.id);
    try {
      saveBlob(await estateApi.certificate(b.id), `beneficiary-certificate-${b.certificateNo || b.id}.pdf`);
    } catch (e) {
      toast({
        title: "The certificate could not be issued",
        description: errorText(e, "Please try again."),
        variant: "destructive",
      });
      // what is missing is on the record: open it so it can be completed
      if (e instanceof ApiError && e.status === 422 && !b.locked) openEdit(b);
    } finally {
      setIssuing(null);
    }
  };

  // ── delete ──────────────────────────────────────────────────────────────────
  const [deleting, setDeleting] = useState<Beneficiary | null>(null);
  const remove = useMutation({
    mutationFn: (id: string) => estateApi.remove(id),
    onSuccess: () => {
      setDeleting(null);
      refetch();
      toast({ title: "Beneficiary removed", description: "Their certificate is no longer valid." });
    },
    onError: (e: unknown) =>
      toast({ title: "Could not remove beneficiary", description: errorText(e, "Please try again."), variant: "destructive" }),
  });

  return (
    <section className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-semibold mb-2">
            <Shield size={12} /> Inheritance & Beneficiary
          </div>
          <h3 className="text-xl md:text-2xl font-bold text-foreground">
            Estate, Heirs & Authorized Representatives
          </h3>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Name the people who should receive your holdings, keep a copy of their identity document with
            their record, and download a certificate for each of them.
          </p>
        </div>
        <Button size="lg" className="gap-2" onClick={openAdd} disabled={locked}>
          <UserPlus size={18} /> Add Beneficiary
        </Button>
      </div>

      {locked && (
        <div
          className="flex items-start gap-2 rounded-lg border border-border bg-muted/50 p-3 text-sm text-muted-foreground"
          data-testid="register-closed"
        >
          <Lock size={16} className="mt-0.5 shrink-0" />
          <span>
            This register is closed: a transfer event was recorded for this account. It can no longer be
            changed. Certificates can still be downloaded.
          </span>
        </div>
      )}

      <Dialog open={open} onOpenChange={(o) => (o ? setOpen(true) : close())}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing ? `Edit ${editing.fullName}` : "Designate Beneficiary / Heir"}</DialogTitle>
            <DialogDescription>
              The person's details as on their identity document. They are printed on the certificate
              you download for them.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="ben-name">Full legal name</Label>
                <Input
                  id="ben-name"
                  value={form.fullName}
                  onChange={(e) => setForm({ ...form, fullName: e.target.value })}
                  placeholder="As shown on ID, in Latin letters"
                />
                <p className="text-[11px] text-muted-foreground">
                  In Latin letters, as in their passport: the certificate is issued in English.
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ben-relationship">Relationship</Label>
                <Input
                  id="ben-relationship"
                  value={form.relationship}
                  onChange={(e) => setForm({ ...form, relationship: e.target.value })}
                  placeholder="Spouse, Son, Daughter…"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Role</Label>
                <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v as BeneficiaryRole })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(Object.keys(roleMeta) as BeneficiaryRole[]).map((r) => (
                      <SelectItem key={r} value={r}>{roleMeta[r].label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ben-email">Email</Label>
                <Input
                  id="ben-email"
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ben-phone">Phone</Label>
                <Input id="ben-phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label>ID type</Label>
                  <Select value={form.idType} onValueChange={(v) => setForm({ ...form, idType: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Passport">Passport</SelectItem>
                      <SelectItem value="National ID">National ID</SelectItem>
                      <SelectItem value="Trade License">Trade License</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="ben-id-number">ID number</Label>
                  <Input
                    id="ben-id-number"
                    value={form.idNumber}
                    onChange={(e) => setForm({ ...form, idNumber: e.target.value })}
                  />
                </div>
              </div>
            </div>

            {/* A copy of the person's identity document, kept with the record */}
            <div className="space-y-2 rounded-lg border border-border p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <Label htmlFor="ben-id-files" className="flex items-center gap-1.5">
                    <IdCard size={15} className="text-primary" /> Copy of their identity document
                  </Label>
                  <p className="text-[11px] text-muted-foreground mt-1">
                    A photo or PDF of the passport or ID card (both sides if it has two), up to 10 MB each.
                    When this person claims, their document is checked against this copy.
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="gap-1.5 shrink-0"
                  disabled={savedDocs.length + queued.length >= MAX_ID_FILES}
                  onClick={() => fileInput.current?.click()}
                >
                  <Upload size={14} /> Choose file
                </Button>
              </div>
              <input
                ref={fileInput}
                id="ben-id-files"
                type="file"
                multiple
                accept={PHOTO_OR_PDF_ACCEPT}
                className="sr-only"
                data-testid="id-file-input"
                onChange={(e) => chooseFiles(e.target.files)}
              />
              {savedDocs.length === 0 && queued.length === 0 ? (
                <p className="text-xs text-muted-foreground">No copy on file yet.</p>
              ) : (
                <ul className="space-y-1.5">
                  {savedDocs.map((d) => (
                    <li key={d.id} className="flex items-center justify-between gap-2 rounded-md bg-muted/50 px-2.5 py-1.5 text-xs">
                      <span className="flex items-center gap-1.5 min-w-0">
                        <FileText size={13} className="shrink-0 text-primary" />
                        <span className="truncate">{d.filename}</span>
                      </span>
                      <span className="flex items-center gap-1 shrink-0">
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2"
                          aria-label={`View ${d.filename}`}
                          onClick={() => editing && viewDocument(editing.id, d)}
                        >
                          <Eye size={13} />
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2 text-destructive hover:text-destructive"
                          aria-label={`Remove ${d.filename}`}
                          disabled={removeDocument.isPending}
                          onClick={() => editing && removeDocument.mutate({ id: editing.id, docId: d.id })}
                        >
                          <Trash2 size={13} />
                        </Button>
                      </span>
                    </li>
                  ))}
                  {queued.map((f, i) => (
                    <li key={`${f.name}-${i}`} className="flex items-center justify-between gap-2 rounded-md border border-dashed border-border px-2.5 py-1.5 text-xs">
                      <span className="flex items-center gap-1.5 min-w-0">
                        <Upload size={13} className="shrink-0 text-muted-foreground" />
                        <span className="truncate">{f.name}</span>
                        <span className="text-muted-foreground shrink-0">· uploaded when you save</span>
                      </span>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2"
                        aria-label={`Do not upload ${f.name}`}
                        onClick={() => setQueued((q) => q.filter((_, j) => j !== i))}
                      >
                        <X size={13} />
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>Allocation percentage</Label>
                <span className="text-sm font-semibold text-primary">{form.allocationPct}%</span>
              </div>
              <Slider
                value={[form.allocationPct]}
                onValueChange={(v) => setForm({ ...form, allocationPct: v[0] })}
                min={0}
                max={Math.max(0, 100 - othersAllocated)}
                step={5}
              />
              <div className="text-[11px] text-muted-foreground">
                {othersAllocated}% allocated to others · {Math.max(0, 100 - othersAllocated)}% available for this person
              </div>
            </div>

            <div className="space-y-2">
              <Label>Coverage scope</Label>
              <div className="grid grid-cols-2 gap-2">
                {(Object.keys(scopeMeta) as CoverageScope[]).map((s) => {
                  const active = form.scope.includes(s);
                  return (
                    <button
                      type="button"
                      key={s}
                      onClick={() => toggleScope(s)}
                      className={cn(
                        "rounded-lg border p-2.5 text-left text-xs font-medium transition-colors",
                        active
                          ? "border-primary bg-primary/5 text-foreground"
                          : "border-border bg-background text-muted-foreground hover:border-primary/40",
                      )}
                    >
                      {scopeMeta[s]}
                    </button>
                  );
                })}
              </div>
              <p className="text-[11px] text-muted-foreground" data-testid="coverage-help">
                Their share of your units is always part of it, and the future returns of those units go
                with them. Tick Wallet Balance or Full Portfolio to add the same share of your wallet
                balance on the day of the transfer.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label>Transfer condition</Label>
              <Select value={form.trigger} onValueChange={(v) => setForm({ ...form, trigger: v as TransferTrigger })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(Object.keys(triggerMeta) as TransferTrigger[]).map((t) => (
                    <SelectItem key={t} value={t}>{triggerMeta[t].label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground" data-testid="condition-help">
                This records your wish. Nothing is transferred by itself: a transfer is made only through
                a claim that this person sends and our team reviews.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="ben-notes">Notes / instructions</Label>
              <Textarea
                id="ben-notes"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                placeholder="Specific wishes, conditions or instructions for this beneficiary…"
                rows={3}
              />
            </div>

            <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-400">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span>
                Every change is recorded with its date and makes a new version of this person's certificate.
                A designation records your wishes; it is not a will. A transfer is made only after Capimax
                PropShare verifies a claim, and is subject to applicable law.
              </span>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={close}>Cancel</Button>
            <Button onClick={submit} disabled={save.isPending}>
              {save.isPending ? "Saving…" : editing ? "Save Changes" : "Save Beneficiary"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleting !== null} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove {deleting?.fullName}?</AlertDialogTitle>
            <AlertDialogDescription>
              Their record and the copies of their identity document are deleted, and the certificate you
              downloaded for them is no longer valid. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={remove.isPending}
              onClick={(e) => {
                e.preventDefault(); // stay open until the server answers
                if (deleting) remove.mutate(deleting.id);
              }}
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Allocation overview */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-center justify-between mb-2">
            <div>
              <div className="text-xs text-muted-foreground">Total estate allocation</div>
              <div className="text-2xl font-bold text-foreground">
                {totalAllocated}<span className="text-sm font-normal text-muted-foreground">% of 100%</span>
              </div>
            </div>
            <Badge variant={totalAllocated === 100 ? "default" : "secondary"} className="gap-1">
              {totalAllocated === 100 ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
              {totalAllocated === 100 ? "Fully allocated" : `${100 - totalAllocated}% unallocated`}
            </Badge>
          </div>
          <Progress value={totalAllocated} />
        </CardContent>
      </Card>

      {/* Beneficiary list */}
      <div className="grid md:grid-cols-2 gap-4">
        {beneficiaries.map((b) => {
          const TIcon = triggerMeta[b.trigger]?.icon ?? Shield;
          return (
            <Card key={b.id} className="relative overflow-hidden" data-testid={`beneficiary-${b.id}`}>
              <div className="absolute top-0 right-0 w-32 h-32 rounded-full bg-primary/5 blur-2xl pointer-events-none" />
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-full bg-gradient-to-br from-primary to-primary/60 text-primary-foreground flex items-center justify-center font-semibold">
                      {b.fullName.split(" ").map((n) => n[0]).slice(0, 2).join("")}
                    </div>
                    <div>
                      <CardTitle className="text-base">{b.fullName}</CardTitle>
                      <CardDescription className="text-xs">{b.relationship}</CardDescription>
                    </div>
                  </div>
                  <Badge className={cn("border-0", (roleMeta[b.role] ?? roleMeta.beneficiary).tone)}>
                    {(roleMeta[b.role] ?? roleMeta.beneficiary).label}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div>
                  <div className="flex justify-between text-xs text-muted-foreground mb-1">
                    <span>Allocation</span>
                    <span className="font-semibold text-foreground">{b.allocationPct}%</span>
                  </div>
                  <Progress value={b.allocationPct} />
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {b.scope.map((s) => (
                    <Badge key={s} variant="secondary" className="text-[10px]">
                      {scopeMeta[s] ?? s}
                    </Badge>
                  ))}
                </div>

                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <TIcon size={13} className="text-primary" />
                  <span>{triggerMeta[b.trigger]?.label ?? b.trigger}</span>
                </div>

                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <IdCard size={13} className={b.documents.length ? "text-primary" : ""} />
                    {b.documents.length
                      ? `ID copy on file (${b.documents.length})`
                      : "No ID copy on file"}
                  </span>
                  {b.certificateNo && (
                    <span className="flex items-center gap-1.5">
                      <ScrollText size={13} className="text-primary" />
                      {b.certificateNo} · v{b.version}
                    </span>
                  )}
                </div>

                {b.notes && (
                  <p className="text-xs text-muted-foreground italic border-l-2 border-border pl-2">
                    "{b.notes}"
                  </p>
                )}

                <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-border">
                  <Badge variant={b.status === "active" ? "default" : "secondary"} className="text-[10px]">
                    {b.status === "active" ? "Has a verified account" : "No verified account yet"}
                  </Badge>
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1.5"
                      disabled={issuing === b.id}
                      onClick={() => downloadCertificate(b)}
                    >
                      <Download size={14} /> {issuing === b.id ? "Preparing…" : "Certificate"}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Edit ${b.fullName}`}
                      disabled={b.locked}
                      onClick={() => openEdit(b)}
                    >
                      <Pencil size={14} />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive hover:text-destructive"
                      aria-label={`Remove ${b.fullName}`}
                      disabled={b.locked}
                      onClick={() => setDeleting(b)}
                    >
                      <Trash2 size={14} />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* What the certificate is for */}
      <Card className="bg-gradient-to-br from-primary/5 to-accent/10 border-primary/20">
        <CardContent className="p-5 flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="w-10 h-10 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0">
            <ScrollText size={18} />
          </div>
          <div className="flex-1">
            <div className="text-sm font-semibold">How a claim is made</div>
            <div className="text-xs text-muted-foreground mt-0.5">
              Give each person their certificate. When the time comes, they present it with their own
              identity document on the claim page; after our team verifies it, their share is transferred
              to their own account. Nobody is given access to yours.
            </div>
          </div>
          <Button asChild variant="outline" size="sm" className="gap-1.5 shrink-0">
            <Link to="/estate-claim" target="_blank" rel="noopener">
              The claim page <ExternalLink size={13} />
            </Link>
          </Button>
        </CardContent>
      </Card>
    </section>
  );
};

export default BeneficiaryRegister;
