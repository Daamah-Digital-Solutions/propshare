import { CreditCard, Wallet, Bitcoin, Coins, Percent, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";

const paymentMethods = [
  { icon: CreditCard, label: "Visa / Mastercard", description: "Instant payment" },
  { icon: Wallet, label: "Apple Pay / Google Pay", description: "One-tap checkout" },
  { icon: Bitcoin, label: "Cryptocurrency", description: "BTC, ETH, USDT" },
  { icon: Coins, label: "Pronova Token", description: "5% Discount" },
];

const PaymentSection = () => {
  return (
    <section className="py-20 bg-background">
      <div className="container mx-auto px-4">
        <div className="max-w-5xl mx-auto">
          {/* Header */}
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
              Flexible Payment Options
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Choose from multiple payment methods to fund your property ownership. 
              Get exclusive discounts when paying with Pronova Token.
            </p>
          </div>

          {/* Payment Methods Grid */}
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-12">
            {paymentMethods.map((method, index) => (
              <div
                key={index}
                className="bg-card rounded-2xl p-6 border border-border hover:border-primary/30 hover:shadow-md transition-all text-center"
              >
                <div className="w-14 h-14 bg-secondary rounded-xl flex items-center justify-center mx-auto mb-4">
                  <method.icon size={28} className="text-primary" />
                </div>
                <h4 className="font-semibold text-foreground mb-1">{method.label}</h4>
                <p className="text-sm text-muted-foreground">{method.description}</p>
              </div>
            ))}
          </div>

          {/* Pronova Token Promo */}
          <div className="bg-gradient-gold rounded-3xl p-8 md:p-10 text-accent-foreground">
            <div className="grid md:grid-cols-2 gap-8 items-center">
              <div>
                <div className="inline-flex items-center gap-2 bg-accent-foreground/20 rounded-full px-4 py-2 mb-4">
                  <Percent size={16} />
                  <span className="text-sm font-semibold">Exclusive Discount</span>
                </div>
                <h3 className="text-2xl md:text-3xl font-bold mb-4">
                  Save 5% with Pronova Token
                </h3>
                <p className="text-accent-foreground/80 mb-6">
                  Pay for your property ownership using Pronova Token and receive an automatic 
                  5% discount on all transaction fees. The more you own, the more you save.
                </p>
                <Button 
                  variant="outline" 
                  size="lg"
                  className="border-accent-foreground/30 text-accent-foreground hover:bg-accent-foreground/10"
                  asChild
                >
                  <a href="https://www.pronovacrypto.com" target="_blank" rel="noopener noreferrer">
                    Learn About Pronova Token
                    <ArrowRight size={18} />
                  </a>
                </Button>
              </div>
              
              <div className="flex justify-center">
                <div className="relative">
                  <div className="w-40 h-40 bg-accent-foreground/20 rounded-full flex items-center justify-center">
                    <div className="w-32 h-32 bg-accent-foreground/30 rounded-full flex items-center justify-center">
                      <div className="text-center">
                        <Coins size={40} className="mx-auto mb-2" />
                        <span className="font-bold text-lg">PRO</span>
                      </div>
                    </div>
                  </div>
                  <div className="absolute -top-2 -right-2 bg-accent-foreground text-accent px-3 py-1 rounded-full font-bold text-sm">
                    -5%
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Nova Financing */}
          <div className="mt-8 bg-card rounded-3xl p-8 border border-border">
            <div className="flex flex-col md:flex-row items-start md:items-center gap-6">
              <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center flex-shrink-0">
                <span className="text-2xl font-bold text-primary">N</span>
              </div>
              <div className="flex-1">
                <h3 className="text-xl font-bold text-foreground mb-2">Nova Financing (Sukuk-Based)</h3>
                <p className="text-muted-foreground">
                  Need additional funding? Access Shariah-compliant financing through our Nova Sukuk program. 
                  Flexible terms with competitive profit rates.
                </p>
              </div>
              <Button variant="outline" asChild>
                <a href="https://www.novadf.com" target="_blank" rel="noopener noreferrer">
                  Learn More
                </a>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default PaymentSection;
