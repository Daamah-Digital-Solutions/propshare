import { Button } from "@/components/ui/button";
import { ArrowRight, Banknote, RefreshCcw, Shield, Wallet } from "lucide-react";
import { useNavigate } from "react-router-dom";

const features = [
  {
    icon: Banknote,
    title: "Competitive Returns",
    description: "Earn attractive fixed returns backed by premium real estate assets.",
  },
  {
    icon: Shield,
    title: "Asset-Backed Security",
    description: "Your capital is secured against tangible real estate assets.",
  },
  {
    icon: RefreshCcw,
    title: "Flexible Terms",
    description: "Choose liquidity periods that match your ownership goals.",
  },
  {
    icon: Wallet,
    title: "Multiple Payouts",
    description: "Receive returns via bank transfer or cryptocurrency.",
  },
];

const LiquiditySection = () => {
  const navigate = useNavigate();

  const handleApplyAsProvider = () => {
    navigate("/liquidity-dashboard");
  };

  return (
    <section className="py-20 bg-foreground text-primary-foreground overflow-hidden relative">
      {/* Background Pattern */}
      <div className="absolute inset-0 opacity-5">
        <div className="absolute top-0 left-0 w-96 h-96 bg-primary rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-accent rounded-full blur-3xl" />
      </div>

      <div className="container mx-auto px-4 relative z-10">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          {/* Content */}
          <div>
            <div className="inline-flex items-center gap-2 bg-primary/20 rounded-full px-4 py-2 mb-6">
              <Wallet size={16} className="text-primary" />
              <span className="text-sm font-medium text-primary">Liquidity Provider Program</span>
            </div>
            
            <h2 className="text-3xl md:text-4xl font-bold mb-6">
              Become a <span className="text-primary">Liquidity Provider</span>
            </h2>
            
            <p className="text-primary-foreground/70 text-lg mb-8 max-w-xl">
              Support platform growth and earn premium returns by providing liquidity. 
              Your capital helps facilitate property funding and secondary market transactions.
            </p>

            <div className="grid sm:grid-cols-2 gap-4 mb-8">
              {features.map((feature, index) => (
                <div
                  key={index}
                  className="flex items-start gap-3 p-4 bg-primary-foreground/5 rounded-xl border border-primary-foreground/10"
                >
                  <feature.icon size={24} className="text-primary flex-shrink-0" />
                  <div>
                    <h4 className="font-semibold mb-1">{feature.title}</h4>
                    <p className="text-sm text-primary-foreground/60">{feature.description}</p>
                  </div>
                </div>
              ))}
            </div>

            <Button variant="hero" size="lg" onClick={handleApplyAsProvider}>
              Apply as Provider
              <ArrowRight size={18} />
            </Button>
          </div>

          {/* Visual - Simplified without returns table */}
          <div className="relative">
            <div className="bg-gradient-hero rounded-3xl p-8 shadow-glow">
              <h3 className="text-xl font-semibold mb-6">Why Become a Provider?</h3>
              
              <div className="space-y-4">
                <div className="flex items-center gap-4 bg-primary-foreground/10 rounded-xl p-4">
                  <div className="w-12 h-12 rounded-full bg-primary/20 flex items-center justify-center">
                    <Banknote size={24} className="text-primary" />
                  </div>
                  <div>
                    <div className="font-semibold">Premium Returns</div>
                    <div className="text-sm text-primary-foreground/70">Earn competitive yields on your capital</div>
                  </div>
                </div>

                <div className="flex items-center gap-4 bg-primary-foreground/10 rounded-xl p-4">
                  <div className="w-12 h-12 rounded-full bg-primary/20 flex items-center justify-center">
                    <Shield size={24} className="text-primary" />
                  </div>
                  <div>
                    <div className="font-semibold">Asset-Backed</div>
                    <div className="text-sm text-primary-foreground/70">Secured by real estate assets</div>
                  </div>
                </div>

                <div className="flex items-center gap-4 bg-primary-foreground/10 rounded-xl p-4">
                  <div className="w-12 h-12 rounded-full bg-primary/20 flex items-center justify-center">
                    <RefreshCcw size={24} className="text-primary" />
                  </div>
                  <div>
                    <div className="font-semibold">Flexible Terms</div>
                    <div className="text-sm text-primary-foreground/70">Choose your preferred commitment period</div>
                  </div>
                </div>
              </div>

              <div className="mt-6 pt-6 border-t border-primary-foreground/10">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-primary-foreground/70">Total Liquidity Provided</span>
                  <span className="font-bold text-lg">$12.5M+</span>
                </div>
              </div>
            </div>

            {/* Floating Badge */}
            <div className="absolute -top-4 -right-4 bg-accent text-accent-foreground px-4 py-2 rounded-full font-semibold shadow-lg">
              Up to 12% APY
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default LiquiditySection;
