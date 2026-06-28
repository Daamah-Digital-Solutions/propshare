import HeroSection from "@/components/home/HeroSection";
import NotificationsSection from "@/components/home/NotificationsSection";
import FeaturedProperties from "@/components/home/FeaturedProperties";
import HowItWorksSection from "@/components/home/HowItWorks";
import BenefitsSection from "@/components/home/BenefitsSection";
import SecondaryMarket from "@/components/home/SecondaryMarket";
import LiquiditySection from "@/components/home/LiquiditySection";
import PaymentSection from "@/components/home/PaymentSection";
import CTASection from "@/components/home/CTASection";
import PropertyTypesBanner from "@/components/home/PropertyTypesBanner";

const Index = () => {
  return (
    <div className="min-h-screen bg-background">
      <main>
        <HeroSection />
        <PropertyTypesBanner />
        <FeaturedProperties />
        <HowItWorksSection />
        <BenefitsSection />
        <SecondaryMarket />
        <LiquiditySection />
        <PaymentSection />
        <NotificationsSection />
        <CTASection />
      </main>
    </div>
  );
};

export default Index;
