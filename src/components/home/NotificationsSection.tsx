import { Link } from "react-router-dom";
import { ExternalLink, TrendingUp, Users, Bell, ArrowRight, Percent, Gift } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const NotificationsSection = () => {
  const notifications = [
    {
      id: 1,
      icon: ExternalLink,
      badge: "New Platform",
      title: "Capimax Tokenization on Blockchain",
      description: "Discover our revolutionary real estate ownership platform powered by blockchain technology. Secure, transparent, and accessible tokenized property ownership.",
      link: "https://capimaxtokenization.store",
      linkText: "Visit Platform",
      isExternal: true,
      color: "from-blue-500 to-cyan-500",
    },
    {
      id: 2,
      icon: TrendingUp,
      badge: "Exclusive Offer",
      title: "Profit Reinvestment Feature",
      description: "Automatically reinvest your returns and enjoy exclusive benefits:",
      features: [
        { icon: Percent, text: "5% Discount on reinvested amounts" },
        { icon: Gift, text: "Pronova bonus rewards for reinvestment" },
      ],
      link: "/dashboard?tab=returns",
      linkText: "Reinvest Now",
      isExternal: false,
      color: "from-emerald-500 to-teal-500",
    },
    {
      id: 3,
      icon: Users,
      badge: "Family Benefits",
      title: "Family Ownership Feature",
      description: "Build wealth together with your family through our integrated family ownership tools:",
      features: [
        { icon: Users, text: "Allocate returns or ownership shares to family members" },
        { icon: Gift, text: "Transfer and link accounts with zero transfer fees" },
      ],
      link: "/dashboard?tab=family",
      linkText: "Manage Family",
      isExternal: false,
      color: "from-purple-500 to-pink-500",
    },
  ];

  return (
    <section className="py-16 md:py-24 bg-gradient-to-b from-muted/30 to-background">
      <div className="container mx-auto px-4">
        {/* Section Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 bg-primary/10 text-primary px-4 py-2 rounded-full mb-4">
            <Bell className="w-4 h-4" />
            <span className="text-sm font-semibold">What's New</span>
          </div>
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            Latest Updates & Features
          </h2>
          <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
            Stay informed about our newest features and exclusive real estate opportunities
          </p>
        </div>

        {/* Notifications Grid */}
        <div className="grid md:grid-cols-3 gap-6 lg:gap-8">
          {notifications.map((notification) => (
            <Card 
              key={notification.id} 
              className="group relative overflow-hidden border-border/50 hover:border-primary/30 transition-all duration-300 hover:shadow-xl hover:-translate-y-1"
            >
              {/* Gradient accent bar */}
              <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${notification.color}`} />
              
              <CardContent className="p-6">
                {/* Icon and Badge */}
                <div className="flex items-start justify-between mb-4">
                  <div className={`p-3 rounded-xl bg-gradient-to-r ${notification.color} bg-opacity-10`}>
                    <notification.icon className="w-6 h-6 text-white" />
                  </div>
                  <Badge variant="secondary" className="text-xs font-medium">
                    {notification.badge}
                  </Badge>
                </div>

                {/* Content */}
                <h3 className="text-xl font-bold text-foreground mb-3 group-hover:text-primary transition-colors">
                  {notification.title}
                </h3>
                <p className="text-muted-foreground text-sm mb-4 leading-relaxed">
                  {notification.description}
                </p>

                {/* Features list if available */}
                {notification.features && (
                  <ul className="space-y-2 mb-6">
                    {notification.features.map((feature, index) => (
                      <li key={index} className="flex items-center gap-2 text-sm text-foreground">
                        <feature.icon className="w-4 h-4 text-primary" />
                        <span>{feature.text}</span>
                      </li>
                    ))}
                  </ul>
                )}

                {/* CTA Button */}
                {notification.isExternal ? (
                  <a
                    href={notification.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-block w-full"
                  >
                    <Button 
                      className={`w-full bg-gradient-to-r ${notification.color} hover:opacity-90 text-white group/btn`}
                    >
                      {notification.linkText}
                      <ExternalLink className="w-4 h-4 ml-2 group-hover/btn:translate-x-1 transition-transform" />
                    </Button>
                  </a>
                ) : (
                  <Link to={notification.link} className="inline-block w-full">
                    <Button 
                      className={`w-full bg-gradient-to-r ${notification.color} hover:opacity-90 text-white group/btn`}
                    >
                      {notification.linkText}
                      <ArrowRight className="w-4 h-4 ml-2 group-hover/btn:translate-x-1 transition-transform" />
                    </Button>
                  </Link>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
};

export default NotificationsSection;
