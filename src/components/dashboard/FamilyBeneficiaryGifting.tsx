import { useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
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
  Users,
  Gift,
  Calendar as CalendarIcon,
  Repeat,
  Sparkles,
  Heart,
  GraduationCap,
  Cake,
  Trophy,
  PartyPopper,
  Plus,
  Lock,
  Clock,
  AlertCircle,
  Pencil,
  Trash2,
  CheckCircle2,
  Send,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { useToast } from "@/hooks/use-toast";

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

const initialBeneficiaries: Beneficiary[] = [
  {
    id: "b1",
    fullName: "Fatima Al-Hassan",
    relationship: "Spouse",
    role: "heir",
    email: "fatima@email.com",
    phone: "+971 50 000 0001",
    idType: "Passport",
    idNumber: "P-A1928374",
    allocationPct: 50,
    notes: "Primary heir for all real estate ownership and rental income.",
    trigger: "death",
    scope: ["ownership", "rental_returns", "passive_income", "portfolio"],
    status: "active",
  },
  {
    id: "b2",
    fullName: "Omar Al-Hassan",
    relationship: "Son",
    role: "beneficiary",
    email: "omar@email.com",
    phone: "+971 50 000 0002",
    idType: "National ID",
    idNumber: "ID-7748321",
    allocationPct: 25,
    notes: "Receives passive income share once turning 21.",
    trigger: "death",
    scope: ["passive_income", "wallet"],
    status: "active",
  },
  {
    id: "b3",
    fullName: "Karim Lawyers LLC",
    relationship: "Family Counsel",
    role: "legal",
    email: "trust@karim-law.ae",
    phone: "+971 4 222 3344",
    idType: "Trade License",
    idNumber: "TL-99812",
    allocationPct: 0,
    notes: "Legal representative coordinating estate execution.",
    trigger: "authorized",
    scope: ["portfolio"],
    status: "active",
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Gifting types
// ─────────────────────────────────────────────────────────────────────────────

type GiftAsset = "property_shares" | "tokenized" | "passive_income" | "rental_returns" | "wallet" | "allocation";
type Occasion = "birthday" | "graduation" | "wedding" | "celebration" | "achievement" | "special";

interface Gift {
  id: string;
  recipient: string;
  occasion: Occasion;
  asset: GiftAsset;
  amount: string;
  scheduledFor: string;
  recurring: boolean;
  message: string;
  status: "scheduled" | "delivered";
}

const occasionMeta: Record<Occasion, { label: string; icon: typeof Gift; color: string }> = {
  birthday: { label: "Birthday", icon: Cake, color: "from-pink-500 to-rose-500" },
  graduation: { label: "Graduation", icon: GraduationCap, color: "from-indigo-500 to-blue-500" },
  wedding: { label: "Marriage", icon: Heart, color: "from-rose-500 to-red-500" },
  celebration: { label: "Family Celebration", icon: PartyPopper, color: "from-amber-500 to-orange-500" },
  achievement: { label: "Achievement Milestone", icon: Trophy, color: "from-emerald-500 to-teal-500" },
  special: { label: "Special Event", icon: Sparkles, color: "from-purple-500 to-fuchsia-500" },
};

const assetMeta: Record<GiftAsset, string> = {
  property_shares: "Property Shares",
  tokenized: "Tokenized Ownership",
  passive_income: "Passive Income",
  rental_returns: "Rental Returns",
  wallet: "Wallet Balance",
  allocation: "Asset Allocation",
};

const familyChoices = ["Fatima Al-Hassan", "Omar Al-Hassan", "Layla Al-Hassan"];

const initialGifts: Gift[] = [
  {
    id: "g1",
    recipient: "Layla Al-Hassan",
    occasion: "birthday",
    asset: "property_shares",
    amount: "5 units · Marina Heights",
    scheduledFor: "2026-06-12",
    recurring: true,
    message: "Happy Birthday Layla — a small step toward your future portfolio. ❤️",
    status: "scheduled",
  },
  {
    id: "g2",
    recipient: "Omar Al-Hassan",
    occasion: "graduation",
    asset: "wallet",
    amount: "$2,500",
    scheduledFor: "2026-07-01",
    recurring: false,
    message: "Congratulations on your graduation, son.",
    status: "scheduled",
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const FamilyBeneficiaryGifting = () => {
  const { toast } = useToast();
  const [beneficiaries, setBeneficiaries] = useState<Beneficiary[]>(initialBeneficiaries);
  const [gifts, setGifts] = useState<Gift[]>(initialGifts);

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
    setBeneficiaries((prev) => [
      ...prev,
      { ...bForm, id: `b${Date.now()}`, status: "pending" },
    ]);
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
    toast({ title: "Beneficiary added", description: "Awaiting verification & legal acknowledgement." });
  };

  const removeBeneficiary = (id: string) =>
    setBeneficiaries((prev) => prev.filter((b) => b.id !== id));

  // ── Schedule gift form ───────────────────────────────────────────────────
  const [gOpen, setGOpen] = useState(false);
  const [gRecipient, setGRecipient] = useState("");
  const [gOccasion, setGOccasion] = useState<Occasion>("birthday");
  const [gAsset, setGAsset] = useState<GiftAsset>("property_shares");
  const [gAmount, setGAmount] = useState("");
  const [gDate, setGDate] = useState<Date | undefined>(undefined);
  const [gRecurring, setGRecurring] = useState(false);
  const [gMessage, setGMessage] = useState("");

  const scheduleGift = () => {
    if (!gRecipient || !gAmount || !gDate) {
      toast({ title: "Missing info", description: "Recipient, asset and date are required.", variant: "destructive" });
      return;
    }
    setGifts((prev) => [
      ...prev,
      {
        id: `g${Date.now()}`,
        recipient: gRecipient,
        occasion: gOccasion,
        asset: gAsset,
        amount: gAmount,
        scheduledFor: format(gDate, "yyyy-MM-dd"),
        recurring: gRecurring,
        message: gMessage,
        status: "scheduled",
      },
    ]);
    setGOpen(false);
    setGRecipient("");
    setGAmount("");
    setGDate(undefined);
    setGRecurring(false);
    setGMessage("");
    toast({ title: "Gift scheduled", description: "The transfer will execute automatically on the chosen date." });
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
      {/* GIFTING                                                              */}
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
              Transfer property shares, tokenized ownership, passive income or wallet balances to family members on
              special occasions — scheduled and executed automatically.
            </p>
          </div>

          <Dialog open={gOpen} onOpenChange={setGOpen}>
            <DialogTrigger asChild>
              <Button size="lg" className="gap-2">
                <Plus size={18} /> Schedule Gift
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Schedule a Gift</DialogTitle>
                <DialogDescription>
                  Choose recipient, asset and date — we'll deliver it automatically.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label>Recipient</Label>
                  <Select value={gRecipient} onValueChange={setGRecipient}>
                    <SelectTrigger><SelectValue placeholder="Select family member" /></SelectTrigger>
                    <SelectContent>
                      {familyChoices.map((m) => (
                        <SelectItem key={m} value={m}>{m}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
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

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>Asset type</Label>
                    <Select value={gAsset} onValueChange={(v) => setGAsset(v as GiftAsset)}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {(Object.keys(assetMeta) as GiftAsset[]).map((a) => (
                          <SelectItem key={a} value={a}>{assetMeta[a]}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Amount / units</Label>
                    <Input
                      placeholder="e.g. 5 units · $1,000"
                      value={gAmount}
                      onChange={(e) => setGAmount(e.target.value)}
                    />
                  </div>
                </div>

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
                <Button variant="outline" onClick={() => setGOpen(false)}>Cancel</Button>
                <Button onClick={scheduleGift} className="gap-2"><Send size={14} /> Schedule</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

        {/* Scheduled gifts */}
        <div className="grid md:grid-cols-2 gap-4">
          {gifts.map((g) => {
            const meta = occasionMeta[g.occasion];
            const Icon = meta.icon;
            return (
              <Card key={g.id} className="overflow-hidden">
                <div className={cn("h-1 bg-gradient-to-r", meta.color)} />
                <CardContent className="p-5 space-y-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className={cn(
                        "w-11 h-11 rounded-xl flex items-center justify-center text-white bg-gradient-to-br",
                        meta.color
                      )}>
                        <Icon size={20} />
                      </div>
                      <div>
                        <div className="text-sm font-semibold">{meta.label} · {g.recipient}</div>
                        <div className="text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5">
                          <CalendarIcon size={11} />
                          {format(new Date(g.scheduledFor), "PPP")}
                          {g.recurring && (
                            <Badge variant="secondary" className="text-[9px] gap-1 ml-1">
                              <Repeat size={9} /> Yearly
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                    <Badge variant={g.status === "delivered" ? "default" : "secondary"} className="text-[10px]">
                      {g.status === "delivered" ? "Delivered" : "Scheduled"}
                    </Badge>
                  </div>

                  <div className="rounded-lg bg-secondary/40 p-3 text-sm">
                    <div className="text-xs text-muted-foreground">{assetMeta[g.asset]}</div>
                    <div className="font-semibold text-foreground">{g.amount}</div>
                  </div>

                  {g.message && (
                    <p className="text-xs text-muted-foreground italic border-l-2 border-border pl-2">
                      "{g.message}"
                    </p>
                  )}

                  <div className="flex justify-end gap-2 pt-1">
                    <Button size="sm" variant="ghost">Edit</Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setGifts((p) => p.filter((x) => x.id !== g.id))}
                    >
                      Cancel
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Reminders strip */}
        <Card className="bg-gradient-to-br from-primary/5 to-accent/10 border-primary/20">
          <CardContent className="p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-primary/15 text-primary flex items-center justify-center">
                <CalendarIcon size={18} />
              </div>
              <div>
                <div className="text-sm font-semibold">Upcoming family event reminders</div>
                <div className="text-xs text-muted-foreground">
                  We'll notify you 7 days before each scheduled gift to confirm or adjust the transfer.
                </div>
              </div>
            </div>
            <Button variant="outline" size="sm">Manage Reminders</Button>
          </CardContent>
        </Card>
      </section>
    </div>
  );
};

export default FamilyBeneficiaryGifting;
