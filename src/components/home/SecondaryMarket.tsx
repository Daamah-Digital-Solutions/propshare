import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowRight, ArrowLeftRight, Clock, TrendingUp, Shield } from "lucide-react";

const SecondaryMarket = () => {
  return (
    <section className="py-20 bg-secondary/30">
      <div className="container mx-auto px-4">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          {/* Visual — illustrative, NOT live market data. Live listings require a signed-in
              account (the listings API is authenticated), so the public homepage shows an
              explainer + a real CTA rather than fabricated "live" prices/volume. */}
          <div className="order-2 lg:order-1">
            <div className="bg-card rounded-3xl p-6 border border-border shadow-lg">
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <h4 className="font-semibold text-foreground">How the Secondary Market Works</h4>
                <Link to="/secondary-market" className="text-sm text-primary font-medium hover:underline">
                  View All
                </Link>
              </div>

              {/* Explainer steps (descriptive, no fake numbers) */}
              <div className="space-y-4">
                {[
                  {
                    icon: ArrowLeftRight,
                    title: "List your units",
                    description: "Set an asking price within the platform's allowed price band.",
                  },
                  {
                    icon: TrendingUp,
                    title: "Buyers purchase units",
                    description: "Another investor buys your units; the trade settles atomically.",
                  },
                  {
                    icon: Shield,
                    title: "Secure, server-priced settlement",
                    description: "Fees and price bounds are enforced server-side on every trade.",
                  },
                ].map((step, index) => (
                  <div
                    key={index}
                    className="flex items-center gap-4 p-4 bg-secondary/50 rounded-xl"
                  >
                    <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center flex-shrink-0">
                      <step.icon size={20} className="text-primary" />
                    </div>
                    <div>
                      <div className="font-medium text-foreground">{step.title}</div>
                      <div className="text-sm text-muted-foreground">{step.description}</div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Activity note (honest — no fabricated volume) */}
              <div className="mt-6 pt-6 border-t border-border">
                <span className="text-sm text-muted-foreground">
                  Sign in to view current active listings and trade your units.
                </span>
              </div>
            </div>
          </div>

          {/* Content */}
          <div className="order-1 lg:order-2">
            <div className="inline-flex items-center gap-2 bg-primary/10 text-primary rounded-full px-4 py-2 mb-6">
              <ArrowLeftRight size={16} />
              <span className="text-sm font-medium">Secondary Market</span>
            </div>
            
            <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-6">
              Trade Your Ownership Units Anytime
            </h2>
            
            <p className="text-muted-foreground text-lg mb-8">
              Unlike traditional real estate, our secondary market lets you sell your 
              ownership units before the property exit. Enjoy liquidity while maintaining 
              exposure to real estate returns.
            </p>

            <div className="space-y-4 mb-8">
              {[
                {
                  icon: Clock,
                  title: "Exit After 6 Months",
                  description: "Trade units on the secondary market after a 6-month holding period.",
                },
                {
                  icon: TrendingUp,
                  title: "Market-Based Pricing",
                  description: "Unit prices reflect current market demand and property performance.",
                },
                {
                  icon: Shield,
                  title: "Secure Transactions",
                  description: "All trades are verified and settled through our secure platform.",
                },
              ].map((feature, index) => (
                <div key={index} className="flex items-start gap-4">
                  <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center flex-shrink-0">
                    <feature.icon size={20} className="text-primary" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-foreground mb-1">{feature.title}</h4>
                    <p className="text-sm text-muted-foreground">{feature.description}</p>
                  </div>
                </div>
              ))}
            </div>

            <Link to="/secondary-market">
              <Button variant="default" size="lg">
                Explore Secondary Market
                <ArrowRight size={18} />
              </Button>
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
};

export default SecondaryMarket;
