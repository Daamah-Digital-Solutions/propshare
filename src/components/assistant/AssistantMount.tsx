import { useEffect, useState } from "react";
import ChatWidget from "@/components/chat/ChatWidget";
import AssistantWidget from "@/components/assistant/AssistantWidget";
import { useAuth } from "@/contexts/AuthContext";
import { ASSISTANT_V2_FLAG, assistantApi, type AssistantStatus } from "@/lib/assistantApi";

/**
 * Feature-flag coexistence (plan §6): the new in-platform assistant mounts ONLY when the
 * build flag VITE_ASSISTANT_V2 is on AND the backend says this caller may use it (or must
 * first give consent). In every other case — flag off, kill switch, rollout, provider not
 * configured — the legacy n8n widget renders exactly as before. Removing the legacy widget
 * is a separate, owner-confirmed task.
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
  if (status === undefined) return null; // deciding; avoid flashing the wrong widget
  if (status && (status.enabled || (isAuthenticated && status.consent_required))) {
    return <AssistantWidget status={status} />;
  }
  return <ChatWidget />;
}

export default AssistantMount;
