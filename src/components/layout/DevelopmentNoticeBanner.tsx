import { useState, useEffect } from "react";
import { AlertTriangle, X } from "lucide-react";

export function DevelopmentNoticeBanner() {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const dismissed = localStorage.getItem("dev-notice-dismissed");
    if (!dismissed) {
      setIsVisible(true);
    }
  }, []);

  const handleDismiss = () => {
    localStorage.setItem("dev-notice-dismissed", "true");
    setIsVisible(false);
  };

  if (!isVisible) return null;

  return (
    <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-2.5">
      <div className="flex items-start justify-between gap-3 max-w-screen-2xl mx-auto">
        <div className="flex items-start gap-2.5 min-w-0">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
          <p className="text-sm text-amber-800 leading-relaxed">
            <span className="font-semibold">Development Notice:</span>{" "}
            This platform is currently under testing and development phase. All current transactions and activities are for demonstration and testing purposes only and do not represent real buying or selling activity. Official operations begin on 01/07/2026.
          </p>
        </div>
        <button
          onClick={handleDismiss}
          className="flex-shrink-0 p-1 rounded-md hover:bg-amber-500/20 transition-colors"
          aria-label="Dismiss notice"
        >
          <X className="h-4 w-4 text-amber-700" />
        </button>
      </div>
    </div>
  );
}
