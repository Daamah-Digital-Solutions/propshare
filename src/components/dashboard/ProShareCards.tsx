import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  CreditCard,
  Plus,
  Eye,
  EyeOff,
  Snowflake,
  Wallet,
  TrendingUp,
  ArrowUpRight,
  ArrowDownLeft,
  Landmark,
  Plane,
  Coffee,
  ShoppingBag,
  Building2,
  Sparkles,
} from "lucide-react";

/**
 * ProShare Cards — a DESIGN PREVIEW of the upcoming real-estate spending cards (owner-requested
 * for prestige). Intentionally NOT wired to any backend: the figures below are clearly-labelled
 * sample data, no card is issued, and every control is inert. When the feature ships, this same
 * layout gets wired to real card/wallet data. (DELETE NOTHING — replaces the old placeholder.)
 */

const CARDS = [
  {
    id: "primary",
    label: "Primary Card",
    tone: "green",
    last4: "4827",
    holder: "Ahmed Al-Mansour",
    available: 12450,
    spent: 2340,
    limit: 8000,
    tagLeft: "Personal",
    tagRight: "Main Wallet",
    frozen: false,
  },
  {
    id: "family",
    label: "Family · Sara",
    tone: "gold",
    last4: "1093",
    holder: "Sara Al-Mansour",
    available: 1800,
    spent: 620,
    limit: 1500,
    tagLeft: "Family Member",
    tagRight: "Family Allocation",
    frozen: false,
  },
  {
    id: "team",
    label: "Team · Operations",
    tone: "dark",
    last4: "7745",
    holder: "Operations Lead",
    available: 5200,
    spent: 980,
    limit: 3000,
    tagLeft: "Team Member",
    tagRight: "Sub Wallet · Ops",
    frozen: true,
  },
];

const TX = [
  { icon: Plane, name: "Emirates Airlines", meta: "Travel · •••• 4827 · Today", amount: -842 },
  { icon: Building2, name: "Rental Income · Marina Tower", meta: "Inflow · •••• 4827 · Today", amount: 1250 },
  { icon: ShoppingBag, name: "Whole Foods", meta: "Groceries · •••• 1093 · Yesterday", amount: -184 },
  { icon: Landmark, name: "Distribution · Downtown SPV", meta: "Inflow · •••• 1093 · 2d ago", amount: 320 },
  { icon: Coffee, name: "Starbucks", meta: "F&B · •••• 4827 · 2d ago", amount: -28 },
];

const STATS = [
  { label: "Total Available", value: "$19,450", icon: Wallet, tone: "text-foreground" },
  { label: "Spent This Month", value: "$3,940", icon: ArrowUpRight, tone: "text-foreground" },
  { label: "Active Cards", value: "2 / 3", icon: CreditCard, tone: "text-foreground" },
  { label: "Monthly Inflow", value: "+$1,570", icon: TrendingUp, tone: "text-emerald-600" },
];

const usd = (n: number) => `$${Math.abs(n).toLocaleString()}`;

const toneClasses: Record<string, string> = {
  green: "bg-gradient-to-br from-[#198653] to-[#0d5233] text-white",
  gold: "bg-gradient-to-br from-[#e6a52b] to-[#b4790f] text-white",
  dark: "bg-gradient-to-br from-[#2b3038] to-[#12151b] text-white",
};

export const ProShareCards = () => {
  const [showNumbers, setShowNumbers] = useState(false);
  const [selected, setSelected] = useState("primary");
  const card = CARDS.find((c) => c.id === selected) ?? CARDS[0];
  const util = Math.round((card.spent / card.limit) * 100);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Badge variant="outline" className="border-primary/30 text-primary">
              <CreditCard className="w-3 h-3 mr-1" /> CapiMax ProShare Cards
            </Badge>
            <Badge variant="outline" className="border-amber-500/30 text-amber-600">
              <Sparkles className="w-3 h-3 mr-1" /> Preview
            </Badge>
          </div>
          <h2 className="text-2xl font-bold">Your Real Estate Spending Infrastructure</h2>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Issue virtual cards linked to your wallet, rental returns, and family allocations.
          </p>
        </div>
        <Button className="gap-2" disabled>
          <Plus className="w-4 h-4" /> Issue New Card
        </Button>
      </div>

      {/* Honest preview note */}
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-2.5 text-sm text-amber-700">
        Design preview — the figures below are sample data. Card issuance and spend controls
        aren't live yet.
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {STATS.map((s) => (
          <Card key={s.label} className="bg-card border-border">
            <CardContent className="p-5">
              <div className="flex items-center gap-2 text-muted-foreground mb-1">
                <s.icon className="h-4 w-4" />
                <span className="text-xs">{s.label}</span>
              </div>
              <p className={`text-2xl font-bold ${s.tone}`}>{s.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Cards */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">Your Cards</h3>
            <button
              type="button"
              className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
              onClick={() => setShowNumbers((v) => !v)}
            >
              {showNumbers ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              {showNumbers ? "Hide numbers" : "Show numbers"}
            </button>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            {CARDS.map((c) => {
              const pct = Math.min(100, Math.round((c.spent / c.limit) * 100));
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setSelected(c.id)}
                  className={`text-left rounded-2xl p-5 shadow-md transition-all ${toneClasses[c.tone]} ${
                    selected === c.id ? "ring-2 ring-offset-2 ring-primary" : ""
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold tracking-wide opacity-90">
                      ⬡ CAPIMAX PROSHARE
                    </span>
                    {c.frozen ? (
                      <span className="text-[10px] bg-white/20 rounded-full px-2 py-0.5 flex items-center gap-1">
                        <Snowflake className="h-3 w-3" /> Frozen
                      </span>
                    ) : (
                      <CreditCard className="h-4 w-4 opacity-80" />
                    )}
                  </div>
                  <p className="mt-3 font-semibold">{c.label}</p>
                  <p className="mt-4 font-mono tracking-widest text-sm opacity-95">
                    {showNumbers ? `4711 2032 8890 ${c.last4}` : `••••  ••••  ••••  ${c.last4}`}
                  </p>
                  <div className="mt-4 flex items-end justify-between">
                    <div>
                      <p className="text-[10px] uppercase opacity-70">Holder</p>
                      <p className="text-sm font-medium">{c.holder}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-[10px] uppercase opacity-70">Available</p>
                      <p className="text-sm font-bold">{usd(c.available)}</p>
                    </div>
                  </div>
                  <div className="mt-3">
                    <div className="flex justify-between text-[10px] opacity-80 mb-1">
                      <span>Monthly Spend</span>
                      <span>
                        {usd(c.spent)} / {usd(c.limit)}
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-white/25 overflow-hidden">
                      <div className="h-full bg-white/80" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                  <div className="mt-3 flex items-center justify-between text-[10px]">
                    <span className="bg-white/20 rounded-full px-2 py-0.5">{c.tagLeft}</span>
                    <span className="opacity-70">{c.tagRight}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Card Controls */}
        <Card className="bg-card border-border h-fit">
          <CardContent className="p-5 space-y-5">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <CreditCard className="h-4 w-4 text-primary" /> Card Controls
            </h3>
            <div>
              <p className="text-xs text-muted-foreground">Selected</p>
              <p className="text-sm font-medium text-foreground">
                {card.label} · •••• {card.last4}
              </p>
              <p className="text-xs text-muted-foreground">Linked to {card.tagRight}</p>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <p className="text-sm font-medium">Card {card.frozen ? "Frozen" : "Active"}</p>
                <p className="text-xs text-muted-foreground">Tap to freeze instantly</p>
              </div>
              <Switch checked={!card.frozen} disabled />
            </div>

            <div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-muted-foreground">Monthly limit</span>
                <span className="font-semibold">{usd(card.limit)}</span>
              </div>
              <Slider value={[card.limit]} max={20000} step={500} disabled />
              <div className="mt-2">
                <div className="flex justify-between text-xs text-muted-foreground mb-1">
                  <span>Used {usd(card.spent)}</span>
                  <span>{util}% utilization</span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div className="h-full bg-primary" style={{ width: `${util}%` }} />
                </div>
              </div>
            </div>

            <div>
              <p className="text-xs text-muted-foreground mb-2">Funding sources</p>
              <div className="flex flex-wrap gap-2">
                {[
                  { icon: Wallet, label: "Wallet Balance" },
                  { icon: Building2, label: "Rental Returns" },
                  { icon: TrendingUp, label: "Passive Income" },
                ].map((f) => (
                  <span
                    key={f.label}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs text-foreground"
                  >
                    <f.icon className="h-3.5 w-3.5 text-muted-foreground" /> {f.label}
                  </span>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Activity */}
      <Tabs defaultValue="transactions">
        <TabsList>
          <TabsTrigger value="transactions">Transactions</TabsTrigger>
          <TabsTrigger value="analytics">Usage Analytics</TabsTrigger>
          <TabsTrigger value="members">Linked Members</TabsTrigger>
        </TabsList>
        <TabsContent value="transactions" className="mt-4">
          <Card className="bg-card border-border">
            <CardContent className="p-0 divide-y divide-border">
              {TX.map((t, i) => (
                <div key={i} className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={`h-9 w-9 rounded-full flex items-center justify-center ${
                        t.amount > 0 ? "bg-emerald-500/10" : "bg-muted"
                      }`}
                    >
                      <t.icon
                        className={`h-4 w-4 ${t.amount > 0 ? "text-emerald-600" : "text-muted-foreground"}`}
                      />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">{t.name}</p>
                      <p className="text-xs text-muted-foreground">{t.meta}</p>
                    </div>
                  </div>
                  <div
                    className={`flex items-center gap-1 text-sm font-semibold ${
                      t.amount > 0 ? "text-emerald-600" : "text-foreground"
                    }`}
                  >
                    {t.amount > 0 ? (
                      <ArrowDownLeft className="h-4 w-4" />
                    ) : (
                      <ArrowUpRight className="h-4 w-4" />
                    )}
                    {t.amount > 0 ? "+" : "-"}
                    {usd(t.amount)}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="analytics" className="mt-4">
          <Card className="bg-card border-border">
            <CardContent className="py-12 text-center text-sm text-muted-foreground">
              Usage analytics will appear here when ProShare Cards go live.
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="members" className="mt-4">
          <Card className="bg-card border-border">
            <CardContent className="py-12 text-center text-sm text-muted-foreground">
              Linked card members will appear here when ProShare Cards go live.
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ProShareCards;
