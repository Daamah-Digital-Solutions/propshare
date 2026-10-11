import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import {
  Users,
  UserPlus,
  ArrowRightLeft,
  TrendingUp,
  Gift,
  Shield,
  Coins,
  RefreshCcw,
  Check,
  AlertCircle,
  Crown,
  Heart,
  Baby,
  User,
  History,
} from "lucide-react";
import { ApiError, familyApi, holdingsApi, type FamilyMember } from "@/lib/api";
import { BeneficiaryRegister } from "./BeneficiaryRegister";
import { FamilyActivity } from "./FamilyActivity";
import { FamilyGifting } from "./FamilyBeneficiaryGifting";
import { FamilyMemberDetail } from "./FamilyMemberDetail";
import { ConfirmAddressNotice } from "@/components/account/ConfirmAddressNotice";

const EMPTY_MEMBER = {
  name: "",
  email: "",
  relationship: "",
  date_of_birth: "",
  phone: "",
  national_id: "",
  nationality: "",
  address: "",
};

const relationshipIcon = (relationship: string) => {
  if (/owner|self/i.test(relationship)) return <Crown className="h-4 w-4 text-amber-500" />;
  if (/spouse/i.test(relationship)) return <Heart className="h-4 w-4 text-rose-500" />;
  if (/son|daughter|child/i.test(relationship)) return <Baby className="h-4 w-4 text-blue-500" />;
  return <User className="h-4 w-4 text-muted-foreground" />;
};

const memberUnits = (m: FamilyMember) => m.real_units + m.pending_units;

const day = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }) : "";

export const FamilyInvestment = () => {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  const [allocOpen, setAllocOpen] = useState(false);
  const [reinvestOpen, setReinvestOpen] = useState(false);
  const [newMember, setNewMember] = useState(EMPTY_MEMBER);
  const [detailMember, setDetailMember] = useState<FamilyMember | null>(null);
  const [transfer, setTransfer] = useState({ to: "", property: "", units: "" });
  const [alloc, setAlloc] = useState({ memberId: "", amount: "" });
  const [reinvest, setReinvest] = useState({ property: "", amount: "" });

  const { data: group } = useQuery({ queryKey: ["family", "group"], queryFn: () => familyApi.getGroup() });
  const { data: transfersData } = useQuery({ queryKey: ["family", "transfers"], queryFn: () => familyApi.listTransfers() });
  const { data: settings } = useQuery({ queryKey: ["family", "settings"], queryFn: () => familyApi.settings() });
  const { data: holdings } = useQuery({ queryKey: ["secondary", "holdings"], queryFn: () => holdingsApi.mine() });

  const members = useMemo(() => group?.members ?? [], [group]);
  const totalUnits = members.reduce((s, m) => s + memberUnits(m), 0);
  const totalReturns = Number(group?.total_returns ?? 0);
  const discountPct = settings ? Number(settings.reinvest_discount_pct) : 7.5;
  const transferFeePct = Number(settings?.transfer_fee_pct ?? 0);
  const ownerProperties = holdings?.items ?? [];
  // A transfer moves the caller's own units: the sender is always their own row.
  const self = members.find((m) => m.is_self) ?? members.find((m) => /self|owner/i.test(m.relationship));

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["family"] });
    qc.invalidateQueries({ queryKey: ["secondary", "holdings"] });
    qc.invalidateQueries({ queryKey: ["holdings"] });
    qc.invalidateQueries({ queryKey: ["unit-movements"] });
    qc.invalidateQueries({ queryKey: ["notifications"] });
    qc.invalidateQueries({ queryKey: ["wallet"] });
  };
  const onErr = (err: unknown, title: string) =>
    toast({ title, description: err instanceof ApiError ? err.message : "Something went wrong", variant: "destructive" });

  const createGroup = useMutation({
    mutationFn: () => familyApi.createGroup("My Family"),
    onSuccess: () => { toast({ title: "Family group created" }); invalidate(); },
    onError: (e) => onErr(e, "Could not create group"),
  });

  const addMember = useMutation({
    mutationFn: () => familyApi.addMember({
      name: newMember.name,
      email: newMember.email || undefined,
      relationship: newMember.relationship,
      date_of_birth: newMember.date_of_birth || null,
      phone: newMember.phone || null,
      national_id: newMember.national_id || null,
      nationality: newMember.nationality || null,
      address: newMember.address || null,
    }),
    onSuccess: (m) => {
      toast({
        title: "Family member added",
        description: m.is_verified
          ? "Linked to their verified account. They were told by notification and email."
          : m.email
            ? "Invited by email — allocations stay pending until they verify."
            : "Added — give them an email so they can register and receive allocations.",
      });
      setNewMember(EMPTY_MEMBER);
      setAddOpen(false);
      invalidate();
    },
    onError: (e) => onErr(e, "Could not add member"),
  });

  const doTransfer = useMutation({
    mutationFn: () => familyApi.transfer({
      from_member_id: self?.member_id ?? "",
      to_member_id: transfer.to,
      property_id: transfer.property,
      units: parseInt(transfer.units),
    }, crypto.randomUUID()),
    onSuccess: (t) => {
      toast({
        title: t.status === "completed" ? "Units transferred" : "Allocation pending",
        description: t.status === "completed"
          ? `${t.units} units moved. You were both told by notification and email.`
          : `${t.units} units reserved until the member verifies. They were told by email.`,
      });
      setTransfer({ to: "", property: "", units: "" });
      setTransferOpen(false);
      invalidate();
    },
    onError: (e) => onErr(e, "Transfer failed"),
  });

  const doAllocate = useMutation({
    mutationFn: () => familyApi.allocateReturns({ member_id: alloc.memberId, amount: parseFloat(alloc.amount) }, crypto.randomUUID()),
    onSuccess: (r) => {
      toast({
        title: "Returns allocated",
        description: r.real
          ? "Sent to their wallet. You were both told by notification and email."
          : "Recorded: it moves to their wallet once they verify. They were told by email.",
      });
      setAlloc({ memberId: "", amount: "" });
      setAllocOpen(false);
      invalidate();
    },
    onError: (e) => onErr(e, "Allocation failed"),
  });

  const doReinvest = useMutation({
    mutationFn: () => familyApi.reinvest({ property_id: reinvest.property, amount: parseFloat(reinvest.amount) }, crypto.randomUUID()),
    onSuccess: (r) => { toast({ title: "Reinvested at family discount", description: `${r.units} units at $${r.effective_price}/unit (${discountPct}% off).` }); setReinvest({ property: "", amount: "" }); setReinvestOpen(false); invalidate(); },
    onError: (e) => onErr(e, "Reinvest failed"),
  });

  // what a relative allocated to this member's address reaches the account only once the
  // address is confirmed: said here, where they would look for it
  const addressNotice = (
    <ConfirmAddressNotice>
      Units or returns a family member allocated to your email address reach this account only once
      that address is confirmed. If the link we emailed when you signed up has expired, ask for a new
      one.
    </ConfirmAddressNotice>
  );

  // No group yet → offer to create one (the owner becomes the Self member). A member who was
  // added to someone else's group has none of their own: what came to them is listed below.
  if (group === null) {
    return (
      <div className="space-y-6">
        {addressNotice}
        <Card className="bg-gradient-to-br from-primary/10 to-accent/5 border-primary/20">
          <CardContent className="py-12 text-center space-y-4">
            <div className="h-14 w-14 rounded-full bg-primary/15 flex items-center justify-center mx-auto">
              <Users className="h-7 w-7 text-primary" />
            </div>
            <div>
              <h3 className="text-lg font-semibold">Start your Family Group</h3>
              <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
                Co-invest with family — allocate and transfer real ownership units, and reinvest together at a {discountPct}% family discount.
              </p>
            </div>
            <Button onClick={() => createGroup.mutate()} disabled={createGroup.isPending}>
              <UserPlus className="h-4 w-4 mr-2" /> Create Family Group
            </Button>
          </CardContent>
        </Card>
        <FamilyActivity hideWhenEmpty />
      </div>
    );
  }

  const recipients = members.filter((m) => m.member_id !== self?.member_id);

  return (
    <div className="space-y-6">
      {addressNotice}
      {/* Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-gradient-to-br from-primary/10 to-primary/5 border-primary/20">
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium flex items-center gap-2"><Users className="h-4 w-4 text-primary" />Family Members</CardTitle></CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{members.length}</div>
            <p className="text-xs text-muted-foreground">{members.filter((m) => m.is_verified).length} verified</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-emerald-500/10 to-emerald-500/5 border-emerald-500/20">
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium flex items-center gap-2"><Coins className="h-4 w-4 text-emerald-600" />Total Family Units</CardTitle></CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalUnits}</div>
            <p className="text-xs text-muted-foreground">Yours, and those you transferred or allocated</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-amber-500/10 to-amber-500/5 border-amber-500/20">
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium flex items-center gap-2"><TrendingUp className="h-4 w-4 text-amber-600" />Family Returns</CardTitle></CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">${totalReturns.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">Allocated across members</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-purple-500/10 to-purple-500/5 border-purple-500/20">
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium flex items-center gap-2"><Gift className="h-4 w-4 text-purple-600" />Family Discount</CardTitle></CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{discountPct}%</div>
            <p className="text-xs text-muted-foreground">On family reinvestment</p>
          </CardContent>
        </Card>
      </div>

      {/* Benefits banner */}
      <Card className="bg-gradient-to-r from-primary/20 via-primary/10 to-accent/10 border-primary/30">
        <CardContent className="py-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-full bg-primary/20 flex items-center justify-center"><Shield className="h-6 w-6 text-primary" /></div>
              <div>
                <h3 className="font-semibold">Family Investment Benefits</h3>
                <p className="text-sm text-muted-foreground">
                  {transferFeePct === 0 ? "Zero transfer fees" : `${transferFeePct}% transfer fee`} • {discountPct}% family reinvest discount • Real on-ledger ownership
                </p>
              </div>
            </div>
            <Button onClick={() => setReinvestOpen(true)}><RefreshCcw className="h-4 w-4 mr-2" />Reinvest at {discountPct}% Discount</Button>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="members" className="space-y-4">
        <TabsList className="flex flex-wrap gap-2 w-full h-auto">
          <TabsTrigger value="members" className="flex items-center gap-2"><Users className="h-4 w-4" />Members</TabsTrigger>
          <TabsTrigger value="transfers" className="flex items-center gap-2"><ArrowRightLeft className="h-4 w-4" />Transfers</TabsTrigger>
          <TabsTrigger value="allocations" className="flex items-center gap-2"><TrendingUp className="h-4 w-4" />Allocations</TabsTrigger>
          <TabsTrigger value="activity" className="flex items-center gap-2"><History className="h-4 w-4" />Activity</TabsTrigger>
          <TabsTrigger value="estate" className="flex items-center gap-2"><Shield className="h-4 w-4" /><span className="hidden sm:inline">Beneficiaries & Inheritance</span><span className="sm:hidden">Estate</span></TabsTrigger>
          <TabsTrigger value="gifting" className="flex items-center gap-2"><Gift className="h-4 w-4" />Gifting</TabsTrigger>
        </TabsList>

        {/* Members */}
        <TabsContent value="members" className="space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">Family Members</h3>
            <Dialog open={addOpen} onOpenChange={setAddOpen}>
              <DialogTrigger asChild><Button size="sm"><UserPlus className="h-4 w-4 mr-2" />Add Member</Button></DialogTrigger>
              <DialogContent className="max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle>Add Family Member</DialogTitle><DialogDescription>If their email matches a verified account they link immediately; otherwise they're invited and allocations stay pending. Either way they are told by email.</DialogDescription></DialogHeader>
                <div className="space-y-4 py-4">
                  <div className="space-y-2"><Label>Full Name</Label><Input value={newMember.name} onChange={(e) => setNewMember({ ...newMember, name: e.target.value })} placeholder="Enter full name" /></div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2"><Label>Relationship</Label>
                      <Select value={newMember.relationship} onValueChange={(v) => setNewMember({ ...newMember, relationship: v })}>
                        <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                        <SelectContent>{["Spouse", "Son", "Daughter", "Parent", "Sibling", "Other"].map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2"><Label>Date of Birth</Label><Input type="date" value={newMember.date_of_birth} onChange={(e) => setNewMember({ ...newMember, date_of_birth: e.target.value })} /></div>
                  </div>
                  <div className="space-y-2"><Label>Email Address</Label><Input type="email" value={newMember.email} onChange={(e) => setNewMember({ ...newMember, email: e.target.value })} placeholder="Enter email (links to their account)" /></div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2"><Label>Phone</Label><Input value={newMember.phone} onChange={(e) => setNewMember({ ...newMember, phone: e.target.value })} placeholder="Phone number" /></div>
                    <div className="space-y-2"><Label>Nationality</Label><Input value={newMember.nationality} onChange={(e) => setNewMember({ ...newMember, nationality: e.target.value })} placeholder="Nationality" /></div>
                  </div>
                  <div className="space-y-2"><Label>National ID / Passport</Label><Input value={newMember.national_id} onChange={(e) => setNewMember({ ...newMember, national_id: e.target.value })} placeholder="ID or passport number" /></div>
                  <div className="space-y-2"><Label>Address</Label><Input value={newMember.address} onChange={(e) => setNewMember({ ...newMember, address: e.target.value })} placeholder="Residential address" /></div>
                  <p className="text-xs text-muted-foreground">You can add the member's bank account(s) after creating them — open the member to manage details.</p>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setAddOpen(false)}>Cancel</Button>
                  <Button onClick={() => addMember.mutate()} disabled={!newMember.name || !newMember.relationship || addMember.isPending}>Add Member</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>

          <div className="grid gap-4">
            {members.map((m) => (
              <Card key={m.member_id} className="hover:shadow-md transition-shadow cursor-pointer" onClick={() => setDetailMember(m)}>
                <CardContent className="py-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="flex items-center gap-4">
                      <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">{relationshipIcon(m.relationship)}</div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="font-semibold">{m.name}</h4>
                          {m.is_verified ? (
                            <Badge variant="outline" className="bg-emerald-500/10 text-emerald-600 border-emerald-500/30"><Check className="h-3 w-3 mr-1" />Verified</Badge>
                          ) : (
                            <Badge variant="outline" className="bg-amber-500/10 text-amber-600 border-amber-500/30"><AlertCircle className="h-3 w-3 mr-1" />Pending</Badge>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground">{m.relationship}{m.email ? ` • ${m.email}` : ""}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-6 text-right">
                      <div><p className="text-sm text-muted-foreground">Units</p><p className="font-semibold">{memberUnits(m)}{m.pending_units > 0 && <span className="text-xs text-amber-600"> ({m.pending_units} pending)</span>}</p></div>
                      <div><p className="text-sm text-muted-foreground">Returns</p><p className="font-semibold text-emerald-600">${Number(m.allocated_returns).toLocaleString()}</p></div>
                      <div className="w-20"><Progress value={totalUnits ? (memberUnits(m) / totalUnits) * 100 : 0} className="h-2" /><p className="text-xs text-muted-foreground mt-1">{totalUnits ? ((memberUnits(m) / totalUnits) * 100).toFixed(1) : "0"}%</p></div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        {/* Transfers */}
        <TabsContent value="transfers" className="space-y-4">
          <div className="flex justify-between items-center">
            <div><h3 className="text-lg font-semibold">Unit Transfers</h3><p className="text-sm text-muted-foreground">Move your own ownership units to a family member</p></div>
            <Dialog open={transferOpen} onOpenChange={setTransferOpen}>
              <DialogTrigger asChild><Button size="sm"><ArrowRightLeft className="h-4 w-4 mr-2" />New Transfer</Button></DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>Transfer Units</DialogTitle><DialogDescription>The units leave your own holding. They move at once when the recipient is verified; otherwise they are held for them until they verify. You are both told by notification and email.</DialogDescription></DialogHeader>
                <div className="space-y-4 py-4">
                  <div className="space-y-2"><Label>From</Label>
                    <div className="rounded-md border border-input bg-muted/40 px-3 py-2 text-sm" data-testid="transfer-from">
                      You{self ? ` (${self.real_units} units)` : ""}
                    </div>
                  </div>
                  <div className="space-y-2"><Label>To Member</Label>
                    <Select value={transfer.to} onValueChange={(v) => setTransfer({ ...transfer, to: v })}>
                      <SelectTrigger><SelectValue placeholder="Select recipient" /></SelectTrigger>
                      <SelectContent>
                        {recipients.length === 0 ? (
                          <div className="px-3 py-2 text-sm text-muted-foreground">Add a family member first.</div>
                        ) : recipients.map((m) => <SelectItem key={m.member_id} value={m.member_id}>{m.name}{m.is_verified ? "" : " (pending)"}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2"><Label>Property</Label>
                    <Select value={transfer.property} onValueChange={(v) => setTransfer({ ...transfer, property: v })}>
                      <SelectTrigger><SelectValue placeholder="Select property" /></SelectTrigger>
                      <SelectContent>
                        {ownerProperties.length === 0 ? (
                          <div className="px-3 py-2 text-sm text-muted-foreground">You hold no units yet.</div>
                        ) : ownerProperties.map((h) => <SelectItem key={h.property_id} value={h.property_id}>{h.title} ({h.units} units)</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2"><Label>Units to Transfer</Label><Input type="number" min={1} value={transfer.units} onChange={(e) => setTransfer({ ...transfer, units: e.target.value })} placeholder="Enter units" /></div>
                  <Card className="bg-emerald-500/10 border-emerald-500/30"><CardContent className="py-3"><div className="flex items-center gap-2 text-emerald-600"><Gift className="h-4 w-4" /><span className="text-sm font-medium">Transfer Fee: {transferFeePct}%</span></div></CardContent></Card>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setTransferOpen(false)}>Cancel</Button>
                  <Button onClick={() => doTransfer.mutate()} disabled={!self || !transfer.to || !transfer.property || !transfer.units || doTransfer.isPending}>Complete Transfer</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>

          <Card>
            <CardHeader><CardTitle className="text-base">Transfer History</CardTitle></CardHeader>
            <CardContent>
              {(transfersData?.items ?? []).length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">No transfers yet.</div>
              ) : (
                <div className="space-y-3">
                  {(transfersData?.items ?? []).map((t) => {
                    const name = (id: string | null) => members.find((m) => m.member_id === id)?.name ?? "—";
                    const fee = Number(t.transfer_fee);
                    return (
                      <div key={t.transfer_id} className="flex items-center justify-between gap-3 py-3 border-b border-border last:border-0" data-testid="transfer-row">
                        <div className="flex items-center gap-4 min-w-0">
                          <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0"><ArrowRightLeft className="h-5 w-5 text-primary" /></div>
                          <div className="min-w-0">
                            <p className="font-medium">{t.from_name ?? name(t.from_member_id)} → {t.to_name ?? name(t.to_member_id)}</p>
                            <p className="text-sm text-muted-foreground">
                              {t.units} unit{t.units === 1 ? "" : "s"}{t.property_title ? ` of ${t.property_title}` : ""}
                              {fee > 0 ? ` · fee $${fee.toLocaleString()}` : ""}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {day(t.created_at)}
                              {t.status === "completed" && t.completed_at && day(t.completed_at) !== day(t.created_at) ? ` · received ${day(t.completed_at)}` : ""}
                              {t.status === "pending" ? " · held until they verify" : ""}
                            </p>
                          </div>
                        </div>
                        <Badge variant="outline" className={t.status === "completed" ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/30" : t.status === "pending" ? "bg-amber-500/10 text-amber-600 border-amber-500/30" : "bg-muted text-muted-foreground"}>{t.status}</Badge>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Allocations */}
        <TabsContent value="allocations" className="space-y-4">
          <div className="flex justify-between items-center">
            <div><h3 className="text-lg font-semibold">Returns Allocation</h3><p className="text-sm text-muted-foreground">Allocate returns to family members, or reinvest together at the family discount</p></div>
            <div className="flex gap-2">
              <Dialog open={allocOpen} onOpenChange={setAllocOpen}>
                <DialogTrigger asChild><Button size="sm" variant="outline"><TrendingUp className="h-4 w-4 mr-2" />Allocate Returns</Button></DialogTrigger>
                <DialogContent>
                  <DialogHeader><DialogTitle>Allocate Returns</DialogTitle><DialogDescription>Move returns to a member's wallet (verified) or record the allocation (pending). You are both told by notification and email.</DialogDescription></DialogHeader>
                  <div className="space-y-4 py-4">
                    <div className="space-y-2"><Label>Member</Label>
                      <Select value={alloc.memberId} onValueChange={(v) => setAlloc({ ...alloc, memberId: v })}>
                        <SelectTrigger><SelectValue placeholder="Select member" /></SelectTrigger>
                        <SelectContent>{members.map((m) => <SelectItem key={m.member_id} value={m.member_id}>{m.name}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2"><Label>Amount ($)</Label><Input type="number" value={alloc.amount} onChange={(e) => setAlloc({ ...alloc, amount: e.target.value })} placeholder="Enter amount" /></div>
                  </div>
                  <DialogFooter><Button variant="outline" onClick={() => setAllocOpen(false)}>Cancel</Button><Button onClick={() => doAllocate.mutate()} disabled={!alloc.memberId || !alloc.amount || doAllocate.isPending}>Allocate</Button></DialogFooter>
                </DialogContent>
              </Dialog>
              <Button size="sm" onClick={() => setReinvestOpen(true)}><RefreshCcw className="h-4 w-4 mr-2" />Reinvest</Button>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-base">Family Returns Summary</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                {members.map((m) => (
                  <div key={m.member_id} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">{relationshipIcon(m.relationship)}<span className="text-sm">{m.name}</span></div>
                    <span className="text-right">
                      <span className="font-semibold text-emerald-600">${Number(m.allocated_returns).toLocaleString()}</span>
                      {Number(m.pending_returns ?? 0) > 0 && (
                        <span className="block text-[11px] text-amber-600">
                          ${Number(m.pending_returns).toLocaleString()} held until they verify
                        </span>
                      )}
                    </span>
                  </div>
                ))}
                <div className="border-t border-border pt-4 flex items-center justify-between"><span className="font-medium">Total Family Returns</span><span className="font-bold text-lg text-emerald-600">${totalReturns.toLocaleString()}</span></div>
              </CardContent>
            </Card>
            <Card className="bg-gradient-to-br from-primary/10 to-accent/5">
              <CardHeader><CardTitle className="text-base flex items-center gap-2"><Gift className="h-5 w-5 text-primary" />Family Reinvest Discount</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">Reinvest family returns and buy units at an effective price of unit price × (1 − {discountPct}%).</p>
                <div className="flex items-center justify-between py-2"><span className="font-medium">Family Discount</span><Badge className="bg-emerald-500 text-white">{discountPct}%</Badge></div>
                <Button onClick={() => setReinvestOpen(true)} className="w-full mt-2"><RefreshCcw className="h-4 w-4 mr-2" />Reinvest at Discount</Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Activity — everything done with this member, on either side (client, 2026-10-07) */}
        <TabsContent value="activity" className="space-y-4">
          <FamilyActivity />
        </TabsContent>

        {/* Estate / Beneficiaries — Capimax's OWN feature (not BRX): the beneficiary register,
            each person's identity document and certificate. */}
        <TabsContent value="estate" className="space-y-4">
          <BeneficiaryRegister />
        </TabsContent>
        {/* Scheduled and recurring gifts (real: a server job executes them on their date) */}
        <TabsContent value="gifting" className="space-y-4">
          <FamilyGifting />
        </TabsContent>
      </Tabs>

      {/* Reinvest dialog (shared by banner + allocations) */}
      <Dialog open={reinvestOpen} onOpenChange={setReinvestOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Reinvest at the Family Discount</DialogTitle><DialogDescription>Buy units at an effective price of unit price × (1 − {discountPct}%), funded from your wallet.</DialogDescription></DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2"><Label>Property</Label>
              <Select value={reinvest.property} onValueChange={(v) => setReinvest({ ...reinvest, property: v })}>
                <SelectTrigger><SelectValue placeholder="Select property" /></SelectTrigger>
                <SelectContent>{ownerProperties.map((h) => <SelectItem key={h.property_id} value={h.property_id}>{h.title}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2"><Label>Amount ($)</Label><Input type="number" value={reinvest.amount} onChange={(e) => setReinvest({ ...reinvest, amount: e.target.value })} placeholder="Enter amount" /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setReinvestOpen(false)}>Cancel</Button><Button onClick={() => doReinvest.mutate()} disabled={!reinvest.property || !reinvest.amount || doReinvest.isPending}>Reinvest</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <FamilyMemberDetail
        member={detailMember}
        open={!!detailMember}
        onOpenChange={(o) => { if (!o) setDetailMember(null); }}
        onChanged={invalidate}
      />
    </div>
  );
};
