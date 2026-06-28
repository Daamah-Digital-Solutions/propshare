import { Suspense, lazy } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { ReinvestProvider } from "@/contexts/ReinvestContext";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { MainLayout } from "@/components/layout/MainLayout";
import PWAInstallPrompt from "@/components/pwa/PWAInstallPrompt";
import PWAServiceWorker from "@/components/pwa/PWAServiceWorker";

// Eagerly load the homepage for fast initial load
import Index from "./pages/Index";

// Lazy load all other pages for code splitting
const Marketplace = lazy(() => import("./pages/Marketplace"));
const PropertyDetails = lazy(() => import("./pages/PropertyDetails"));
const SamplePropertyDetails = lazy(() => import("./pages/SamplePropertyDetails"));
const InvestorDashboard = lazy(() => import("./pages/InvestorDashboard"));
const SecondaryMarket = lazy(() => import("./pages/SecondaryMarket"));
const OwnerDashboard = lazy(() => import("./pages/OwnerDashboard"));
const DeveloperDashboard = lazy(() => import("./pages/DeveloperDashboard"));
const LiquidityDashboard = lazy(() => import("./pages/LiquidityDashboard"));
const LiquidityProviderMarket = lazy(() => import("./pages/LiquidityProviderMarket"));
const ExitMechanisms = lazy(() => import("./pages/ExitMechanisms"));
const PropertyTypes = lazy(() => import("./pages/PropertyTypes"));
const ConstructionModelPage = lazy(() => import("./pages/ConstructionModelPage"));
const AdvancedPropertyPage = lazy(() => import("./pages/AdvancedPropertyPage"));
const BrokerDashboard = lazy(() => import("./pages/BrokerDashboard"));
const Notifications = lazy(() => import("./pages/Notifications"));
const Partners = lazy(() => import("./pages/Partners"));
const HowItWorks = lazy(() => import("./pages/HowItWorks"));
const SPVModel = lazy(() => import("./pages/SPVModel"));
const Fees = lazy(() => import("./pages/Fees"));
const Auth = lazy(() => import("./pages/Auth"));
const InstallApp = lazy(() => import("./pages/InstallApp"));
const Support = lazy(() => import("./pages/Support"));
const Disclaimer = lazy(() => import("./pages/Disclaimer"));
const Legal = lazy(() => import("./pages/Legal"));
const Terms = lazy(() => import("./pages/Terms"));
const Privacy = lazy(() => import("./pages/Privacy"));
const RiskDisclosure = lazy(() => import("./pages/RiskDisclosure"));
const PlatformRules = lazy(() => import("./pages/PlatformRules"));
const KYCVerification = lazy(() => import("./pages/KYCVerification"));
const AccountSettings = lazy(() => import("./pages/AccountSettings"));
const AboutCapimaxPropShare = lazy(() => import("./pages/AboutCapimaxPropShare"));
const FAQ = lazy(() => import("./pages/FAQ"));
const AuthCallback = lazy(() => import("./pages/AuthCallback"));
const NotFound = lazy(() => import("./pages/NotFound"));

const queryClient = new QueryClient();

// Loading fallback component
const PageLoader = () => (
  <div className="flex items-center justify-center min-h-[50vh]">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
  </div>
);

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <ReinvestProvider>
        <TooltipProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
            <PWAInstallPrompt />
            <PWAServiceWorker />
            <MainLayout>
              <Suspense fallback={<PageLoader />}>
                <Routes>
                  <Route path="/" element={<Index />} />
                  <Route path="/marketplace" element={<Marketplace />} />
                  <Route path="/property/:id" element={<PropertyDetails />} />
                  <Route path="/property-sample/:slug" element={<SamplePropertyDetails />} />
                  <Route
                    path="/dashboard"
                    element={
                      <ProtectedRoute roles={["investor"]}>
                        <InvestorDashboard />
                      </ProtectedRoute>
                    }
                  />
                  <Route path="/secondary-market" element={<SecondaryMarket />} />
                  <Route
                    path="/owner-dashboard"
                    element={
                      <ProtectedRoute roles={["owner"]}>
                        <OwnerDashboard />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/developer-dashboard"
                    element={
                      <ProtectedRoute roles={["owner"]}>
                        <DeveloperDashboard />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/liquidity-dashboard"
                    element={
                      <ProtectedRoute roles={["liquidity_provider"]}>
                        <LiquidityDashboard />
                      </ProtectedRoute>
                    }
                  />
                  <Route path="/liquidity-market" element={<LiquidityProviderMarket />} />
                  <Route path="/exit-mechanisms" element={<ExitMechanisms />} />
                  <Route path="/property-types" element={<PropertyTypes />} />
                  <Route path="/properties/:model" element={<ConstructionModelPage />} />
                  <Route path="/advanced-property/:model" element={<AdvancedPropertyPage />} />
                  <Route
                    path="/broker-dashboard"
                    element={
                      <ProtectedRoute roles={["broker"]}>
                        <BrokerDashboard />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/notifications"
                    element={
                      <ProtectedRoute>
                        <Notifications />
                      </ProtectedRoute>
                    }
                  />
                  <Route path="/partners" element={<Partners />} />
                  <Route path="/how-it-works" element={<HowItWorks />} />
                  <Route path="/spv-model" element={<SPVModel />} />
                  <Route path="/spv-model/:propertyId" element={<SPVModel />} />
                  <Route path="/fees" element={<Fees />} />
                  <Route path="/auth" element={<Auth />} />
                  <Route path="/auth/callback/:provider" element={<AuthCallback />} />
                  <Route path="/install" element={<InstallApp />} />
                  <Route path="/support" element={<Support />} />
                  <Route path="/disclaimer" element={<Disclaimer />} />
                  <Route path="/legal" element={<Legal />} />
                  <Route path="/terms" element={<Terms />} />
                  <Route path="/privacy" element={<Privacy />} />
                  <Route path="/risk-disclosure" element={<RiskDisclosure />} />
                  <Route path="/platform-rules" element={<PlatformRules />} />
                  <Route
                    path="/kyc"
                    element={
                      <ProtectedRoute>
                        <KYCVerification />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/settings"
                    element={
                      <ProtectedRoute>
                        <AccountSettings />
                      </ProtectedRoute>
                    }
                  />
                  <Route path="/about-capimax-propshare" element={<AboutCapimaxPropShare />} />
                  <Route path="/faq" element={<FAQ />} />
                  {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </MainLayout>
          </BrowserRouter>
        </TooltipProvider>
      </ReinvestProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
