import { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PortfolioOverview } from "@/components/dashboard/PortfolioOverview";
import { ActiveInvestments } from "@/components/dashboard/ActiveInvestments";
import { ReturnsTracker } from "@/components/dashboard/ReturnsTracker";
import { InstallmentSchedule } from "@/components/dashboard/InstallmentSchedule";
import { InvestorWallet } from "@/components/dashboard/InvestorWallet";
import { InvestmentCertificates } from "@/components/dashboard/InvestmentCertificates";
import { SecondaryMarketTab } from "@/components/dashboard/SecondaryMarketTab";
import { ProShareCards } from "@/components/dashboard/ProShareCards";
import { ReinvestReturns } from "@/components/dashboard/ReinvestReturns";
import { FamilyInvestment } from "@/components/dashboard/FamilyInvestment";
import {
  LayoutDashboard,
  Building2,
  TrendingUp,
  Calendar,
  Wallet,
  FileText,
  Bell,
  Settings,
  ArrowRightLeft,
  RefreshCcw,
  Users,
  CreditCard,
  LogOut,
  Home,
  Plus
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ExitRequestsPanel } from "@/components/exit/ExitRequestsPanel";
import { ExitButton } from "@/components/exit/ExitButton";

const validTabs = ["overview", "investments", "returns", "installments", "wallet", "cards", "market", "reinvest", "family", "certificates", "exits"];

const InvestorDashboard = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const greetingName = user?.full_name?.trim() || user?.email?.split("@")[0] || "Investor";
  const tabFromUrl = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState(() => {
    return validTabs.includes(tabFromUrl || "") ? tabFromUrl! : "overview";
  });

  useEffect(() => {
    if (tabFromUrl && validTabs.includes(tabFromUrl) && tabFromUrl !== activeTab) {
      setActiveTab(tabFromUrl);
    }
  }, [tabFromUrl]);

  const handleTabChange = (value: string) => {
    setActiveTab(value);
    setSearchParams({ tab: value });
  };

  return (
    <div className="min-h-screen bg-background">
      <main>
        {/* Dashboard Header */}
        <section className="bg-gradient-to-br from-primary/10 via-background to-accent/5 py-8 border-b border-border">
          <div className="container mx-auto px-4">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <div>
                <h1 className="text-3xl font-bold text-foreground">
                  Welcome back, <span className="text-primary">{greetingName}</span>
                </h1>
                <p className="text-muted-foreground mt-1">
                  Here's an overview of your investment portfolio
                </p>
              </div>
              <div className="flex items-center gap-3 flex-wrap">
                <Button
                  className="gap-2 bg-primary text-primary-foreground hover:bg-primary/90"
                  onClick={() => navigate("/marketplace")}
                >
                  <Plus className="h-4 w-4" />
                  New Investment
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Home"
                  onClick={() => navigate("/")}
                >
                  <Home className="h-5 w-5" />
                </Button>
                <ExitButton variant="outline" label="Exit" />
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Notifications"
                  onClick={() => navigate("/notifications")}
                >
                  <Bell className="h-5 w-5" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Account settings"
                  onClick={() => navigate("/settings")}
                >
                  <Settings className="h-5 w-5" />
                </Button>
              </div>
            </div>
          </div>
        </section>

        {/* Dashboard Content */}
        <section className="py-8">
          <div className="container mx-auto px-4">
            <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-8">
              <TabsList className="w-full flex flex-wrap justify-start gap-2 h-auto p-2 bg-muted/50">
                <TabsTrigger 
                  value="overview" 
                  className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                >
                  <LayoutDashboard className="h-4 w-4" />
                  <span className="hidden sm:inline">Portfolio Overview</span>
                  <span className="sm:hidden">Overview</span>
                </TabsTrigger>
                <TabsTrigger 
                  value="investments"
                  className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                >
                  <Building2 className="h-4 w-4" />
                  <span className="hidden sm:inline">Active Investments</span>
                  <span className="sm:hidden">Investments</span>
                </TabsTrigger>
                <TabsTrigger 
                  value="returns"
                  className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                >
                  <TrendingUp className="h-4 w-4" />
                  <span className="hidden sm:inline">Returns Tracker</span>
                  <span className="sm:hidden">Returns</span>
                </TabsTrigger>
                <TabsTrigger 
                  value="installments"
                  className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                >
                  <Calendar className="h-4 w-4" />
                  <span className="hidden sm:inline">Installment Schedule</span>
                  <span className="sm:hidden">Installments</span>
                </TabsTrigger>
                <TabsTrigger 
                  value="wallet"
                  className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                >
                  <Wallet className="h-4 w-4" />
                  Wallet
                </TabsTrigger>
                <TabsTrigger 
                  value="cards"
                  className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                >
                  <CreditCard className="h-4 w-4" />
                  <span className="hidden sm:inline">ProShare Cards</span>
                  <span className="sm:hidden">Cards</span>
                </TabsTrigger>
                <TabsTrigger 
                  value="market"
                  className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                >
                  <ArrowRightLeft className="h-4 w-4" />
                  <span className="hidden sm:inline">Secondary Market</span>
                  <span className="sm:hidden">Market</span>
                </TabsTrigger>
                <TabsTrigger 
                  value="reinvest"
                  className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                >
                  <RefreshCcw className="h-4 w-4" />
                  <span className="hidden sm:inline">Reinvest Returns</span>
                  <span className="sm:hidden">Reinvest</span>
                </TabsTrigger>
                <TabsTrigger 
                  value="family"
                  className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                >
                  <Users className="h-4 w-4" />
                  <span className="hidden sm:inline">Family Investment</span>
                  <span className="sm:hidden">Family</span>
                </TabsTrigger>
                <TabsTrigger 
                  value="certificates"
                  className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                >
                  <FileText className="h-4 w-4" />
                  Certificates
                </TabsTrigger>
                <TabsTrigger 
                  value="exits"
                  className="flex items-center gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                >
                  <LogOut className="h-4 w-4" />
                  <span className="hidden sm:inline">Exit Requests</span>
                  <span className="sm:hidden">Exits</span>
                </TabsTrigger>
              </TabsList>

              <TabsContent value="overview" className="space-y-6">
                <PortfolioOverview />
              </TabsContent>

              <TabsContent value="investments" className="space-y-6">
                <ActiveInvestments />
              </TabsContent>

              <TabsContent value="returns" className="space-y-6">
                <ReturnsTracker />
              </TabsContent>

              <TabsContent value="installments" className="space-y-6">
                <InstallmentSchedule />
              </TabsContent>

              <TabsContent value="wallet" className="space-y-6">
                <InvestorWallet />
              </TabsContent>

              <TabsContent value="cards" className="space-y-6">
                <ProShareCards />
              </TabsContent>

              <TabsContent value="reinvest" className="space-y-6">
                <ReinvestReturns availableReturns={19000} />
              </TabsContent>

              <TabsContent value="family" className="space-y-6">
                <FamilyInvestment />
              </TabsContent>

              <TabsContent value="certificates" className="space-y-6">
                <InvestmentCertificates />
              </TabsContent>

              <TabsContent value="market" className="space-y-6">
                <SecondaryMarketTab />
              </TabsContent>

              <TabsContent value="exits" className="space-y-6">
                <ExitRequestsPanel />
              </TabsContent>
            </Tabs>
          </div>
        </section>
      </main>
    </div>
  );
};

export default InvestorDashboard;
