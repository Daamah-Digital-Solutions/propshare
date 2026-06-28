import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, UserPlus, ShieldCheck, Clock } from "lucide-react";
import { useAuth, type UserRole } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { ApiError } from "@/lib/api";
import { requestableRoles, roleLabel } from "@/lib/roles";

/**
 * Self-serve role acquisition (D12). Property Owner is granted instantly;
 * Broker / Liquidity Provider create a pending admin request. On a successful
 * self-serve grant, AuthContext.requestRole() reloads /me, so the sidebar
 * role-switcher appears automatically once the user holds 2+ roles.
 */
export function RoleAccessCard() {
  const { authorizedRoles, requestRole } = useAuth();
  const { toast } = useToast();
  const [pending, setPending] = useState<string | null>(null);

  const options = requestableRoles(authorizedRoles as string[]);

  const handleRequest = async (role: UserRole, label: string) => {
    setPending(role);
    try {
      const res = await requestRole(role);
      if (res.status === "pending_approval") {
        toast({
          title: "Request submitted",
          description: `Your ${label} request is pending admin approval.`,
        });
      } else {
        toast({
          title: "Role added",
          description: `You now have the ${label} role — use the role switcher in the sidebar to switch to it.`,
        });
      }
    } catch (error) {
      toast({
        title: "Couldn't complete the request",
        description: error instanceof ApiError ? error.message : "Please try again.",
        variant: "destructive",
      });
    } finally {
      setPending(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5" />
          Roles &amp; Access
        </CardTitle>
        <CardDescription>
          Add a role to unlock its dashboard. Investor is included by default.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div>
          <p className="text-sm text-muted-foreground mb-2">Your current roles</p>
          <div className="flex flex-wrap gap-2">
            {authorizedRoles.length === 0 ? (
              <span className="text-sm text-muted-foreground">None yet</span>
            ) : (
              authorizedRoles.map((r) => (
                <Badge key={r} variant="secondary">
                  {roleLabel(r)}
                </Badge>
              ))
            )}
          </div>
        </div>

        {options.length === 0 ? (
          <p className="text-sm text-muted-foreground">You hold all available roles.</p>
        ) : (
          <div className="space-y-3">
            {options.map((opt) => (
              <div
                key={opt.role}
                className="flex items-center justify-between gap-4 rounded-lg border border-border p-4"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-foreground">{opt.label}</span>
                    {opt.kind === "approval" && (
                      <Badge variant="outline" className="text-xs">
                        <Clock className="h-3 w-3 mr-1" />
                        Admin approval
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground mt-0.5">{opt.description}</p>
                </div>
                <Button
                  variant={opt.kind === "self-serve" ? "default" : "outline"}
                  size="sm"
                  disabled={pending !== null}
                  onClick={() => handleRequest(opt.role, opt.label)}
                >
                  {pending === opt.role ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <UserPlus className="h-4 w-4 mr-2" />
                      {opt.kind === "self-serve" ? "Become" : "Request"}
                    </>
                  )}
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
