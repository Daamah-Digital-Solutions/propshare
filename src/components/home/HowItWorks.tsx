import { UserPlus, Search, CreditCard, TrendingUp, Building2, Shield } from "lucide-react";

const steps = [
  {
    icon: UserPlus,
    title: "Create Account",
    description: "Sign up in minutes and complete KYC verification to unlock real estate ownership opportunities.",
    color: "bg-primary",
  },
  {
    icon: Search,
    title: "Browse Properties",
    description: "Explore vetted properties with detailed financials, location analysis, and expected returns.",
    color: "bg-accent",
  },
  {
    icon: CreditCard,
    title: "Own Your Share",
    description: "Acquire fractional ownership starting from $100. Multiple payment methods available.",
    color: "bg-primary",
  },
  {
    icon: TrendingUp,
    title: "Earn Returns",
    description: "Receive rental income distributions and benefit from property value appreciation.",
    color: "bg-accent",
  },
];

const HowItWorks = () => {
  return (
    <section className="py-20 bg-secondary/30">
      <div className="container mx-auto px-4">
        {/* Header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            What is Fractional Real Estate Ownership?
          </h2>
          <p className="text-lg text-muted-foreground">
            Own a share of premium properties without the hassle of full ownership. 
            Pool resources with other owners to access institutional-grade real estate.
          </p>
        </div>

        {/* Steps */}
        <div className="grid md:grid-cols-4 gap-8 mb-16">
          {steps.map((step, index) => (
            <div
              key={index}
              className="relative text-center animate-fade-up"
              style={{ animationDelay: `${index * 0.15}s` }}
            >
              {/* Connector Line */}
              {index < steps.length - 1 && (
                <div className="hidden md:block absolute top-12 left-1/2 w-full h-0.5 bg-border z-0" />
              )}
              
              {/* Icon */}
              <div className={`relative z-10 w-24 h-24 ${step.color} rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-lg`}>
                <step.icon size={36} className="text-primary-foreground" />
              </div>
              
              {/* Step Number */}
              <div className="absolute top-0 right-1/2 translate-x-16 -translate-y-2 w-8 h-8 bg-foreground text-background rounded-full flex items-center justify-center text-sm font-bold">
                {index + 1}
              </div>
              
              <h3 className="text-xl font-semibold text-foreground mb-3">{step.title}</h3>
              <p className="text-muted-foreground">{step.description}</p>
            </div>
          ))}
        </div>

        {/* SPV Model Explainer */}
        <div className="bg-card rounded-3xl p-8 md:p-12 border border-border shadow-lg">
          <div className="grid md:grid-cols-2 gap-8 items-center">
            <div>
              <div className="inline-flex items-center gap-2 bg-primary/10 text-primary rounded-full px-4 py-2 mb-4">
                <Shield size={16} />
                <span className="text-sm font-medium">Secure Ownership Structure</span>
              </div>
              <h3 className="text-2xl md:text-3xl font-bold text-foreground mb-4">
                Protected by SPV Model
              </h3>
              <p className="text-muted-foreground mb-6">
                Each property is held in a Special Purpose Vehicle (SPV), a legal entity that 
                owns the asset and issues shares to owners. This structure provides:
              </p>
              <ul className="space-y-3">
                {[
                  "Legal separation of assets for owner protection",
                  "Clear ownership structure with blockchain verification",
                  "Simplified tax reporting and compliance",
                  "Ability to trade shares on secondary market",
                ].map((item, index) => (
                  <li key={index} className="flex items-start gap-3">
                    <div className="w-5 h-5 rounded-full bg-success/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <div className="w-2 h-2 rounded-full bg-success" />
                    </div>
                    <span className="text-foreground">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            
            {/* Visual Diagram */}
            <div className="relative">
              <div className="bg-secondary/50 rounded-2xl p-6 space-y-4">
                <div className="flex items-center gap-4 bg-background rounded-xl p-4 border border-border">
                  <Building2 className="text-primary" size={24} />
                  <div>
                    <div className="font-semibold text-foreground">Property Asset</div>
                    <div className="text-sm text-muted-foreground">$2,500,000 Value</div>
                  </div>
                </div>
                <div className="flex justify-center">
                  <div className="w-0.5 h-8 bg-border" />
                </div>
                <div className="flex items-center gap-4 bg-primary/10 rounded-xl p-4 border border-primary/20">
                  <Shield className="text-primary" size={24} />
                  <div>
                    <div className="font-semibold text-foreground">SPV Entity</div>
                    <div className="text-sm text-muted-foreground">Legal Asset Holder</div>
                  </div>
                </div>
                <div className="flex justify-center">
                  <div className="w-0.5 h-8 bg-border" />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {[...Array(3)].map((_, i) => (
                    <div key={i} className="flex flex-col items-center gap-2 bg-background rounded-xl p-3 border border-border">
                      <div className="w-10 h-10 bg-accent/20 rounded-full flex items-center justify-center">
                        <span className="text-accent font-bold text-sm">I{i + 1}</span>
                      </div>
                      <span className="text-xs text-muted-foreground">Owner {i + 1}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default HowItWorks;
