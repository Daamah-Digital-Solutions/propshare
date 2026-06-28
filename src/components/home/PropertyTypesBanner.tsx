import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Layers,
  HardHat,
  CalendarClock,
  Hourglass,
  KeyRound,
  Briefcase,
  Home as HomeIcon,
} from "lucide-react";

const types = [
  { icon: HomeIcon, label: "Ready" },
  { icon: HardHat, label: "Construction" },
  { icon: CalendarClock, label: "Installment" },
  { icon: Layers, label: "Phase-Based" },
  { icon: Hourglass, label: "Future" },
  { icon: KeyRound, label: "Option" },
];

const PropertyTypesBanner = () => {
  return (
    <section className="py-10 md:py-14 bg-background">
      <div className="container mx-auto px-4">
        <div className="mx-auto max-w-6xl rounded-2xl border border-accent/30 bg-gradient-to-br from-primary/[0.06] via-accent/[0.05] to-primary/[0.03] p-5 md:p-7 shadow-elegant">
          <div className="flex flex-col lg:flex-row lg:items-center gap-5">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <Layers size={14} className="text-accent" />
                <span className="text-[11px] md:text-xs uppercase tracking-[0.2em] text-accent font-semibold">
                  Multiple Ownership & Opportunity Models
                </span>
              </div>
              <h3 className="text-foreground text-lg md:text-2xl font-bold leading-snug">
                6 Different Real Estate Ownership & Opportunity Types Available on the Platform
              </h3>

              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mt-4">
                {types.map((t) => (
                  <div
                    key={t.label}
                    className="flex flex-col items-center justify-center rounded-lg border border-border bg-card py-2.5 px-1 hover:border-accent/50 hover:bg-accent/5 transition-colors"
                  >
                    <t.icon size={18} className="text-accent mb-1" />
                    <span className="text-[10px] md:text-xs text-foreground font-medium text-center leading-tight">
                      {t.label}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="lg:w-px lg:h-32 lg:bg-border hidden lg:block" />

            <div className="flex flex-col items-stretch lg:items-center gap-2 lg:min-w-[220px]">
              <Link to="/property-types">
                <Button variant="gold" size="lg" className="w-full">
                  <Briefcase size={18} />
                  Explore Property Types
                </Button>
              </Link>
              <Link
                to="/property-types"
                className="text-center text-xs text-muted-foreground hover:text-accent transition-colors"
              >
                Discover Opportunity Models →
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default PropertyTypesBanner;
