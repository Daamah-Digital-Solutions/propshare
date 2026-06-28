import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowRight, CheckCircle } from "lucide-react";

const CTASection = () => {
  const benefits = [
    "Start owning from just $100",
    "Earn quarterly rental income",
    "Full transparency & security",
    "Exit anytime via secondary market",
  ];

  return (
    <section className="py-20 bg-background">
      <div className="container mx-auto px-4">
        <div className="relative bg-gradient-hero rounded-3xl p-8 md:p-16 overflow-hidden">
          {/* Background Elements */}
          <div className="absolute top-0 right-0 w-96 h-96 bg-primary-foreground/5 rounded-full blur-3xl" />
          <div className="absolute bottom-0 left-0 w-64 h-64 bg-accent/10 rounded-full blur-3xl" />

          <div className="relative z-10 max-w-3xl mx-auto text-center text-primary-foreground">
            <h2 className="text-3xl md:text-5xl font-bold mb-6">
              Start Building Your Real Estate Portfolio Today
            </h2>
            <p className="text-lg md:text-xl text-primary-foreground/80 mb-8">
              Join thousands of owners already earning passive income through 
              fractional property ownership. No experience needed.
            </p>

            {/* Benefits */}
            <div className="flex flex-wrap justify-center gap-4 mb-10">
              {benefits.map((benefit, index) => (
                <div
                  key={index}
                  className="flex items-center gap-2 bg-primary-foreground/10 backdrop-blur-sm rounded-full px-4 py-2"
                >
                  <CheckCircle size={16} className="text-accent" />
                  <span className="text-sm font-medium">{benefit}</span>
                </div>
              ))}
            </div>

            {/* CTAs */}
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <Link to="/auth">
                <Button variant="gold" size="xl">
                  Create Free Account
                  <ArrowRight size={20} />
                </Button>
              </Link>
              <Link to="/support">
                <Button variant="heroOutline" size="xl">
                  Schedule a Demo
                </Button>
              </Link>
            </div>

            {/* Trust Note */}
            <p className="mt-8 text-sm text-primary-foreground/60">
              Regulated platform • 256-bit encryption • KYC verified owners
            </p>
          </div>
        </div>
      </div>
    </section>
  );
};

export default CTASection;
