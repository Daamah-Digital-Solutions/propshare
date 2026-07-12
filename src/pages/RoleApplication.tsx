import { useMemo, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  ArrowLeft,
  ShieldCheck,
  Clock,
  CheckCircle2,
  Loader2,
  UploadCloud,
  FileText,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { ApiError } from "@/lib/api";
import { ROLE_APPLICATIONS, roleLabel, type RoleDoc } from "@/lib/roles";

/**
 * Task 12 — Broker / Liquidity-Provider join form. Any authenticated user can open this page
 * ("pages open on request"); submitting sends the fields + documents to the admin queue and
 * puts the role into "pending" (which unlocks read-only preview of its dashboards). On admin
 * approval the role is granted automatically.
 */
export default function RoleApplication() {
  const { role = "" } = useParams();
  const navigate = useNavigate();
  const { user, authorizedRoles, pendingRoles, applyForRole, isAuthenticated } = useAuth();
  const spec = ROLE_APPLICATIONS[role];

  const [values, setValues] = useState<Record<string, string>>({});
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const alreadyHas = authorizedRoles.includes(role as never);
  const isPending = pendingRoles.includes(role as never) || done;

  const label = spec ? roleLabel(spec.role) : role;

  const missing = useMemo(() => {
    if (!spec) return [];
    const m: string[] = [];
    for (const f of spec.fields) {
      if (f.required && !(values[f.name] ?? "").trim()) m.push(f.label);
    }
    for (const d of spec.documents) {
      if (d.required && !files[d.name]) m.push(d.label);
    }
    return m;
  }, [spec, values, files]);

  if (!spec) {
    return (
      <div className="container mx-auto px-4 py-16 text-center">
        <h1 className="text-2xl font-bold">Unknown role</h1>
        <p className="text-muted-foreground mt-2">This role doesn't have an application form.</p>
        <Link to="/settings" className="text-primary underline mt-4 inline-block">
          Back to settings
        </Link>
      </div>
    );
  }

  const submit = async () => {
    if (!isAuthenticated) {
      navigate("/auth", { state: { from: `/roles/apply/${role}` } });
      return;
    }
    if (missing.length) {
      toast.error("Please complete the required items", { description: missing.join(", ") });
      return;
    }
    setSubmitting(true);
    try {
      const documents = spec.documents
        .filter((d) => files[d.name])
        .map((d) => ({ label: d.label, file: files[d.name] as File }));
      await applyForRole(spec.role, values, documents);
      setDone(true);
      toast.success("Application submitted", {
        description: `Your ${label} application is now pending admin review.`,
      });
    } catch (err) {
      toast.error("Couldn't submit your application", {
        description: err instanceof ApiError ? err.message : "Please try again.",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-8 max-w-3xl">
        <Link
          to="/settings"
          className="inline-flex items-center gap-2 text-muted-foreground hover:text-foreground mb-6"
        >
          <ArrowLeft size={18} /> Back to settings
        </Link>

        {/* Header */}
        <div className="mb-6">
          <Badge variant="outline" className="border-primary/30 text-primary mb-2">
            <ShieldCheck className="h-3 w-3 mr-1" /> Role activation
          </Badge>
          <h1 className="text-3xl font-bold">{spec.title}</h1>
          <p className="text-muted-foreground mt-2 max-w-2xl">{spec.intro}</p>
        </div>

        {alreadyHas ? (
          <Card>
            <CardContent className="py-10 text-center space-y-3">
              <CheckCircle2 className="h-10 w-10 text-primary mx-auto" />
              <h2 className="text-xl font-semibold">You already hold the {label} role</h2>
              <p className="text-muted-foreground">
                Use the role switcher in the sidebar to switch to it.
              </p>
            </CardContent>
          </Card>
        ) : isPending ? (
          <Card className="border-amber-500/40">
            <CardContent className="py-10 text-center space-y-3">
              <Clock className="h-10 w-10 text-amber-500 mx-auto" />
              <h2 className="text-xl font-semibold">Application pending review</h2>
              <p className="text-muted-foreground max-w-md mx-auto">
                Thanks{user?.full_name ? `, ${user.full_name}` : ""}! Your {label} application has
                been sent to our team. You now have read-only preview access to the {label} area —
                we'll activate the role once it's approved.
              </p>
              <Button variant="outline" onClick={() => setDone(false)}>
                Edit &amp; resubmit
              </Button>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>Application details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Fields */}
              <div className="grid sm:grid-cols-2 gap-4">
                {spec.fields.map((f) => (
                  <div
                    key={f.name}
                    className={f.type === "textarea" ? "sm:col-span-2 space-y-1.5" : "space-y-1.5"}
                  >
                    <Label htmlFor={f.name}>
                      {f.label}
                      {f.required && <span className="text-destructive"> *</span>}
                    </Label>
                    {f.type === "textarea" ? (
                      <Textarea
                        id={f.name}
                        placeholder={f.placeholder}
                        value={values[f.name] ?? ""}
                        onChange={(e) =>
                          setValues((v) => ({ ...v, [f.name]: e.target.value }))
                        }
                      />
                    ) : f.type === "select" ? (
                      <select
                        id={f.name}
                        value={values[f.name] ?? ""}
                        onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                        className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                      >
                        <option value="">Select…</option>
                        {f.options?.map((o) => (
                          <option key={o} value={o}>
                            {o}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <Input
                        id={f.name}
                        type={f.type}
                        placeholder={f.placeholder}
                        value={values[f.name] ?? ""}
                        onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                      />
                    )}
                  </div>
                ))}
              </div>

              {/* Documents */}
              <div className="space-y-3 pt-2">
                <h3 className="text-sm font-semibold text-foreground">Required documents</h3>
                {spec.documents.map((d: RoleDoc) => (
                  <div
                    key={d.name}
                    className="flex items-center justify-between gap-4 rounded-lg border border-border p-3"
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-medium flex items-center gap-2">
                        <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                        {d.label}
                        {d.required && <span className="text-destructive">*</span>}
                      </div>
                      {d.hint && <p className="text-xs text-muted-foreground ml-6">{d.hint}</p>}
                      {files[d.name] && (
                        <p className="text-xs text-primary ml-6 truncate">{files[d.name]?.name}</p>
                      )}
                    </div>
                    <label className="shrink-0 cursor-pointer">
                      <input
                        type="file"
                        className="hidden"
                        accept=".pdf,.png,.jpg,.jpeg,.webp"
                        onChange={(e) =>
                          setFiles((prev) => ({ ...prev, [d.name]: e.target.files?.[0] ?? null }))
                        }
                      />
                      <span className="inline-flex items-center gap-1.5 rounded-md border border-input px-3 py-2 text-sm hover:bg-secondary">
                        <UploadCloud className="h-4 w-4" />
                        {files[d.name] ? "Replace" : "Upload"}
                      </span>
                    </label>
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between gap-4 pt-2">
                <p className="text-xs text-muted-foreground">
                  Documents are shared only with our review team.
                </p>
                <Button onClick={submit} disabled={submitting} className="gap-2">
                  {submitting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <ShieldCheck className="h-4 w-4" />
                  )}
                  Submit application
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
