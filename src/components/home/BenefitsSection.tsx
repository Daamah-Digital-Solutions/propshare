import { 
  TrendingUp, 
  Shield, 
  Wallet, 
  Users, 
  Building2, 
  Globe,
  ArrowUpRight,
  DollarSign,
  Clock,
  Zap
} from "lucide-react";

const investorBenefits = [
  {
    icon: Wallet,
    title: "Low Entry Barrier",
    description: "Start owning from as little as $100 in premium properties worldwide.",
  },
  {
    icon: TrendingUp,
    title: "Passive Income",
    description: "Receive quarterly rental income distributions directly to your wallet.",
  },
  {
    icon: Globe,
    title: "Global Diversification",
    description: "Access properties across multiple markets to spread risk.",
  },
  {
    icon: Shield,
    title: "Full Transparency",
    description: "Track performance, view documents, and monitor your portfolio 24/7.",
  },
];

const ownerBenefits = [
  {
    icon: DollarSign,
    title: "Access Capital",
    description: "Unlock property equity without selling the entire asset.",
  },
  {
    icon: Users,
    title: "Wider Owner Pool",
    description: "Reach thousands of qualified property owners through our platform.",
  },
  {
    icon: Zap,
    title: "Faster Funding",
    description: "Complete property funding in weeks, not months.",
  },
  {
    icon: Building2,
    title: "Retain Ownership",
    description: "Keep managing your property while sharing equity with co-owners.",
  },
];

const BenefitsSection = () => {
  return (
    <section className="py-20 bg-background">
      <div className="container mx-auto px-4">
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            Benefits for Everyone
          </h2>
          <p className="text-lg text-muted-foreground">
            Our platform creates value for owners seeking wealth-building opportunities 
            and property owners looking to unlock capital.
          </p>
        </div>

        <div className="grid lg:grid-cols-2 gap-8 lg:gap-12">
          {/* Investor Benefits */}
          <div className="bg-gradient-hero rounded-3xl p-8 md:p-10 text-primary-foreground">
            <div className="flex items-center gap-3 mb-8">
              <div className="w-12 h-12 bg-primary-foreground/20 rounded-xl flex items-center justify-center">
                <TrendingUp size={24} />
              </div>
              <h3 className="text-2xl font-bold">For Investors</h3>
            </div>

            <div className="grid sm:grid-cols-2 gap-6">
              {investorBenefits.map((benefit, index) => (
                <div
                  key={index}
                  className="bg-primary-foreground/10 backdrop-blur-sm rounded-2xl p-5 border border-primary-foreground/10 hover:bg-primary-foreground/15 transition-colors"
                >
                  <benefit.icon size={28} className="text-accent mb-4" />
                  <h4 className="font-semibold text-lg mb-2">{benefit.title}</h4>
                  <p className="text-primary-foreground/80 text-sm">{benefit.description}</p>
                </div>
              ))}
            </div>

            <div className="mt-8 flex items-center gap-2 text-accent cursor-pointer hover:underline">
              <span className="font-medium">Start Owning Today</span>
              <ArrowUpRight size={18} />
            </div>
          </div>

          {/* Owner Benefits */}
          <div className="bg-card rounded-3xl p-8 md:p-10 border border-border shadow-lg">
            <div className="flex items-center gap-3 mb-8">
              <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center">
                <Building2 size={24} className="text-primary" />
              </div>
              <h3 className="text-2xl font-bold text-foreground">For Property Owners</h3>
            </div>

            <div className="grid sm:grid-cols-2 gap-6">
              {ownerBenefits.map((benefit, index) => (
                <div
                  key={index}
                  className="bg-secondary/50 rounded-2xl p-5 hover:bg-secondary transition-colors"
                >
                  <benefit.icon size={28} className="text-primary mb-4" />
                  <h4 className="font-semibold text-lg text-foreground mb-2">{benefit.title}</h4>
                  <p className="text-muted-foreground text-sm">{benefit.description}</p>
                </div>
              ))}
            </div>

            <div className="mt-8 flex items-center gap-2 text-primary cursor-pointer hover:underline">
              <span className="font-medium">List Your Property</span>
              <ArrowUpRight size={18} />
            </div>
          </div>
        </div>

        {/* Ownership Types */}
        <div className="mt-20">
          <h3 className="text-2xl md:text-3xl font-bold text-foreground text-center mb-12">
            Ownership Types
          </h3>
          
          <div className="grid md:grid-cols-2 gap-6">
            {/* Ready Properties */}
            <div className="group bg-card rounded-2xl p-6 border border-border hover:border-primary/30 hover:shadow-lg transition-all">
              <div className="flex items-start gap-4">
                <div className="w-14 h-14 bg-success/10 rounded-2xl flex items-center justify-center flex-shrink-0">
                  <TrendingUp size={28} className="text-success" />
                </div>
                <div>
                  <h4 className="text-xl font-semibold text-foreground mb-2">Ready Properties</h4>
                  <p className="text-muted-foreground mb-4">
                    Own shares in completed properties generating immediate rental income. 
                    Ideal for owners seeking stable, predictable returns.
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <span className="px-3 py-1 bg-success/10 text-success rounded-full text-sm font-medium">
                      Immediate Income
                    </span>
                    <span className="px-3 py-1 bg-secondary text-muted-foreground rounded-full text-sm">
                      8-12% Annual Yield
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Under Construction */}
            <div className="group bg-card rounded-2xl p-6 border border-border hover:border-primary/30 hover:shadow-lg transition-all">
              <div className="flex items-start gap-4">
                <div className="w-14 h-14 bg-accent/10 rounded-2xl flex items-center justify-center flex-shrink-0">
                  <Clock size={28} className="text-accent" />
                </div>
                <div>
                  <h4 className="text-xl font-semibold text-foreground mb-2">Under Construction</h4>
                  <p className="text-muted-foreground mb-4">
                    Access development-stage properties with installment payment options. 
                    Higher growth potential with capital appreciation focus.
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <span className="px-3 py-1 bg-accent/10 text-accent rounded-full text-sm font-medium">
                      Installment Plans
                    </span>
                    <span className="px-3 py-1 bg-secondary text-muted-foreground rounded-full text-sm">
                      15-25% Capital Growth
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default BenefitsSection;
