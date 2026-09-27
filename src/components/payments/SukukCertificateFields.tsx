import { FileText, ShieldAlert } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";

/**
 * Paying with a Nova Sukuk certificate (Nova Digital Finance): the investor uploads the
 * certificate (PDF) and what it states; our team reviews it while the units are held. Approved,
 * the units are the investor's but stay pledged to Nova Finance until it releases them.
 */
export const MAX_CERTIFICATE_BYTES = 10 * 1024 * 1024;

export interface SukukDraft {
  file: File | null;
  certificate_no: string;
  issuer: string;
  certificate_value: string;
  valid_until: string;
  accepted: boolean;
}

export const EMPTY_SUKUK_DRAFT: SukukDraft = {
  file: null,
  certificate_no: "",
  issuer: "",
  certificate_value: "",
  valid_until: "",
  accepted: false,
};

export function certificateProblem(file: File | null): string | null {
  if (!file) return "Attach your Nova certificate (PDF).";
  const pdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!pdf) return "The certificate must be a PDF file.";
  if (file.size > MAX_CERTIFICATE_BYTES) return "The certificate must be 10 MB or smaller.";
  return null;
}

/** Ready to submit: a valid PDF and the pledge accepted. */
export function sukukReady(draft: SukukDraft): boolean {
  return certificateProblem(draft.file) === null && draft.accepted;
}

export function NovaPledgeNotice({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-foreground"
      data-testid="nova-pledge-notice"
    >
      <div className="flex items-center gap-2 font-semibold mb-1">
        <ShieldAlert className="h-4 w-4 text-amber-600" /> Nova Finance pledge
      </div>
      <p className="text-muted-foreground">
        Units paid with a Nova Sukuk certificate are pledged to Nova Finance. They are yours, but
        you cannot sell, exit, gift or transfer them until Nova Finance releases them.
        {!compact &&
          " Financing is provided by Nova Digital Finance under its own agreement; the platform does not decide or guarantee it."}
      </p>
    </div>
  );
}

interface Props {
  amountDue: number;
  value: SukukDraft;
  onChange: (next: SukukDraft) => void;
}

export function SukukCertificateFields({ amountDue, value, onChange }: Props) {
  const set = (patch: Partial<SukukDraft>) => onChange({ ...value, ...patch });
  const fileProblem = value.file ? certificateProblem(value.file) : null;
  const due = amountDue.toLocaleString("en-US", { style: "currency", currency: "USD" });
  return (
    <div className="space-y-3 rounded-xl border border-border p-4" data-testid="sukuk-fields">
      <div className="flex items-start gap-2 text-sm">
        <FileText className="h-4 w-4 text-primary mt-0.5 shrink-0" />
        <p className="text-muted-foreground">
          Upload your Nova Digital Finance certificate (PDF, up to 10&nbsp;MB). Our team reviews
          it and your units are held for you meanwhile. The certificate must cover{" "}
          <span className="font-semibold text-foreground">{due}</span>.
        </p>
      </div>
      <div className="space-y-1">
        <Label htmlFor="sukuk-file">Certificate (PDF)</Label>
        <Input
          id="sukuk-file"
          type="file"
          accept="application/pdf,.pdf"
          onChange={(e) => set({ file: e.target.files?.[0] ?? null })}
        />
        {fileProblem && <p className="text-xs text-destructive">{fileProblem}</p>}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="sukuk-no">Certificate no. (optional)</Label>
          <Input
            id="sukuk-no"
            placeholder="NOVA-…"
            value={value.certificate_no}
            onChange={(e) => set({ certificate_no: e.target.value })}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="sukuk-issuer">Issuer (optional)</Label>
          <Input
            id="sukuk-issuer"
            placeholder="Nova Digital Finance"
            value={value.issuer}
            onChange={(e) => set({ issuer: e.target.value })}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="sukuk-value">Certificate value, USD (optional)</Label>
          <Input
            id="sukuk-value"
            inputMode="decimal"
            placeholder={amountDue.toFixed(2)}
            value={value.certificate_value}
            onChange={(e) => set({ certificate_value: e.target.value })}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="sukuk-until">Valid until (optional)</Label>
          <Input
            id="sukuk-until"
            type="date"
            value={value.valid_until}
            onChange={(e) => set({ valid_until: e.target.value })}
          />
        </div>
      </div>
      <NovaPledgeNotice />
      <label className="flex items-start gap-2 text-sm cursor-pointer">
        <Checkbox
          id="sukuk-accept"
          checked={value.accepted}
          onCheckedChange={(checked) => set({ accepted: checked === true })}
        />
        <span>I understand these units stay pledged to Nova Finance until it releases them.</span>
      </label>
    </div>
  );
}

export default SukukCertificateFields;
