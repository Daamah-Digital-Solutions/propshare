import { useEffect, useState } from "react";
import ChatWidget from "@/components/chat/ChatWidget";
import AssistantWidget from "@/components/assistant/AssistantWidget";
import { useAuth } from "@/contexts/AuthContext";
import { ASSISTANT_V2_FLAG, assistantApi, type AssistantStatus } from "@/lib/assistantApi";

// Reasons the assistant cannot answer THIS caller right now, but the caller can do something
// about (sign in) or should be told (a limit for today): the widget opens and says so.
const SAY_WHY = new Set(["SIGN_IN_REQUIRED", "VISITOR_KEY_REQUIRED", "DAILY_CAP", "BUDGET_EXHAUSTED"]);

/**
 * With the build flag VITE_ASSISTANT_V2 off, the legacy n8n widget renders as before. With it
 * on, the legacy widget NEVER renders: it would send what people type to a different service
 * than the one the Privacy Policy and the assistant notice describe. The new assistant mounts
 * when the backend lets this caller use it (or a signed-in user must first consent), says why
 * when it can't answer for a reason the caller should know, and stays out of sight when it is
 * switched off, not open to this account yet, or the backend cannot be reached.
 */
export function AssistantMount() {
  const { isAuthenticated, isLoading } = useAuth();
  const [status, setStatus] = useState<AssistantStatus | null | undefined>(undefined);

  useEffect(() => {
    if (!ASSISTANT_V2_FLAG || isLoading) return;
    let cancelled = false;
    assistantApi
      .status()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled) setStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, isLoading]);

  if (!ASSISTANT_V2_FLAG) return <ChatWidget />;
  if (!status) return null; // deciding, or unreachable: no chat rather than a different one
  if (status.enabled || (isAuthenticated && status.consent_required)) {
    return <AssistantWidget status={status} />;
  }
  if (status.reason && SAY_WHY.has(status.reason)) return <AssistantWidget status={status} />;
  return null;
}

export default AssistantMount;
