import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, UserPlus, ShieldCheck, Clock, ArrowRight } from "lucide-react";
import { useAuth, type UserRole } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { ApiError } from "@/lib/api";
import { requestableRoles, roleLabel } from "@/lib/roles";

/**
 * Role acquisition (D12 + Task 12). Property Owner is granted instantly (self-serve). Broker /
 * Liquidity Provider open a full JOIN FORM (fields + documents) that goes to the admin queue;
 * while pending, the user gets read-only preview of that role's area and the badge shows
 * "Pending review". On admin approval the role is granted automatically.
 */
export function RoleAccessCard() {
  const { authorizedRoles, pendingRoles, requestRole } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [pending, setPending] = useState<string | null>(null);

  const options = requestableRoles(authorizedRoles as string[]);

  const handleSelfServe = async (role: UserRole, label: string) => {
    setPending(role);
    try {
      await requestRole(role);
      toast({
        title: "Role added",
        description: `You now have the ${label} role — use the role switcher in the sidebar.`,
      });
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
            {options.map((opt) => {
              const isPending = pendingRoles.includes(opt.role as UserRole);
              return (
                <div
                  key={opt.role}
                  className="flex items-center justify-between gap-4 rounded-lg border border-border p-4"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-foreground">{opt.label}</span>
                      {isPending ? (
                        <Badge variant="outline" className="text-xs border-amber-500/40 text-amber-600">
                          <Clock className="h-3 w-3 mr-1" />
                          Pending review
                        </Badge>
                      ) : (
                        opt.kind === "approval" && (
                          <Badge variant="outline" className="text-xs">
                            <Clock className="h-3 w-3 mr-1" />
                            Admin approval
                          </Badge>
                        )
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mt-0.5">{opt.description}</p>
                  </div>
                  {opt.kind === "self-serve" ? (
                    <Button
                      size="sm"
                      disabled={pending !== null}
                      onClick={() => handleSelfServe(opt.role, opt.label)}
                    >
                      {pending === opt.role ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <>
                          <UserPlus className="h-4 w-4 mr-2" /> Become
                        </>
                      )}
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => navigate(`/roles/apply/${opt.role}`)}
                    >
                      {isPending ? "View application" : "Request activation"}
                      <ArrowRight className="h-4 w-4 ml-2" />
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
