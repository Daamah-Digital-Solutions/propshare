import { useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Shield,
  ScrollText,
  UserPlus,
  Gift,
  Lock,
  Clock,
  AlertCircle,
  Pencil,
  Trash2,
  CheckCircle2,
  Calendar as CalendarIcon,
  Repeat,
  Sparkles,
  Heart,
  GraduationCap,
  Cake,
  Trophy,
  PartyPopper,
  Plus,
  Send,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { useToast } from "@/hooks/use-toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  estateApi,
  giftsApi,
  holdingsApi,
  type EstateBeneficiary as ApiBeneficiary,
  type GiftAsset,
  type Holding,
  type ScheduledGift,
} from "@/lib/api";

// Group 4: map the real backend beneficiary row <-> the existing UI Beneficiary shape.
// The UI's extra fields (role/idType/idNumber/scope/trigger) round-trip via `meta` so NO
// markup/copy changes are needed — only the data layer is swapped from local mock to the API.
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
  };
};

// ─────────────────────────────────────────────────────────────────────────────
// Beneficiary types
// ─────────────────────────────────────────────────────────────────────────────

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
}

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

// Beneficiaries now load from the real estate API (see the component body) — the prior
// hardcoded mock list has been retired (no fabricated beneficiaries shipped).

// ─────────────────────────────────────────────────────────────────────────────
// Gifting types (Group 5 — REAL scheduled + recurring gifts)
// ─────────────────────────────────────────────────────────────────────────────

type Occasion = "birthday" | "graduation" | "wedding" | "celebration" | "achievement" | "special";

const occasionMeta: Record<Occasion, { label: string; icon: typeof Gift; color: string }> = {
  birthday: { label: "Birthday", icon: Cake, color: "from-pink-500 to-rose-500" },
  graduation: { label: "Graduation", icon: GraduationCap, color: "from-indigo-500 to-blue-500" },
  wedding: { label: "Marriage", icon: Heart, color: "from-rose-500 to-red-500" },
  celebration: { label: "Family Celebration", icon: PartyPopper, color: "from-amber-500 to-orange-500" },
  achievement: { label: "Achievement Milestone", icon: Trophy, color: "from-emerald-500 to-teal-500" },
  special: { label: "Special Event", icon: Sparkles, color: "from-purple-500 to-fuchsia-500" },
};

// Asset options follow the original UI. Only property_shares + wallet have a REAL backing
// and can be gifted; the rest are honest-disabled (shown, not removed) exactly as PASSIVE
// is everywhere — tokenization is the separate BRX project, not PropShare.
const giftAssetOptions: { value: string; label: string; enabled: boolean }[] = [
  { value: "property_shares", label: "Property Shares", enabled: true },
  { value: "wallet", label: "Wallet Balance", enabled: true },
  { value: "tokenized", label: "Tokenized Ownership", enabled: false },
  { value: "passive_income", label: "Passive Income", enabled: false },
  { value: "rental_returns", label: "Rental Returns", enabled: false },
  { value: "allocation", label: "Asset Allocation", enabled: false },
];

const giftAssetLabel = (a: string): string =>
  giftAssetOptions.find((o) => o.value === a)?.label ?? a;

const giftStatusMeta: Record<string, { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
  scheduled: { label: "Scheduled", variant: "secondary" },
  pending: { label: "Awaiting recipient", variant: "secondary" },
  executed: { label: "Delivered", variant: "default" },
  cancelled: { label: "Cancelled", variant: "outline" },
  failed: { label: "Failed", variant: "destructive" },
};

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const FamilyBeneficiaryGifting = () => {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  // Beneficiaries: real, owner-scoped data from the estate API (mapped to the UI shape).
  const { data: apiBeneficiaries } = useQuery({
    queryKey: ["estate-beneficiaries"],
    queryFn: estateApi.list,
  });
  const beneficiaries: Beneficiary[] = (apiBeneficiaries ?? []).map(fromApi);

  const totalAllocated = useMemo(
    () => beneficiaries.reduce((s, b) => s + b.allocationPct, 0),
    [beneficiaries]
  );

  // ── Add beneficiary form ─────────────────────────────────────────────────
  const [bOpen, setBOpen] = useState(false);
  const [bForm, setBForm] = useState<Omit<Beneficiary, "id" | "status">>({
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
  });

  const toggleScope = (s: CoverageScope) => {
    setBForm((f) => ({
      ...f,
      scope: f.scope.includes(s) ? f.scope.filter((x) => x !== s) : [...f.scope, s],
    }));
  };

  const refetchBeneficiaries = () =>
    queryClient.invalidateQueries({ queryKey: ["estate-beneficiaries"] });

  const addMutation = useMutation({
    mutationFn: () =>
      estateApi.add({
        full_name: bForm.fullName,
        relationship: bForm.relationship,
        email: bForm.email || null,
        phone: bForm.phone || null,
        allocation_pct: bForm.allocationPct,
        notes: bForm.notes || null,
        // UI extras round-trip via meta so no markup change is needed.
        meta: {
          role: bForm.role,
          idType: bForm.idType,
          idNumber: bForm.idNumber,
          scope: bForm.scope,
          trigger: bForm.trigger,
        },
      }),
    onSuccess: () => {
      setBOpen(false);
      setBForm({
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
      });
      refetchBeneficiaries();
      toast({ title: "Beneficiary added", description: "Awaiting verification & legal acknowledgement." });
    },
    onError: (e: unknown) =>
      toast({
        title: "Could not save beneficiary",
        description: e instanceof Error ? e.message : "Please try again.",
        variant: "destructive",
      }),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => estateApi.remove(id),
    onSuccess: refetchBeneficiaries,
  });

  const addBeneficiary = () => {
    if (!bForm.fullName || !bForm.relationship) {
      toast({ title: "Missing info", description: "Add full name and relationship.", variant: "destructive" });
      return;
    }
    const remaining = 100 - totalAllocated;
    if (bForm.allocationPct > remaining) {
      toast({
        title: "Allocation exceeds 100%",
        description: `Only ${remaining}% remaining to allocate.`,
        variant: "destructive",
      });
      return;
    }
    addMutation.mutate();
  };

  const removeBeneficiary = (id: string) => removeMutation.mutate(id);

  // ── Gifting (Group 5): real scheduled gifts from the API ─────────────────
  const { data: apiGifts } = useQuery({ queryKey: ["scheduled-gifts"], queryFn: giftsApi.list });
  const gifts: ScheduledGift[] = apiGifts ?? [];
  const { data: holdingsData } = useQuery({ queryKey: ["secondary-holdings"], queryFn: holdingsApi.mine });
  const holdings: Holding[] = holdingsData?.items ?? [];

  const refetchGifts = () => queryClient.invalidateQueries({ queryKey: ["scheduled-gifts"] });

  const [gOpen, setGOpen] = useState(false);
  const [gRecipientName, setGRecipientName] = useState("");
  const [gRecipientEmail, setGRecipientEmail] = useState("");
  const [gOccasion, setGOccasion] = useState<Occasion>("birthday");
  const [gAsset, setGAsset] = useState<GiftAsset>("property_shares");
  const [gPropertyId, setGPropertyId] = useState("");
  const [gUnits, setGUnits] = useState("");
  const [gAmount, setGAmount] = useState("");
  const [gDate, setGDate] = useState<Date | undefined>(undefined);
  const [gRecurring, setGRecurring] = useState(false);
  const [gMessage, setGMessage] = useState("");

  const resetGiftForm = () => {
    setGOpen(false);
    setGRecipientName("");
    setGRecipientEmail("");
    setGOccasion("birthday");
    setGAsset("property_shares");
    setGPropertyId("");
    setGUnits("");
    setGAmount("");
    setGDate(undefined);
    setGRecurring(false);
    setGMessage("");
  };

  const scheduleMutation = useMutation({
    mutationFn: () =>
      giftsApi.schedule({
        recipient_name: gRecipientName,
        recipient_email: gRecipientEmail,
        asset_type: gAsset,
        property_id: gAsset === "property_shares" ? gPropertyId : null,
        units: gAsset === "property_shares" ? Number(gUnits) : null,
        amount: gAsset === "wallet" ? Number(gAmount).toFixed(2) : null,
        occasion: gOccasion,
        message: gMessage || null,
        scheduled_for: gDate ? format(gDate, "yyyy-MM-dd") : "",
        recurring: gRecurring,
      }),
    onSuccess: () => {
      resetGiftForm();
      refetchGifts();
      queryClient.invalidateQueries({ queryKey: ["secondary-holdings"] });
      toast({ title: "Gift scheduled", description: "It will execute automatically on the chosen date." });
    },
    onError: (e: unknown) =>
      toast({
        title: "Could not schedule gift",
        description: e instanceof Error ? e.message : "Please try again.",
        variant: "destructive",
      }),
  });

  const cancelMutation = useMutation({
    mutationFn: (id: string) => giftsApi.cancel(id),
    onSuccess: () => {
      refetchGifts();
      queryClient.invalidateQueries({ queryKey: ["secondary-holdings"] });
      toast({ title: "Gift cancelled", description: "The reservation/escrow has been released." });
    },
    onError: (e: unknown) =>
      toast({
        title: "Could not cancel gift",
        description: e instanceof Error ? e.message : "Please try again.",
        variant: "destructive",
      }),
  });

  const scheduleGift = () => {
    if (!gRecipientName || !gRecipientEmail || !gDate) {
      toast({ title: "Missing info", description: "Recipient name, email and date are required.", variant: "destructive" });
      return;
    }
    if (gAsset === "property_shares" && (!gPropertyId || Number(gUnits) < 1)) {
      toast({ title: "Missing info", description: "Choose a property and number of units.", variant: "destructive" });
      return;
    }
    if (gAsset === "wallet" && Number(gAmount) <= 0) {
      toast({ title: "Missing info", description: "Enter a wallet amount to gift.", variant: "destructive" });
      return;
    }
    scheduleMutation.mutate();
  };

  return (
    <div className="space-y-8">
      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* BENEFICIARY & INHERITANCE                                            */}
      {/* ─────────────────────────────────────────────────────────────────── */}
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
              Designate beneficiaries, heirs, authorized persons and legal counsel for your real estate ownership,
              passive income and wallet — protected by structured transfer conditions.
            </p>
          </div>
          <Dialog open={bOpen} onOpenChange={setBOpen}>
            <DialogTrigger asChild>
              <Button size="lg" className="gap-2">
                <UserPlus size={18} /> Add Beneficiary
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Designate Beneficiary / Heir</DialogTitle>
                <DialogDescription>
                  Wealth-management grade structure. Information is encrypted and reviewed by our legal partners.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>Full legal name</Label>
                    <Input value={bForm.fullName} onChange={(e) => setBForm({ ...bForm, fullName: e.target.value })} placeholder="As shown on ID" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Relationship</Label>
                    <Input value={bForm.relationship} onChange={(e) => setBForm({ ...bForm, relationship: e.target.value })} placeholder="Spouse, Son, Daughter…" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Role</Label>
                    <Select value={bForm.role} onValueChange={(v) => setBForm({ ...bForm, role: v as BeneficiaryRole })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {(Object.keys(roleMeta) as BeneficiaryRole[]).map((r) => (
                          <SelectItem key={r} value={r}>{roleMeta[r].label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Email</Label>
                    <Input type="email" value={bForm.email} onChange={(e) => setBForm({ ...bForm, email: e.target.value })} />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Phone</Label>
                    <Input value={bForm.phone} onChange={(e) => setBForm({ ...bForm, phone: e.target.value })} />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1.5">
                      <Label>ID type</Label>
                      <Select value={bForm.idType} onValueChange={(v) => setBForm({ ...bForm, idType: v })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="Passport">Passport</SelectItem>
                          <SelectItem value="National ID">National ID</SelectItem>
                          <SelectItem value="Trade License">Trade License</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label>ID number</Label>
                      <Input value={bForm.idNumber} onChange={(e) => setBForm({ ...bForm, idNumber: e.target.value })} />
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label>Allocation percentage</Label>
                    <span className="text-sm font-semibold text-primary">{bForm.allocationPct}%</span>
                  </div>
                  <Slider
                    value={[bForm.allocationPct]}
                    onValueChange={(v) => setBForm({ ...bForm, allocationPct: v[0] })}
                    min={0}
                    max={100 - (totalAllocated - 0)}
                    step={5}
                  />
                  <div className="text-[11px] text-muted-foreground">
                    {totalAllocated}% currently allocated · {100 - totalAllocated}% remaining
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Coverage scope</Label>
                  <div className="grid grid-cols-2 gap-2">
                    {(Object.keys(scopeMeta) as CoverageScope[]).map((s) => {
                      const active = bForm.scope.includes(s);
                      return (
                        <button
                          type="button"
                          key={s}
                          onClick={() => toggleScope(s)}
                          className={cn(
                            "rounded-lg border p-2.5 text-left text-xs font-medium transition-colors",
                            active
                              ? "border-primary bg-primary/5 text-foreground"
                              : "border-border bg-background text-muted-foreground hover:border-primary/40"
                          )}
                        >
                          {scopeMeta[s]}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label>Transfer condition</Label>
                  <Select value={bForm.trigger} onValueChange={(v) => setBForm({ ...bForm, trigger: v as TransferTrigger })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {(Object.keys(triggerMeta) as TransferTrigger[]).map((t) => (
                        <SelectItem key={t} value={t}>{triggerMeta[t].label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label>Notes / instructions</Label>
                  <Textarea
                    value={bForm.notes}
                    onChange={(e) => setBForm({ ...bForm, notes: e.target.value })}
                    placeholder="Specific wishes, conditions or instructions for this beneficiary…"
                    rows={3}
                  />
                </div>

                <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-400">
                  <AlertCircle size={14} className="mt-0.5 shrink-0" />
                  <span>
                    All beneficiary changes are encrypted, logged, and reviewed by our legal partners before becoming legally binding.
                  </span>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setBOpen(false)}>Cancel</Button>
                <Button onClick={addBeneficiary}>Save Beneficiary</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

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
            const TIcon = triggerMeta[b.trigger].icon;
            return (
              <Card key={b.id} className="relative overflow-hidden">
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
                    <Badge className={cn("border-0", roleMeta[b.role].tone)}>
                      {roleMeta[b.role].label}
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
                        {scopeMeta[s]}
                      </Badge>
                    ))}
                  </div>

                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <TIcon size={13} className="text-primary" />
                    <span>{triggerMeta[b.trigger].label}</span>
                  </div>

                  {b.notes && (
                    <p className="text-xs text-muted-foreground italic border-l-2 border-border pl-2">
                      "{b.notes}"
                    </p>
                  )}

                  <div className="flex items-center justify-between pt-2 border-t border-border">
                    <Badge variant={b.status === "active" ? "default" : "secondary"} className="text-[10px]">
                      {b.status === "active" ? "Legally acknowledged" : "Pending verification"}
                    </Badge>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive hover:text-destructive"
                      onClick={() => removeBeneficiary(b.id)}
                    >
                      <Trash2 size={14} />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* GIFTING — REAL scheduled + recurring gifts (Group 5).                */}
      {/* Schedule reserves the units / escrows the cash; a server cron executes */}
      {/* due gifts on the date — so "executes automatically" is truthful.       */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/15 text-accent-foreground text-xs font-semibold mb-2">
              <Gift size={12} /> Family Gifting & Asset Transfer
            </div>
            <h3 className="text-xl md:text-2xl font-bold text-foreground">
              Gift Real Estate, Income & Allocations
            </h3>
            <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
              Transfer property shares or wallet balance to family members on special occasions —
              scheduled and executed automatically on the chosen date.
            </p>
          </div>

          <Dialog open={gOpen} onOpenChange={(o) => (o ? setGOpen(true) : resetGiftForm())}>
            <DialogTrigger asChild>
              <Button size="lg" className="gap-2">
                <Plus size={18} /> Schedule Gift
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Schedule a Gift</DialogTitle>
                <DialogDescription>
                  Choose recipient, asset and date — it executes automatically on the date.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>Recipient name</Label>
                    <Input
                      placeholder="Family member"
                      value={gRecipientName}
                      onChange={(e) => setGRecipientName(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Recipient email</Label>
                    <Input
                      type="email"
                      placeholder="name@email.com"
                      value={gRecipientEmail}
                      onChange={(e) => setGRecipientEmail(e.target.value)}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Occasion</Label>
                  <div className="grid grid-cols-3 gap-2">
                    {(Object.keys(occasionMeta) as Occasion[]).map((o) => {
                      const meta = occasionMeta[o];
                      const Icon = meta.icon;
                      const active = gOccasion === o;
                      return (
                        <button
                          key={o}
                          type="button"
                          onClick={() => setGOccasion(o)}
                          className={cn(
                            "flex flex-col items-center gap-1 rounded-lg border p-2 text-[11px] font-medium transition-colors",
                            active
                              ? "border-primary bg-primary/5 text-foreground"
                              : "border-border text-muted-foreground hover:border-primary/40"
                          )}
                        >
                          <Icon size={16} className={active ? "text-primary" : ""} />
                          {meta.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label>Asset type</Label>
                  <Select value={gAsset} onValueChange={(v) => setGAsset(v as GiftAsset)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {giftAssetOptions.map((a) => (
                        <SelectItem key={a.value} value={a.value} disabled={!a.enabled}>
                          {a.label}{a.enabled ? "" : " (not available)"}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {gAsset === "property_shares" ? (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label>Property</Label>
                      <Select value={gPropertyId} onValueChange={setGPropertyId}>
                        <SelectTrigger><SelectValue placeholder="Select a holding" /></SelectTrigger>
                        <SelectContent>
                          {holdings.filter((h) => h.sellable_units > 0).map((h) => (
                            <SelectItem key={h.property_id} value={h.property_id}>
                              {h.title ?? "Property"} · {h.sellable_units} avail.
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label>Units</Label>
                      <Input
                        type="number"
                        min={1}
                        placeholder="e.g. 5"
                        value={gUnits}
                        onChange={(e) => setGUnits(e.target.value)}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    <Label>Amount (wallet)</Label>
                    <Input
                      type="number"
                      min={0}
                      step="0.01"
                      placeholder="e.g. 1000.00"
                      value={gAmount}
                      onChange={(e) => setGAmount(e.target.value)}
                    />
                  </div>
                )}

                <div className="space-y-1.5">
                  <Label>Scheduled date</Label>
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button variant="outline" className={cn("w-full justify-start text-left font-normal", !gDate && "text-muted-foreground")}>
                        <CalendarIcon className="mr-2 h-4 w-4" />
                        {gDate ? format(gDate, "PPP") : <span>Pick a date</span>}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        mode="single"
                        selected={gDate}
                        onSelect={setGDate}
                        initialFocus
                        className={cn("p-3 pointer-events-auto")}
                      />
                    </PopoverContent>
                  </Popover>
                </div>

                <div className="flex items-center justify-between rounded-lg border border-border p-3">
                  <div className="flex items-center gap-2">
                    <Repeat size={16} className="text-primary" />
                    <div>
                      <div className="text-sm font-medium">Recurring transfer</div>
                      <div className="text-xs text-muted-foreground">Repeat every year on the same date</div>
                    </div>
                  </div>
                  <Switch checked={gRecurring} onCheckedChange={setGRecurring} />
                </div>

                <div className="space-y-1.5">
                  <Label>Personal message</Label>
                  <Textarea
                    placeholder="Write a heartfelt note for the recipient…"
                    value={gMessage}
                    onChange={(e) => setGMessage(e.target.value)}
                    rows={3}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={resetGiftForm}>Cancel</Button>
                <Button onClick={scheduleGift} disabled={scheduleMutation.isPending} className="gap-2">
                  <Send size={14} /> Schedule
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

        {/* Scheduled gifts (real, from the API — no fabricated cards) */}
        {gifts.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="py-10 flex flex-col items-center text-center gap-2">
              <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
                <Gift className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground max-w-md">
                No scheduled gifts yet. Schedule one above — it reserves the units (or escrows the
                cash) now and executes automatically on the date you choose.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid md:grid-cols-2 gap-4">
            {gifts.map((g) => {
              const occ = (g.occasion && occasionMeta[g.occasion as Occasion]) || occasionMeta.special;
              const Icon = occ.icon;
              const st = giftStatusMeta[g.status] ?? { label: g.status, variant: "secondary" as const };
              const value =
                g.asset_type === "wallet"
                  ? `$${g.amount}`
                  : `${g.units} units`;
              return (
                <Card key={g.id} className="overflow-hidden">
                  <div className={cn("h-1 bg-gradient-to-r", occ.color)} />
                  <CardContent className="p-5 space-y-3">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "w-11 h-11 rounded-xl flex items-center justify-center text-white bg-gradient-to-br",
                          occ.color
                        )}>
                          <Icon size={20} />
                        </div>
                        <div>
                          <div className="text-sm font-semibold">{occ.label} · {g.recipient_name}</div>
                          <div className="text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5">
                            <CalendarIcon size={11} />
                            {format(new Date(g.scheduled_for), "PPP")}
                            {g.recurring && (
                              <Badge variant="secondary" className="text-[9px] gap-1 ml-1">
                                <Repeat size={9} /> Yearly
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                      <Badge variant={st.variant} className="text-[10px]">{st.label}</Badge>
                    </div>

                    <div className="rounded-lg bg-secondary/40 p-3 text-sm">
                      <div className="text-xs text-muted-foreground">{giftAssetLabel(g.asset_type)}</div>
                      <div className="font-semibold text-foreground">{value}</div>
                    </div>

                    {g.message && (
                      <p className="text-xs text-muted-foreground italic border-l-2 border-border pl-2">
                        "{g.message}"
                      </p>
                    )}

                    {g.status === "failed" && g.failure_reason && (
                      <p className="text-xs text-destructive">{g.failure_reason}</p>
                    )}

                    {g.status === "scheduled" && (
                      <div className="flex justify-end gap-2 pt-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-destructive hover:text-destructive"
                          disabled={cancelMutation.isPending}
                          onClick={() => cancelMutation.mutate(g.id)}
                        >
                          Cancel
                        </Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}

        {/* Reminders strip — now true: a server cron sends this reminder 7 days ahead. */}
        <Card className="bg-gradient-to-br from-primary/5 to-accent/10 border-primary/20">
          <CardContent className="p-5 flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-primary/15 text-primary flex items-center justify-center">
              <CalendarIcon size={18} />
            </div>
            <div>
              <div className="text-sm font-semibold">Upcoming family event reminders</div>
              <div className="text-xs text-muted-foreground">
                We'll notify you 7 days before each scheduled gift so you can confirm or cancel the transfer.
              </div>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
};

export default FamilyBeneficiaryGifting;
