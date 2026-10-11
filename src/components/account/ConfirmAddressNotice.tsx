import { MailCheck } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { ConfirmEmailButton } from "@/components/account/ConfirmEmailButton";

/**
 * Shown to a signed-in member whose email address is not confirmed yet, on a page where
 * something may have been sent to that address. Said to every such member, whether or not
 * anything waits: what waits for an address is told only to the account that confirmed it.
 */
export function ConfirmAddressNotice({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (!user || user.email_verified) return null;
  return (
    <div
      className="flex items-start gap-3 rounded-lg border border-border bg-muted/40 p-4 text-sm"
      data-testid="confirm-address-notice"
    >
      <MailCheck size={18} className="mt-0.5 shrink-0 text-primary" />
      <div>
        <p className="font-semibold text-foreground">Confirm your email address</p>
        <p className="text-muted-foreground mt-1">{children}</p>
        <div className="mt-3">
          <ConfirmEmailButton email={user.email} />
        </div>
      </div>
    </div>
  );
}
