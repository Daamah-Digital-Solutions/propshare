import { useEffect, useState } from "react";

/**
 * Single source of truth for the PWA install flow.
 *
 * The browser's `beforeinstallprompt` event fires ONCE and EARLY (often before a
 * given component mounts), so we capture it at module load and stash it here. Any
 * component — the auto-popup or the sidebar "Install" button — can then trigger the
 * real install via `triggerInstall()`, instead of each re-registering its own
 * listener and racing for the one-shot event.
 */
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let deferred: BeforeInstallPromptEvent | null = null;
let installed = false;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // stop Chrome's mini-infobar; we drive the prompt ourselves
    deferred = e as BeforeInstallPromptEvent;
    emit();
  });
  window.addEventListener("appinstalled", () => {
    deferred = null;
    installed = true;
    emit();
  });
}

export const isStandalone = () =>
  typeof window !== "undefined" &&
  (window.matchMedia("(display-mode: standalone)").matches ||
    (window.navigator as Navigator & { standalone?: boolean }).standalone === true);

export const isIOSDevice = () =>
  typeof navigator !== "undefined" &&
  /iPad|iPhone|iPod/.test(navigator.userAgent) &&
  !(window as Window & { MSStream?: unknown }).MSStream;

export type InstallOutcome = "accepted" | "dismissed" | "ios" | "unavailable";

/** Trigger the native install prompt. Returns how it resolved so the caller can guide
 *  the user when a native prompt isn't available (iOS Safari, or already installed). */
export async function triggerInstall(): Promise<InstallOutcome> {
  if (deferred) {
    await deferred.prompt();
    const { outcome } = await deferred.userChoice;
    if (outcome === "accepted") {
      deferred = null;
      emit();
    }
    return outcome;
  }
  if (isIOSDevice()) return "ios";
  return "unavailable";
}

export function usePwaInstall() {
  const [, bump] = useState(0);
  useEffect(() => {
    const cb = () => bump((n) => n + 1);
    listeners.add(cb);
    return () => {
      listeners.delete(cb);
    };
  }, []);
  return {
    canInstall: deferred !== null,
    isIOS: isIOSDevice(),
    isInstalled: installed || isStandalone(),
    triggerInstall,
  };
}
