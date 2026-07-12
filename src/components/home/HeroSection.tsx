import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  ArrowRight,
  Shield,
  TrendingUp,
  Users,
  Building2,
  PieChart,
  Coins,
  LineChart,
  ArrowLeftRight,
  Globe2,
  Sparkles,
  Layers,
  HardHat,
  CalendarClock,
  Hourglass,
  KeyRound,
  Briefcase,
  Home as HomeIcon,
} from "lucide-react";

const HeroSection = () => {
  const stats = [
    { value: "$50M+", label: "Assets Under Management" },
    { value: "15,000+", label: "Active Owners" },
    { value: "12%", label: "Avg. Annual Returns" },
    { value: "100+", label: "Properties Funded" },
  ];

  const pillars = [
    { icon: Building2, label: "Own Real Estate", sub: "Fractional title" },
    { icon: Coins, label: "Receive Returns", sub: "Rental income" },
    { icon: LineChart, label: "Grow Capital", sub: "Appreciation" },
    { icon: ArrowLeftRight, label: "Exit Easily", sub: "P2P liquidity" },
    { icon: Globe2, label: "Multiple Markets", sub: "Global access" },
  ];

  return (
    <section className="relative min-h-screen flex items-start sm:items-center pt-3 sm:pt-20 overflow-hidden">
      {/* Background */}
      <div className="absolute inset-0 bg-gradient-hero opacity-95" />
      <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHZpZXdCb3g9IjAgMCA2MCA2MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZyBmaWxsPSJub25lIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiPjxnIGZpbGw9IiNmZmZmZmYiIGZpbGwtb3BhY2l0eT0iMC4wNSI+PGNpcmNsZSBjeD0iMzAiIGN5PSIzMCIgcj0iMiIvPjwvZz48L2c+PC9zdmc+')] opacity-30" />

      {/* Floating Elements */}
      <div className="absolute top-1/4 right-10 w-64 h-64 bg-primary-foreground/5 rounded-full blur-3xl animate-float" />
      <div className="absolute bottom-1/4 left-10 w-48 h-48 bg-accent/10 rounded-full blur-3xl animate-float" style={{ animationDelay: "2s" }} />

      <div className="container mx-auto px-4 relative z-10 py-5 sm:py-10">
        {/* Institutional Ecosystem Banner */}
        <div className="mb-10 animate-fade-up">
          <div className="mx-auto max-w-5xl rounded-2xl border border-primary-foreground/15 bg-primary-foreground/[0.06] backdrop-blur-md px-5 py-4 md:px-7 md:py-5 shadow-glow">
            <div className="flex items-center justify-center gap-2 mb-2">
              <Sparkles size={14} className="text-accent" />
              <span className="text-[11px] md:text-xs uppercase tracking-[0.2em] text-accent font-semibold">
                A Complete Digital Real Estate Ecosystem
              </span>
            </div>
            <p className="text-center text-xs md:text-sm text-primary-foreground/90 font-medium mb-2">
              Global Real Estate Platform — Own Fractional Real Estate Shares Across More Than 15 Countries From Anywhere
            </p>
            <p className="text-center text-primary-foreground/85 text-sm md:text-base leading-relaxed">
              The First Digital Real Estate Ecosystem Bringing Together{" "}
              <span className="text-accent font-semibold">Developers, Property Owners, Investors, Brokers, and Liquidity Providers</span>{" "}
              in One Platform.
            </p>
          </div>
        </div>

        <div className="grid lg:grid-cols-2 gap-12 items-center">
          {/* Content */}
          <div className="text-primary-foreground animate-fade-up">
            <div className="inline-flex items-center gap-2 bg-primary-foreground/10 backdrop-blur-sm rounded-full px-4 py-2 mb-6">
              <Shield size={16} className="text-accent" />
              <span className="text-sm font-medium">Regulated • Institutional-Grade • Fully Compliant</span>
            </div>

            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold leading-tight mb-6">
              Own Real Estate.
              <br />
              <span className="text-accent">Earn. Grow. Exit.</span>
            </h1>

            <p className="text-lg md:text-xl text-primary-foreground/80 mb-8 max-w-xl">
              Acquire fractional ownership in premium properties worldwide, receive
              rental returns, benefit from capital appreciation, and exit easily
              through our integrated secondary market — all in one wealth-grade platform.
            </p>

            {/* Pillars */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5 mb-8">
              {pillars.map((p) => (
                <div
                  key={p.label}
                  className="group rounded-xl border border-primary-foreground/15 bg-primary-foreground/[0.06] backdrop-blur-sm p-3 hover:bg-primary-foreground/[0.1] transition-colors"
                >
                  <p.icon size={18} className="text-accent mb-1.5" />
                  <div className="text-xs font-semibold text-primary-foreground leading-tight">
                    {p.label}
                  </div>
                  <div className="text-[10px] text-primary-foreground/60 mt-0.5">
                    {p.sub}
                  </div>
                </div>
              ))}
            </div>

            <div className="flex flex-wrap gap-4 mb-10">
              <Link to="/marketplace">
                <Button variant="gold" size="xl">
                  Browse Properties
                  <ArrowRight size={20} />
                </Button>
              </Link>
              <Link to="/developer-dashboard">
                <Button variant="heroOutline" size="xl">
                  List Property
                </Button>
              </Link>
            </div>

            {/* Trust Indicators */}
            <div className="flex flex-wrap items-center gap-6 text-sm text-primary-foreground/70">
              <div className="flex items-center gap-2">
                <Shield size={18} className="text-accent" />
                <span>KYC Verified</span>
              </div>
              <div className="flex items-center gap-2">
                <TrendingUp size={18} className="text-accent" />
                <span>SPV Protected</span>
              </div>
              <div className="flex items-center gap-2">
                <PieChart size={18} className="text-accent" />
                <span>Fractional Title</span>
              </div>
              <div className="flex items-center gap-2">
                <Users size={18} className="text-accent" />
                <span>24/7 Support</span>
              </div>
            </div>
          </div>

          {/* Stats Card */}
          <div className="relative animate-fade-up" style={{ animationDelay: "0.2s" }}>
            <div className="bg-primary-foreground/10 backdrop-blur-lg rounded-3xl p-8 border border-primary-foreground/20 shadow-glow">
              <h3 className="text-primary-foreground text-lg font-semibold mb-6">Platform Performance</h3>
              <div className="grid grid-cols-2 gap-6">
                {stats.map((stat, index) => (
                  <div key={index} className="text-center p-4 bg-primary-foreground/5 rounded-2xl">
                    <div className="text-2xl md:text-3xl font-bold text-accent mb-1">{stat.value}</div>
                    <div className="text-sm text-primary-foreground/70">{stat.label}</div>
                  </div>
                ))}
              </div>

              {/* Live Activity */}
              <div className="mt-6 pt-6 border-t border-primary-foreground/10">
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <div className="w-3 h-3 bg-accent rounded-full animate-pulse" />
                    <div className="absolute inset-0 w-3 h-3 bg-accent rounded-full animate-ping" />
                  </div>
                  <span className="text-sm text-primary-foreground/80">
                    <strong>$125,000</strong> in property ownership acquired in the last hour
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Scroll Indicator */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 animate-bounce">
        <div className="w-6 h-10 border-2 border-primary-foreground/30 rounded-full flex justify-center pt-2">
          <div className="w-1 h-2 bg-primary-foreground/50 rounded-full" />
        </div>
      </div>
    </section>
  );
};

export default HeroSection;
