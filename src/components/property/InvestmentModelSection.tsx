import {
  Award,
  BadgeCheck,
  BarChart3,
  Building2,
  CalendarClock,
  FileCheck2,
  HardHat,
  Layers,
  LogOut,
  PercentCircle,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface Point {
  icon: LucideIcon;
  title: string;
  text: string;
}

/**
 * The "Investment Model" section of a property page (client letter, 2026-11-18): how a ready
 * property and a property under construction make their return, how the investment is followed
 * after purchase, how an exit is priced, and the investor's journey from identity check to
 * ownership certificate. The wording is the client's.
 */

const READY: Point[] = [
  {
    icon: PercentCircle,
    title: "Where the return comes from",
    text: "The total return is made of the net annual rental yield and the growth in the property's market value.",
  },
  {
    icon: Wallet,
    title: "Rent paid monthly",
    text: "Your share of the net rent is paid into your wallet on the platform every month.",
  },
  {
    icon: RefreshCw,
    title: "When the valuation is updated",
    text: "When the market valuation is updated, the value of your investment and the unit price are updated in Investments and on your dashboard, and you are told by email and in your notifications on the platform.",
  },
  {
    icon: LogOut,
    title: "When you exit",
    text: "The latest updated unit price is the reference for pricing your sale. The final price is fixed when the deal completes, according to the market's mechanism.",
  },
];

const DRIVERS: Point[] = [
  {
    icon: HardHat,
    title: "Construction progress",
    text: "The unit's market value may rise as it moves from off-plan to execution and as construction advances to handover, depending on market conditions.",
  },
  {
    icon: Layers,
    title: "Rising release-phase prices",
    text: "The developer releases units in successive phases, each priced higher than the one before under the approved release schedule.",
  },
  {
    icon: TrendingUp,
    title: "Stepped prices offered to the platform",
    text: "The developer updates the prices of the units it makes available to the platform under its agreement, and new batches offered are priced at the updated price.",
  },
  {
    icon: Award,
    title: "Pre-launch purchase discount",
    text: "The discount obtained on the unit before it was released to investors lets you enter below the opportunity's reference price.",
  },
];

const AFTER_PURCHASE: Point = {
  icon: CalendarClock,
  title: "Following your investment after purchase",
  text: "A valuation of the unit's current market value is issued every three months. When it is updated, the new unit price appears on your dashboard and is reflected in the value of your investment in the unit and in the total value of your investments. Your dashboard also shows how much the value of your investment has changed, as an amount and a percentage, compared with its value at purchase.",
};

const OFFPLAN_EXIT: Point = {
  icon: LogOut,
  title: "Exit",
  text: "On exit, the latest updated valuation of the property shown on the platform is the reference for pricing the units offered for sale. The final sale price is set when the deal completes, and that is when the gain or loss is actually realised.",
};

const JOURNEY: Point[] = [
  { icon: ShieldCheck, title: "Verify your identity", text: "Complete identity verification (KYC) first." },
  { icon: Building2, title: "Buy your units", text: "Choose the number of units and pay." },
  {
    icon: FileCheck2,
    title: "Your certificate is issued",
    text: "As soon as the purchase completes, the system issues the ownership certificate for the units you bought, in Certificates on your dashboard.",
  },
  {
    icon: BarChart3,
    title: "Your units in Investments",
    text: "Your units appear in Investments on your dashboard, where you can sell them or transfer them.",
  },
];

function PointRow({ p }: { p: Point }) {
  return (
    <div className="flex gap-3">
      <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
        <p.icon className="h-4 w-4 text-primary" />
      </div>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-foreground">{p.title}</p>
        <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">{p.text}</p>
      </div>
    </div>
  );
}

interface InvestmentModelSectionProps {
  /** a ready property (rent + value growth); otherwise under construction */
  ready: boolean;
}

const InvestmentModelSection = ({ ready }: InvestmentModelSectionProps) => {
  return (
    <Card className="border-border" data-testid="investment-model">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-lg">
            <BadgeCheck className="h-5 w-5 text-primary" />
            Investment Model
          </CardTitle>
          <Badge variant="outline">{ready ? "Ready property" : "Under construction"}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {ready ? (
          <div className="grid gap-5 md:grid-cols-2" data-testid="model-ready">
            {READY.map((p) => (
              <PointRow key={p.title} p={p} />
            ))}
          </div>
        ) : (
          <div className="space-y-5" data-testid="model-offplan">
            <p className="text-sm leading-relaxed text-muted-foreground">
              This model relies on the potential growth in a unit's value from its off-plan purchase to handover,
              supported by four drivers:
            </p>
            <ol className="grid gap-5 md:grid-cols-2">
              {DRIVERS.map((p) => (
                <li key={p.title}>
                  <PointRow p={p} />
                </li>
              ))}
            </ol>
            <div className="grid gap-5 border-t border-border pt-5 md:grid-cols-2">
              <PointRow p={AFTER_PURCHASE} />
              <PointRow p={OFFPLAN_EXIT} />
            </div>
          </div>
        )}

        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4" data-testid="model-journey">
          <p className="mb-3 text-sm font-semibold text-foreground">From purchase to ownership certificate</p>
          <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {JOURNEY.map((p, i) => (
              <li key={p.title} className="flex gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
                  {i + 1}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground">{p.title}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{p.text}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </CardContent>
    </Card>
  );
};

export default InvestmentModelSection;
