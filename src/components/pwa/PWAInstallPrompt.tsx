import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { X, Download, Smartphone } from "lucide-react";
import { cn } from "@/lib/utils";
import { usePwaInstall } from "@/hooks/usePwaInstall";

const DISMISS_KEY = "pwa-prompt-dismissed";

// Was the auto-popup dismissed within the last 7 days?
const dismissedRecently = () => {
  const at = localStorage.getItem(DISMISS_KEY);
  if (!at) return false;
  return (Date.now() - parseInt(at)) / (1000 * 60 * 60 * 24) < 7;
};

const PWAInstallPrompt = () => {
  const { canInstall, isIOS, isInstalled, triggerInstall } = usePwaInstall();
  const [showPrompt, setShowPrompt] = useState(false);
  const [showIOSPrompt, setShowIOSPrompt] = useState(false);

  useEffect(() => {
    if (isInstalled || dismissedRecently()) return;
    // iOS Safari has no beforeinstallprompt — nudge with Share → Add to Home Screen.
    if (isIOS) {
      const t = setTimeout(() => setShowIOSPrompt(true), 3000);
      return () => clearTimeout(t);
    }
    // Android/Desktop: only once the browser has offered an installable prompt.
    if (canInstall) {
      const t = setTimeout(() => setShowPrompt(true), 2000);
      return () => clearTimeout(t);
    }
  }, [canInstall, isIOS, isInstalled]);

  const handleInstall = async () => {
    await triggerInstall();
    setShowPrompt(false);
  };

  const handleDismiss = () => {
    setShowPrompt(false);
    setShowIOSPrompt(false);
    localStorage.setItem(DISMISS_KEY, Date.now().toString());
  };

  // Android/Desktop Install Prompt
  if (showPrompt && canInstall) {
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
