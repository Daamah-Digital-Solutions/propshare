import { useEffect } from "react";
import { toast } from "sonner";
import { WifiOff } from "lucide-react";

/**
 * PWA service worker — autoUpdate mode. A new deploy's service worker self-activates
 * (skipWaiting + clientsClaim) and virtual:pwa-register reloads the page automatically, so a
 * broken build can never leave users stuck on a cached white screen with an un-clickable
 * "update" prompt. Registration is deferred a few seconds so it never blocks first paint.
 */
const PWAServiceWorker = () => {
  useEffect(() => {
    const timeoutId = setTimeout(async () => {
      try {
        const { registerSW } = await import("virtual:pwa-register");
        registerSW({
          immediate: true,
          onOfflineReady() {
            toast.success("App ready for offline use", {
              description: "CapiMax PropShare has been cached and works offline.",
              icon: <WifiOff className="h-5 w-5" />,
              duration: 5000,
            });
          },
          onRegisteredSW(_swUrl, registration) {
            // Long-lived tabs poll for a fresh SW hourly so fixes reach them without a manual reload.
            if (registration) {
              setInterval(() => void registration.update(), 60 * 60 * 1000);
            }
          },
          onRegisterError(error) {
            console.log("SW registration error:", error);
          },
        });
      } catch (error) {
        console.log("SW registration error:", error);
      }
    }, 3000);

    return () => clearTimeout(timeoutId);
  }, []);

  return null;
};

export default PWAServiceWorker;
