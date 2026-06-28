import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Download, Smartphone, CheckCircle2, Share, Plus, MoreVertical } from "lucide-react";
import { Link } from "react-router-dom";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const InstallApp = () => {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isInstalled, setIsInstalled] = useState(false);
  const [isIOS, setIsIOS] = useState(false);

  useEffect(() => {
    // Check if already installed
    if (window.matchMedia("(display-mode: standalone)").matches) {
      setIsInstalled(true);
    }

    // Check if iOS
    const isIOSDevice = /iPad|iPhone|iPod/.test(navigator.userAgent);
    setIsIOS(isIOSDevice);

    // Listen for install prompt
    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };

    window.addEventListener("beforeinstallprompt", handleBeforeInstall);

    // Listen for successful install
    window.addEventListener("appinstalled", () => {
      setIsInstalled(true);
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
      setIsInstalled(true);
    }
    setDeferredPrompt(null);
  };

  const features = [
    "Quick access from your home screen",
    "Works offline - view your portfolio anytime",
    "Fast loading - native app experience",
    "Push notifications for investment updates",
    "Secure biometric authentication",
  ];

  if (isInstalled) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="max-w-md w-full text-center">
          <CardHeader>
            <div className="mx-auto w-20 h-20 mb-4">
              <img src="/icon-512.png" alt="CapiMax PropShare" className="w-full h-full rounded-2xl shadow-lg" />
            </div>
            <CardTitle className="text-2xl text-primary">App Installed!</CardTitle>
            <CardDescription>
              CapiMax PropShare is now installed on your device. You can access it from your home screen.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-center gap-2 text-success mb-6">
              <CheckCircle2 className="h-5 w-5" />
              <span className="font-medium">Ready to use</span>
            </div>
            <Link to="/">
              <Button className="w-full">Open App</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary/5 via-background to-accent/5 pt-24 pb-12 px-4">
      <div className="container mx-auto max-w-2xl">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="mx-auto w-24 h-24 mb-6">
            <img src="/icon-512.png" alt="CapiMax PropShare" className="w-full h-full rounded-3xl shadow-xl" />
          </div>
          <h1 className="text-3xl md:text-4xl font-bold text-foreground mb-3">
            Install CapiMax PropShare
          </h1>
          <p className="text-muted-foreground text-lg">
            Get the full mobile experience with our installable app
          </p>
        </div>

        {/* Features */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Smartphone className="h-5 w-5 text-primary" />
              App Features
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {features.map((feature, index) => (
                <li key={index} className="flex items-center gap-3">
                  <CheckCircle2 className="h-5 w-5 text-success flex-shrink-0" />
                  <span className="text-foreground">{feature}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        {/* Install Instructions */}
        {isIOS ? (
          <Card className="mb-8">
            <CardHeader>
              <CardTitle>Install on iPhone/iPad</CardTitle>
              <CardDescription>Follow these steps to add to your home screen</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-start gap-4 p-4 bg-secondary/50 rounded-lg">
                <div className="w-8 h-8 bg-primary text-primary-foreground rounded-full flex items-center justify-center font-bold flex-shrink-0">
                  1
                </div>
                <div>
                  <p className="font-medium">Tap the Share button</p>
                  <p className="text-sm text-muted-foreground flex items-center gap-1">
                    Look for the <Share className="h-4 w-4" /> icon at the bottom of Safari
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-4 p-4 bg-secondary/50 rounded-lg">
                <div className="w-8 h-8 bg-primary text-primary-foreground rounded-full flex items-center justify-center font-bold flex-shrink-0">
                  2
                </div>
                <div>
                  <p className="font-medium">Scroll and tap "Add to Home Screen"</p>
                  <p className="text-sm text-muted-foreground flex items-center gap-1">
                    Look for the <Plus className="h-4 w-4" /> icon in the menu
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-4 p-4 bg-secondary/50 rounded-lg">
                <div className="w-8 h-8 bg-primary text-primary-foreground rounded-full flex items-center justify-center font-bold flex-shrink-0">
                  3
                </div>
                <div>
                  <p className="font-medium">Tap "Add" to confirm</p>
                  <p className="text-sm text-muted-foreground">
                    The app will appear on your home screen
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        ) : deferredPrompt ? (
          <Card className="mb-8">
            <CardContent className="pt-6">
              <Button onClick={handleInstall} size="lg" className="w-full gap-2">
                <Download className="h-5 w-5" />
                Install CapiMax PropShare
              </Button>
            </CardContent>
          </Card>
        ) : (
          <Card className="mb-8">
            <CardHeader>
              <CardTitle>Install on Android</CardTitle>
              <CardDescription>Follow these steps to add to your home screen</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-start gap-4 p-4 bg-secondary/50 rounded-lg">
                <div className="w-8 h-8 bg-primary text-primary-foreground rounded-full flex items-center justify-center font-bold flex-shrink-0">
                  1
                </div>
                <div>
                  <p className="font-medium">Tap the menu button</p>
                  <p className="text-sm text-muted-foreground flex items-center gap-1">
                    Look for <MoreVertical className="h-4 w-4" /> in Chrome
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-4 p-4 bg-secondary/50 rounded-lg">
                <div className="w-8 h-8 bg-primary text-primary-foreground rounded-full flex items-center justify-center font-bold flex-shrink-0">
                  2
                </div>
                <div>
                  <p className="font-medium">Tap "Install app" or "Add to Home screen"</p>
                  <p className="text-sm text-muted-foreground">
                    The option may vary by browser
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-4 p-4 bg-secondary/50 rounded-lg">
                <div className="w-8 h-8 bg-primary text-primary-foreground rounded-full flex items-center justify-center font-bold flex-shrink-0">
                  3
                </div>
                <div>
                  <p className="font-medium">Confirm installation</p>
                  <p className="text-sm text-muted-foreground">
                    The app will appear on your home screen
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Back to app */}
        <div className="text-center">
          <Link to="/">
            <Button variant="outline">Continue in Browser</Button>
          </Link>
        </div>
      </div>
    </div>
  );
};

export default InstallApp;
