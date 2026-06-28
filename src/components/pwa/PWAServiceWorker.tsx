import { useEffect, useState } from "react";
import { toast } from "sonner";
import { WifiOff, RefreshCw } from "lucide-react";

const PWAServiceWorker = () => {
  const [swModule, setSwModule] = useState<{
    needRefresh: [boolean, (value: boolean) => void];
    offlineReady: [boolean, (value: boolean) => void];
    updateServiceWorker: (reloadPage?: boolean) => Promise<void>;
  } | null>(null);

  // Defer service worker registration until after initial page load
  useEffect(() => {
    const registerSW = async () => {
      // Wait for the page to be fully loaded and idle
      if ('requestIdleCallback' in window) {
        window.requestIdleCallback(async () => {
          const { useRegisterSW } = await import("virtual:pwa-register/react");
          // We need to use a different approach since hooks can't be called dynamically
        });
      }
    };

    // Only register after initial paint
    const timeoutId = setTimeout(async () => {
      try {
        const { registerSW } = await import("virtual:pwa-register");
        const updateSW = registerSW({
          onRegistered(registration) {
            console.log("SW Registered:", registration);
          },
          onRegisterError(error) {
            console.log("SW registration error:", error);
          },
          onNeedRefresh() {
            toast("New version available", {
              description: "Click update to get the latest features.",
              icon: <RefreshCw className="h-5 w-5" />,
              duration: Infinity,
              action: {
                label: "Update",
                onClick: () => {
                  updateSW(true);
                },
              },
            });
          },
          onOfflineReady() {
            toast.success("App ready for offline use", {
              description: "CapiMax PropShare has been cached and works offline.",
              icon: <WifiOff className="h-5 w-5" />,
              duration: 5000,
            });
          },
        });
      } catch (error) {
        console.log("SW registration error:", error);
      }
    }, 3000); // Delay SW registration by 3 seconds to not block initial load

    return () => clearTimeout(timeoutId);
  }, []);

  return null;
};

export default PWAServiceWorker;
