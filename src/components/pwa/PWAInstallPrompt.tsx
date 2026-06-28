import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { X, Download, Smartphone } from "lucide-react";
import { cn } from "@/lib/utils";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const PWAInstallPrompt = () => {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);
  const [isIOS, setIsIOS] = useState(false);
  const [showIOSPrompt, setShowIOSPrompt] = useState(false);

  useEffect(() => {
    // Check if already installed
    if (window.matchMedia("(display-mode: standalone)").matches) {
      return;
    }

    // Check if dismissed recently (within 7 days)
    const dismissedAt = localStorage.getItem("pwa-prompt-dismissed");
    if (dismissedAt) {
      const daysSinceDismissed = (Date.now() - parseInt(dismissedAt)) / (1000 * 60 * 60 * 24);
      if (daysSinceDismissed < 7) return;
    }

    // Check if iOS
    const isIOSDevice =
      /iPad|iPhone|iPod/.test(navigator.userAgent) &&
      !(window as Window & { MSStream?: unknown }).MSStream;
    setIsIOS(isIOSDevice);

    if (isIOSDevice) {
      // Show iOS prompt after a delay
      const timer = setTimeout(() => setShowIOSPrompt(true), 3000);
      return () => clearTimeout(timer);
    }

    // Listen for install prompt (Android/Desktop)
    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
      // Show prompt after a short delay
      setTimeout(() => setShowPrompt(true), 2000);
    };

    window.addEventListener("beforeinstallprompt", handleBeforeInstall);

    // Listen for successful install
    window.addEventListener("appinstalled", () => {
      setShowPrompt(false);
      setDeferredPrompt(null);
    });

    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstall);
    };
  }, []);

  const handleInstall = async () => {
    if (!deferredPrompt) return;

    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;

    if (outcome === "accepted") {
      setShowPrompt(false);
    }
    setDeferredPrompt(null);
  };

  const handleDismiss = () => {
    setShowPrompt(false);
    setShowIOSPrompt(false);
    localStorage.setItem("pwa-prompt-dismissed", Date.now().toString());
  };

  // Android/Desktop Install Prompt
  if (showPrompt && deferredPrompt) {
    return (
      <div className={cn(
        "fixed bottom-20 lg:bottom-4 left-4 right-4 z-50 animate-fade-up",
        "max-w-md mx-auto"
      )}>
        <div className="bg-card border border-border rounded-2xl shadow-xl p-4">
          <div className="flex items-start gap-3">
            <div className="w-12 h-12 rounded-xl overflow-hidden flex-shrink-0">
              <img src="/icon-192.png" alt="CapiMax PropShare" className="w-full h-full object-cover" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="font-semibold text-foreground text-sm">Install CapiMax PropShare</h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Add to home screen for quick access & offline use
              </p>
              <div className="flex gap-2 mt-3">
                <Button size="sm" onClick={handleInstall} className="gap-1.5">
                  <Download className="h-4 w-4" />
                  Install
                </Button>
                <Button size="sm" variant="ghost" onClick={handleDismiss}>
                  Not now
                </Button>
              </div>
            </div>
            <button 
              onClick={handleDismiss}
              className="text-muted-foreground hover:text-foreground p-1"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  // iOS Install Prompt
  if (showIOSPrompt && isIOS) {
    return (
      <div className={cn(
        "fixed bottom-20 lg:bottom-4 left-4 right-4 z-50 animate-fade-up",
        "max-w-md mx-auto"
      )}>
        <div className="bg-card border border-border rounded-2xl shadow-xl p-4">
          <div className="flex items-start gap-3">
            <div className="w-12 h-12 rounded-xl overflow-hidden flex-shrink-0">
              <img src="/icon-192.png" alt="CapiMax PropShare" className="w-full h-full object-cover" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="font-semibold text-foreground text-sm">Install CapiMax PropShare</h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Tap <span className="inline-flex items-center align-middle mx-0.5 px-1 py-0.5 bg-secondary rounded text-foreground">
                  <Smartphone className="h-3 w-3 mr-0.5" /> Share
                </span> then <strong>"Add to Home Screen"</strong>
              </p>
              <div className="flex gap-2 mt-3">
                <Button size="sm" variant="outline" onClick={handleDismiss}>
                  Got it
                </Button>
              </div>
            </div>
            <button 
              onClick={handleDismiss}
              className="text-muted-foreground hover:text-foreground p-1"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return null;
};

export default PWAInstallPrompt;
