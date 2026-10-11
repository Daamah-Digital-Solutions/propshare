import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/contexts/AuthContext";
import { ConfirmEmailButton } from "@/components/account/ConfirmEmailButton";
import {
  ApiError,
  estateClaimsApi,
  type EstateClaim as Claim,
  type EstateClaimDocumentKind,
  type EstateClaimReason,
} from "@/lib/api";
import {
  CLAIM_MAX_TOTAL_BYTES,
  PHOTO_OR_PDF_ACCEPT as ACCEPT,
  photoOrPdfProblem as fileProblem,
} from "@/lib/uploads";
import {
  CheckCircle2,
  FileCheck2,
  FileText,
  IdCard,
  Lock,
  MailCheck,
  ScrollText,
  Send,
  ShieldCheck,
  Upload,
  UserCheck,
  X,
} from "lucide-react";

// The public claim page (client, 2026-10-07): the person an account holder named reports
// the holder's death and claims, with the beneficiary certificate and their own identity
// document. Our team reviews it; on approval the assets move to the claimant's OWN verified
// account. Nobody is ever given the holder's account.

const REASONS: { value: EstateClaimReason; label: string }[] = [
  { value: "death", label: "Death of the account holder" },
  { value: "incapacity", label: "The account holder can no longer manage the account" },
  { value: "other", label: "Another reason" },
];

const TOO_LARGE_TOGETHER =
  "The files together are larger than 25 MB. Use smaller photos or fewer files: a document can be added to the claim later from your account.";

const STATUS_TONE: Record<string, string> = {
  submitted: "bg-amber-500/10 text-amber-700 border-amber-500/30",
  in_review: "bg-blue-500/10 text-blue-700 border-blue-500/30",
  needs_info: "bg-amber-500/10 text-amber-700 border-amber-500/30",
  approved: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30",
  rejected: "bg-destructive/10 text-destructive border-destructive/30",
};

const STEPS = [
  {
    icon: Send,
    title: "Send the claim",
    text: "Your details, the account holder's name, the reason, the beneficiary certificate and a copy of your own identity document.",
  },
  {
    icon: FileCheck2,
    title: "We verify it",
    text: "Our team checks the certificate and your identity against the holder's register, and writes to you if anything else is needed.",
  },
  {
    icon: UserCheck,
    title: "Your own account",
    text: "Create your own Capimax PropShare account and complete identity verification in it.",
  },
  {
    icon: ShieldCheck,
    title: "The transfer",
    text: "After approval, the assets allocated to you are transferred to your own account.",
  },
];

const today = () => new Date().toISOString().slice(0, 10);
const day = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }) : "";

interface FilePickerProps {
  id: string;
  label: string;
  help: string;
  files: File[];
  max: number;
  required?: boolean;
  onChange: (files: File[]) => void;
  onProblem: (message: string) => void;
}

/** A labelled file field that keeps what was chosen in view and lets each file be removed. */
const FilePicker = ({ id, label, help, files, max, required, onChange, onProblem }: FilePickerProps) => {
  const input = useRef<HTMLInputElement>(null);
  const choose = (list: FileList | null) => {
    const chosen = Array.from(list ?? []);
    if (input.current) input.current.value = "";
    const next = [...files];
    for (const file of chosen) {
      const problem = fileProblem(file);
      if (problem) onProblem(problem);
      else if (next.length >= max) onProblem(`At most ${max} file${max === 1 ? "" : "s"} here.`);
      else next.push(file);
    }
    onChange(next);
  };
  return (
    <div className="space-y-2 rounded-lg border border-border p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <Label htmlFor={id}>
            {label}
            {required && <span className="text-destructive"> *</span>}
          </Label>
          <p className="text-xs text-muted-foreground mt-1">{help}</p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="gap-1.5 shrink-0"
          disabled={files.length >= max}
          onClick={() => input.current?.click()}
        >
          <Upload size={14} /> Choose file
        </Button>
      </div>
      <input
        ref={input}
        id={id}
        data-testid={id}
        type="file"
        accept={ACCEPT}
        multiple={max > 1}
        className="sr-only"
        onChange={(e) => choose(e.target.files)}
      />
      {files.length > 0 && (
        <ul className="space-y-1.5">
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`} className="flex items-center justify-between gap-2 rounded-md bg-muted/50 px-2.5 py-1.5 text-xs">
              <span className="flex items-center gap-1.5 min-w-0">
                <FileText size={13} className="shrink-0 text-primary" />
                <span className="truncate">{f.name}</span>
              </span>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 px-2"
                aria-label={`Remove ${f.name}`}
                onClick={() => onChange(files.filter((_, j) => j !== i))}
              >
                <X size={13} />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

/** A signed-in claimant's claims, with the team's last message and a way to add a document. */
const MyClaims = () => {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { data: claims } = useQuery({ queryKey: ["estate-claims", "mine"], queryFn: estateClaimsApi.mine });
  const [kind, setKind] = useState<EstateClaimDocumentKind>("evidence");
  const inputs = useRef<Record<string, HTMLInputElement | null>>({});
  const add = useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => estateClaimsApi.addDocument(id, kind, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["estate-claims", "mine"] });
      toast({ title: "Document added", description: "Our team was told and continues the review." });
    },
    onError: (e: unknown) =>
      toast({
        title: "Could not add the document",
        description: e instanceof ApiError ? e.message : "Please try again.",
        variant: "destructive",
      }),
  });
  if (!claims || claims.length === 0) return null;
  return (
    <Card data-testid="my-claims">
      <CardHeader>
        <CardTitle className="text-lg">Your claims</CardTitle>
        <CardDescription>Their status, and what our team last wrote to you.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {claims.map((c: Claim) => (
          <div key={c.id} className="rounded-lg border border-border p-4 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-semibold">{c.reference}</p>
                <p className="text-xs text-muted-foreground">
                  About the account of {c.holder_name} · sent {day(c.created_at)}
                </p>
              </div>
              <Badge variant="outline" className={STATUS_TONE[c.status] ?? ""}>{c.status_label}</Badge>
            </div>
            {c.message && (
              <p className="text-sm rounded-md bg-muted/50 p-3 whitespace-pre-line">
                <span className="font-medium">Message from our team: </span>
                {c.message}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              Documents sent: {c.documents.map((d) => d.filename).join(", ") || "none"}
            </p>
            {c.can_add_documents && (
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Select value={kind} onValueChange={(v) => setKind(v as EstateClaimDocumentKind)}>
                  <SelectTrigger className="w-[260px] h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="evidence">Official supporting document</SelectItem>
                    <SelectItem value="identity">My identity document</SelectItem>
                    <SelectItem value="certificate">Beneficiary certificate</SelectItem>
                    <SelectItem value="other">Other document</SelectItem>
                  </SelectContent>
                </Select>
                <input
                  ref={(el) => (inputs.current[c.id] = el)}
                  type="file"
                  accept={ACCEPT}
                  className="sr-only"
                  data-testid={`claim-file-${c.id}`}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.target.value = "";
                    if (!file) return;
                    const problem = fileProblem(file);
                    if (problem) toast({ title: "File not added", description: problem, variant: "destructive" });
                    else add.mutate({ id: c.id, file });
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  disabled={add.isPending}
                  onClick={() => inputs.current[c.id]?.click()}
                >
                  <Upload size={14} /> {add.isPending ? "Uploading…" : "Add a document"}
                </Button>
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
};

const EstateClaim = () => {
  const { toast } = useToast();
  const { user, isAuthenticated } = useAuth();
  const [params] = useSearchParams();
  const queryClient = useQueryClient();

  const [form, setForm] = useState({
    claimant_name: "",
    claimant_email: "",
    claimant_phone: "",
    claimant_country: "",
    claimant_id_type: "Passport",
    claimant_id_number: "",
    relationship: "",
    holder_name: "",
    holder_email: "",
    certificate_no: params.get("certificate") ?? "",
    date_of_death: "",
    details: "",
  });
  const [reason, setReason] = useState<EstateClaimReason>("death");
  const [certificate, setCertificate] = useState<File[]>([]);
  const [identity, setIdentity] = useState<File[]>([]);
  const [evidence, setEvidence] = useState<File[]>([]);
  const [declared, setDeclared] = useState(false);
  const [sent, setSent] = useState<Claim | null>(null);

  // a signed-in member's own name and address, once (they stay editable)
  const filled = useRef(false);
  useEffect(() => {
    if (!user || filled.current) return;
    filled.current = true;
    setForm((f) => ({
      ...f,
      claimant_name: f.claimant_name || (user.full_name ?? ""),
      claimant_email: f.claimant_email || user.email,
    }));
  }, [user]);

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));
  const problem = (message: string) => toast({ title: "File not added", description: message, variant: "destructive" });

  const submit = useMutation({
    mutationFn: () =>
      estateClaimsApi.submit(
        {
          claimant_name: form.claimant_name.trim(),
          claimant_email: form.claimant_email.trim(),
          claimant_phone: form.claimant_phone.trim() || undefined,
          claimant_country: form.claimant_country.trim(),
          claimant_id_type: form.claimant_id_type,
          claimant_id_number: form.claimant_id_number.trim() || undefined,
          relationship: form.relationship.trim() || undefined,
          holder_name: form.holder_name.trim(),
          holder_email: form.holder_email.trim() || undefined,
          certificate_no: form.certificate_no.trim(),
          reason,
          date_of_death: reason === "death" ? form.date_of_death : null,
          details: form.details.trim() || undefined,
        },
        { certificate: certificate[0], identity, evidence },
      ),
    onSuccess: (claim) => {
      setSent(claim);
      queryClient.invalidateQueries({ queryKey: ["estate-claims", "mine"] });
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    onError: (e: unknown) =>
      toast({
        title: "The claim was not sent",
        description:
          e instanceof ApiError
            ? e.status === 413
              ? TOO_LARGE_TOGETHER
              : e.message
            : "Please check your connection and try again.",
        variant: "destructive",
      }),
  });

  const missing = (): string | null => {
    if (!form.claimant_name.trim()) return "Enter your full name.";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.claimant_email.trim())) return "Enter a valid email address.";
    if (!form.claimant_country.trim()) return "Enter your country.";
    if (!form.holder_name.trim()) return "Enter the account holder's full name.";
    if (reason === "death" && !form.date_of_death) return "Enter the date of death.";
    if (reason === "other" && !form.details.trim()) return "Describe the reason for the claim.";
    if (!form.certificate_no.trim()) return "Enter the certificate number printed on the beneficiary certificate.";
    if (certificate.length === 0) return "Attach the beneficiary certificate.";
    if (identity.length === 0) return "Attach a copy of your identity document.";
    // phone photos add up: said here, before a long upload is refused
    const together = [...certificate, ...identity, ...evidence].reduce((sum, f) => sum + f.size, 0);
    if (together > CLAIM_MAX_TOTAL_BYTES) return TOO_LARGE_TOGETHER;
    if (!declared) return "Confirm the declaration at the end of the form.";
    return null;
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const what = missing();
    if (what) {
      toast({ title: "The form is not complete", description: what, variant: "destructive" });
      return;
    }
    submit.mutate();
  };

  const needsAccount = !isAuthenticated;
  const needsKyc = isAuthenticated && user?.kyc_status !== "verified";

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl space-y-8">
      <div className="text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
          <ScrollText className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-3xl md:text-4xl font-bold text-foreground mb-3">Report a Death or Make a Claim</h1>
        <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
          For a person an account holder named as beneficiary, heir, authorized person or legal
          representative, and holds a beneficiary certificate from Capimax PropShare.
        </p>
      </div>

      {sent ? (
        <Card className="border-primary/30" data-testid="claim-sent">
          <CardContent className="p-8 text-center space-y-4">
            <CheckCircle2 className="h-12 w-12 text-primary mx-auto" />
            <div>
              <h2 className="text-2xl font-bold">We received your claim</h2>
              <p className="text-muted-foreground mt-1">Your reference is</p>
              <p className="text-2xl font-mono font-bold text-primary mt-1" data-testid="claim-reference">
                {sent.reference}
              </p>
            </div>
            <p className="text-sm text-muted-foreground max-w-xl mx-auto">
              We sent it to {form.claimant_email.trim()} as well. Our team checks the certificate and the
              documents you sent, and writes to you at that address if anything else is needed and when
              the claim is decided.
            </p>
            {(needsAccount || needsKyc) && (
              <div className="rounded-lg bg-muted/60 p-4 text-sm max-w-xl mx-auto">
                <p className="font-medium">One thing you can do now</p>
                <p className="text-muted-foreground mt-1">
                  {needsAccount
                    ? "Create your own Capimax PropShare account with the same email address, confirm the address from the email we send you, and verify your identity in it. The transfer is made to that account only."
                    : "Complete identity verification in your account. The transfer is made to a verified account only."}
                </p>
                <Button asChild className="mt-3">
                  <Link to={needsAccount ? "/auth?tab=register" : "/kyc"}>
                    {needsAccount ? "Create your account" : "Verify your identity"}
                  </Link>
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {STEPS.map((s, i) => (
              <Card key={s.title}>
                <CardContent className="p-5">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-9 h-9 rounded-full bg-primary/10 text-primary flex items-center justify-center">
                      <s.icon size={18} />
                    </div>
                    <span className="text-xs font-semibold text-muted-foreground">Step {i + 1}</span>
                  </div>
                  <h3 className="font-semibold text-foreground">{s.title}</h3>
                  <p className="text-sm text-muted-foreground mt-1">{s.text}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-sm" data-testid="own-account-notice">
            <Lock size={18} className="mt-0.5 shrink-0 text-amber-600" />
            <div>
              <p className="font-semibold text-foreground">You need an account of your own</p>
              <p className="text-muted-foreground mt-1">
                Assets are transferred only to your own Capimax PropShare account, once your identity is
                verified in it. Nobody is given the account holder's account, password or records: they stay
                private.
              </p>
              {(needsAccount || needsKyc) && (
                <Button asChild variant="outline" size="sm" className="mt-3">
                  <Link to={needsAccount ? "/auth?tab=register" : "/kyc"}>
                    {needsAccount ? "Create your account" : "Verify your identity"}
                  </Link>
                </Button>
              )}
            </div>
          </div>
        </>
      )}

      {isAuthenticated && user && !user.email_verified && (
        <div
          className="flex items-start gap-3 rounded-lg border border-border bg-muted/40 p-4 text-sm"
          data-testid="confirm-email-notice"
        >
          <MailCheck size={18} className="mt-0.5 shrink-0 text-primary" />
          <div>
            <p className="font-semibold text-foreground">Confirm your email address</p>
            <p className="text-muted-foreground mt-1">
              A claim sent with {user.email} before you signed in shows here, and is tied to this account,
              once that address is confirmed. If the link we emailed when you signed up has expired, ask
              for a new one.
            </p>
            <div className="mt-3">
              <ConfirmEmailButton email={user.email} />
            </div>
          </div>
        </div>
      )}

      {isAuthenticated && <MyClaims />}

      {!sent && (
        <Card>
          <CardHeader>
            <CardTitle>Claim form</CardTitle>
            <CardDescription>Fields marked * are required.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-6" noValidate>
              <fieldset className="space-y-4">
                <legend className="text-sm font-semibold text-primary uppercase tracking-wide">About you</legend>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="claimant_name">Your full name <span className="text-destructive">*</span></Label>
                    <Input id="claimant_name" value={form.claimant_name} onChange={set("claimant_name")} placeholder="As on your identity document" autoComplete="name" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="claimant_email">Email address <span className="text-destructive">*</span></Label>
                    <Input id="claimant_email" type="email" value={form.claimant_email} onChange={set("claimant_email")} placeholder="We write to you here" autoComplete="email" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="claimant_phone">Phone</Label>
                    <Input id="claimant_phone" value={form.claimant_phone} onChange={set("claimant_phone")} placeholder="With the country code" autoComplete="tel" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="claimant_country">Country <span className="text-destructive">*</span></Label>
                    <Input id="claimant_country" value={form.claimant_country} onChange={set("claimant_country")} placeholder="Where you live" autoComplete="country-name" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="relationship">Your relationship to the account holder</Label>
                    <Input id="relationship" value={form.relationship} onChange={set("relationship")} placeholder="Spouse, son, daughter, lawyer…" />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-2">
                      <Label>Identity document</Label>
                      <Select value={form.claimant_id_type} onValueChange={(v) => setForm((f) => ({ ...f, claimant_id_type: v }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="Passport">Passport</SelectItem>
                          <SelectItem value="National ID">National ID</SelectItem>
                          <SelectItem value="Other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="claimant_id_number">Document number</Label>
                      <Input id="claimant_id_number" value={form.claimant_id_number} onChange={set("claimant_id_number")} />
                    </div>
                  </div>
                </div>
              </fieldset>

              <fieldset className="space-y-4">
                <legend className="text-sm font-semibold text-primary uppercase tracking-wide">The account holder</legend>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="holder_name">Account holder's full name <span className="text-destructive">*</span></Label>
                    <Input id="holder_name" value={form.holder_name} onChange={set("holder_name")} placeholder="As printed on the certificate" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="holder_email">Account holder's email, if you know it</Label>
                    <Input id="holder_email" type="email" value={form.holder_email} onChange={set("holder_email")} />
                  </div>
                  <div className="space-y-2">
                    <Label>Reason for the claim <span className="text-destructive">*</span></Label>
                    <Select value={reason} onValueChange={(v) => setReason(v as EstateClaimReason)}>
                      <SelectTrigger data-testid="claim-reason"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {REASONS.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  {reason === "death" && (
                    <div className="space-y-2">
                      <Label htmlFor="date_of_death">Date of death <span className="text-destructive">*</span></Label>
                      <Input id="date_of_death" type="date" max={today()} value={form.date_of_death} onChange={set("date_of_death")} />
                    </div>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="details">
                    Anything our team should know
                    {reason === "other" && <span className="text-destructive"> *</span>}
                  </Label>
                  <Textarea id="details" rows={3} value={form.details} onChange={set("details")} placeholder="For example where the death was registered, or what the documents you attach are." />
                </div>
              </fieldset>

              <fieldset className="space-y-4">
                <legend className="text-sm font-semibold text-primary uppercase tracking-wide">Documents</legend>
                <div className="space-y-2">
                  <Label htmlFor="certificate_no">Certificate number <span className="text-destructive">*</span></Label>
                  <Input id="certificate_no" value={form.certificate_no} onChange={set("certificate_no")} placeholder="CPB-XXXX-XXXX" className="font-mono" />
                  <p className="text-xs text-muted-foreground">
                    Printed on the beneficiary certificate the account holder gave you.{" "}
                    <Link to="/support" className="text-primary underline">No certificate? Contact support.</Link>
                  </p>
                </div>
                <FilePicker
                  id="claim-certificate"
                  label="The beneficiary certificate"
                  help="The certificate issued by Capimax PropShare with your name on it. A PDF or a clear photo, up to 10 MB."
                  files={certificate}
                  max={1}
                  required
                  onChange={setCertificate}
                  onProblem={problem}
                />
                <FilePicker
                  id="claim-identity"
                  label="Your identity document"
                  help="Your passport or identity card (both sides if it has two). A PDF or clear photos, up to 10 MB each."
                  files={identity}
                  max={2}
                  required
                  onChange={setIdentity}
                  onProblem={problem}
                />
                <FilePicker
                  id="claim-evidence"
                  label={reason === "death" ? "The official death certificate" : "The official document supporting your claim"}
                  help="Send it now if you have it: nothing is transferred before our team has it. You can also add it later from your account."
                  files={evidence}
                  max={3}
                  onChange={setEvidence}
                  onProblem={problem}
                />
              </fieldset>

              <label className="flex items-start gap-3 text-sm cursor-pointer">
                <Checkbox
                  checked={declared}
                  onCheckedChange={(v) => setDeclared(v === true)}
                  className="mt-0.5"
                  aria-label="Declaration"
                />
                <span>
                  I confirm that what I wrote is true and that the documents are genuine. I understand that
                  the account holder is told about this claim, and that a false claim is refused and may be
                  reported.
                </span>
              </label>

              <Button type="submit" size="lg" className="w-full gap-2" disabled={submit.isPending}>
                <Send size={16} /> {submit.isPending ? "Sending…" : "Send the claim"}
              </Button>
              <p className="text-xs text-muted-foreground flex items-start gap-2">
                <IdCard size={14} className="mt-0.5 shrink-0" />
                Your documents are used only to review this claim, and are seen only by the team that
                reviews it.
              </p>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default EstateClaim;
