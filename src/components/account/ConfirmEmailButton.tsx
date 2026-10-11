import { useState } from "react";
import { MailCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { authApi, ApiError } from "@/lib/api";

/**
 * Sends the signed-in member a fresh link to confirm their email address. The one emailed at
 * sign-up expires, and until the address is confirmed nothing sent to it (a claim, for one) is
 * taken as this account's.
 */
export function ConfirmEmailButton({ email }: { email?: string | null }) {
  const { toast } = useToast();
  const [state, setState] = useState<"idle" | "busy" | "sent">("idle");

  const send = async () => {
    setState("busy");
    try {
      await authApi.resendVerification();
      setState("sent");
      toast({
        title: "Confirmation link sent",
        description: `Open the email we sent${email ? ` to ${email}` : ""} and follow the link.`,
      });
    } catch (e) {
      setState("idle");
      toast({
        title: "Could not send the link",
        description: e instanceof ApiError ? e.message : "Please try again.",
        variant: "destructive",
      });
    }
  };

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="gap-1.5"
      disabled={state !== "idle"}
      onClick={() => void send()}
    >
      <MailCheck size={14} />
      {state === "sent" ? "Link sent" : state === "busy" ? "Sending…" : "Send me the confirmation link"}
    </Button>
  );
}
