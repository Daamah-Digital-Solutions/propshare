import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Calendar,
  Check,
  Globe,
  Landmark,
  Mail,
  MapPin,
  Phone,
  Plus,
  ShieldCheck,
  Trash2,
  User,
  Users,
} from "lucide-react";
import { ApiError, familyApi, type FamilyMember } from "@/lib/api";
import { toast } from "sonner";

const RELATIONSHIPS = ["Spouse", "Son", "Daughter", "Parent", "Sibling", "Other"];

const emptyBank = {
  bank_name: "",
  account_holder: "",
  iban: "",
  account_number: "",
  swift_bic: "",
};

const InfoRow = ({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string | null | undefined;
}) => (
  <div className="flex items-start gap-3 rounded-lg border border-border p-3">
    <Icon className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
    <div className="min-w-0">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-sm font-medium text-foreground break-words">{value || "—"}</p>
    </div>
  </div>
);

export function FamilyMemberDetail({
  member,
  open,
  onOpenChange,
  onChanged,
}: {
  member: FamilyMember | null;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onChanged: () => void;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [addingBank, setAddingBank] = useState(false);
  const [form, setForm] = useState({
    name: "",
    email: "",
    relationship: "",
    date_of_birth: "",
    phone: "",
    national_id: "",
    nationality: "",
    address: "",
  });
  const [bank, setBank] = useState(emptyBank);

  useEffect(() => {
    if (member) {
      setForm({
        name: member.name,
        email: member.email ?? "",
        relationship: member.relationship,
        date_of_birth: member.date_of_birth ?? "",
        phone: member.phone ?? "",
        national_id: member.national_id ?? "",
        nationality: member.nationality ?? "",
        address: member.address ?? "",
      });
    }
    setEditing(false);
    setAddingBank(false);
    setBank(emptyBank);
  }, [member]);

  const memberId = member?.member_id ?? "";

  const { data: banks } = useQuery({
    queryKey: ["family", "member-banks", memberId],
    queryFn: () => familyApi.listMemberBankAccounts(memberId),
    enabled: !!memberId && open,
    initialData: member?.bank_accounts,
  });

  const save = useMutation({
    mutationFn: () =>
      familyApi.updateMember(memberId, {
        name: form.name,
        email: form.email || undefined,
        relationship: form.relationship,
        date_of_birth: form.date_of_birth || null,
        phone: form.phone || null,
        national_id: form.national_id || null,
        nationality: form.nationality || null,
        address: form.address || null,
      }),
    onSuccess: () => {
      toast.success("Member updated");
      setEditing(false);
      onChanged();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not save the member"),
  });

  const addBank = useMutation({
    mutationFn: () => familyApi.addMemberBankAccount(memberId, bank),
    onSuccess: () => {
      toast.success("Bank account added");
      setBank(emptyBank);
      setAddingBank(false);
      qc.invalidateQueries({ queryKey: ["family", "member-banks", memberId] });
      onChanged();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not add the account"),
  });

  const delBank = useMutation({
    mutationFn: (id: string) => familyApi.deleteMemberBankAccount(memberId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["family", "member-banks", memberId] });
      onChanged();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not remove the account"),
  });

  if (!member) return null;

  const linked = member.linked_date ? new Date(member.linked_date).toLocaleDateString() : "—";
  const bankList = banks ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center">
              <User className="h-4 w-4 text-primary" />
            </div>
            <span>{member.name}</span>
            {member.is_verified ? (
              <Badge variant="outline" className="bg-emerald-500/10 text-emerald-600 border-emerald-500/30">
                <Check className="h-3 w-3 mr-1" /> Verified
              </Badge>
            ) : (
              <Badge variant="outline" className="bg-amber-500/10 text-amber-600 border-amber-500/30">
                Pending
              </Badge>
            )}
          </DialogTitle>
        </DialogHeader>

        {/* Personal Information */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4 text-primary" /> Personal Information
            </h4>
            {!editing && (
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
          </div>

          {editing ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5 col-span-2">
                  <Label>Full name</Label>
                  <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>Relationship</Label>
                  <Select value={form.relationship} onValueChange={(v) => setForm({ ...form, relationship: v })}>
                    <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                    <SelectContent>
                      {RELATIONSHIPS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Date of birth</Label>
                  <Input type="date" value={form.date_of_birth} onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} />
                </div>
                <div className="space-y-1.5 col-span-2">
                  <Label>Email</Label>
                  <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>Phone</Label>
                  <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>Nationality</Label>
                  <Input value={form.nationality} onChange={(e) => setForm({ ...form, nationality: e.target.value })} />
                </div>
                <div className="space-y-1.5 col-span-2">
                  <Label>National ID / Passport</Label>
                  <Input value={form.national_id} onChange={(e) => setForm({ ...form, national_id: e.target.value })} />
                </div>
                <div className="space-y-1.5 col-span-2">
                  <Label>Address</Label>
                  <Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
                </div>
              </div>
              <div className="flex gap-2 justify-end">
                <Button variant="outline" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
                <Button size="sm" disabled={!form.name || !form.relationship || save.isPending} onClick={() => save.mutate()}>
                  {save.isPending ? "Saving…" : "Save"}
                </Button>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <InfoRow icon={User} label="Name" value={member.name} />
              <InfoRow icon={Users} label="Relationship" value={member.relationship} />
              <InfoRow icon={Mail} label="Email" value={member.email} />
              <InfoRow icon={Calendar} label="Date of birth" value={member.date_of_birth} />
              <InfoRow icon={Phone} label="Phone" value={member.phone} />
              <InfoRow icon={Globe} label="Nationality" value={member.nationality} />
              <InfoRow icon={ShieldCheck} label="National ID / Passport" value={member.national_id} />
              <InfoRow icon={Calendar} label="Linked date" value={linked} />
              <div className="col-span-2">
                <InfoRow icon={MapPin} label="Address" value={member.address} />
              </div>
            </div>
          )}
        </section>

        {/* Financial Summary */}
        <section className="space-y-2">
          <h4 className="text-sm font-semibold">Financial Summary</h4>
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-lg border border-border p-3 text-center">
              <p className="text-lg font-bold text-emerald-600">${Number(member.allocated_returns).toLocaleString()}</p>
              <p className="text-[11px] text-muted-foreground">Allocated Returns</p>
            </div>
            <div className="rounded-lg border border-border p-3 text-center">
              <p className="text-lg font-bold text-foreground">{member.real_units}</p>
              <p className="text-[11px] text-muted-foreground">Units held</p>
            </div>
            <div className="rounded-lg border border-border p-3 text-center">
              <p className="text-lg font-bold text-amber-600">{member.pending_units}</p>
              <p className="text-[11px] text-muted-foreground">Pending units</p>
            </div>
          </div>
        </section>

        {/* Bank Accounts */}
        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold flex items-center gap-1.5">
              <Landmark className="h-4 w-4 text-primary" /> Bank Accounts
            </h4>
            {!addingBank && (
              <Button variant="outline" size="sm" onClick={() => setAddingBank(true)}>
                <Plus className="h-4 w-4 mr-1" /> Add Bank Account
              </Button>
            )}
          </div>

          {bankList.length === 0 && !addingBank && (
            <p className="text-sm text-muted-foreground text-center py-3">No bank accounts linked.</p>
          )}
          {bankList.map((b) => (
            <div key={b.id} className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <p className="text-sm font-medium text-foreground">
                  {b.bank_name} {b.iban || b.account_number ? `···· ${(b.iban ?? b.account_number ?? "").slice(-4)}` : ""}
                </p>
                <p className="text-xs text-muted-foreground">{b.account_holder ?? "—"}</p>
              </div>
              <Button variant="ghost" size="icon" aria-label="Remove bank account" disabled={delBank.isPending} onClick={() => delBank.mutate(b.id)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}

          {addingBank && (
            <div className="space-y-3 rounded-lg border border-border p-3 bg-muted/30">
              <div className="space-y-1.5">
                <Label>Bank name</Label>
                <Input value={bank.bank_name} onChange={(e) => setBank({ ...bank, bank_name: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label>Account holder</Label>
                <Input value={bank.account_holder} onChange={(e) => setBank({ ...bank, account_holder: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>IBAN</Label>
                  <Input value={bank.iban} onChange={(e) => setBank({ ...bank, iban: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>Account number</Label>
                  <Input value={bank.account_number} onChange={(e) => setBank({ ...bank, account_number: e.target.value })} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>SWIFT / BIC</Label>
                <Input value={bank.swift_bic} onChange={(e) => setBank({ ...bank, swift_bic: e.target.value })} />
              </div>
              <p className="text-xs text-muted-foreground">Provide an IBAN or an account number.</p>
              <div className="flex gap-2 justify-end">
                <Button variant="outline" size="sm" onClick={() => { setAddingBank(false); setBank(emptyBank); }}>Cancel</Button>
                <Button size="sm" disabled={!bank.bank_name || addBank.isPending} onClick={() => addBank.mutate()}>
                  {addBank.isPending ? "Adding…" : "Add account"}
                </Button>
              </div>
            </div>
          )}
        </section>
      </DialogContent>
    </Dialog>
  );
}
