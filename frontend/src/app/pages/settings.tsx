import { useAuthStore } from "@/stores/auth";
import { ALL_PERMISSIONS } from "@/lib/permissions";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Check, Minus } from "lucide-react";
import { isMockMode } from "@/api";

function labelled(permission: string): string {
  return permission
    .split(".")
    .join(" — ")
    .replace(/^./, (c) => c.toUpperCase());
}

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const roles = useAuthStore((s) => s.roles);
  const permissions = useAuthStore((s) => s.permissions);

  const granted = new Set(permissions);
  const roleTone: Record<string, "accent" | "success" | "info" | "neutral"> = {
    ADMIN: "accent",
    INVESTIGATOR: "success",
    ANALYST: "info",
    VIEWER: "neutral",
  };

  const apiLabel = isMockMode ? "Mock adapter (deterministic demo data)" : "Live Harmony API";

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Preferences"
        title="Settings"
        description="Your identity, role and permissions in this workspace."
      />

      <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="space-y-5">
          <Card>
            <CardHeader><CardTitle>Profile</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                <p className="text-[11px] uppercase tracking-wider text-dim">Username</p>
                <p className="mt-0.5 text-foreground">{user?.username ?? "—"}</p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wider text-dim">Email</p>
                <p className="mt-0.5 text-foreground">{user?.email ?? "—"}</p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wider text-dim">Account</p>
                <Badge tone={user?.is_active ? "success" : "neutral"}>{user?.is_active ? "Active" : "Inactive"}</Badge>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wider text-dim">Roles</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {roles.map((role) => (
                    <Badge key={role} tone={roleTone[role] ?? "neutral"}>{role}</Badge>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Data source</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p className="text-foreground">{apiLabel}</p>
              <p className="text-xs leading-relaxed text-dim">
                The UI talks to a single adapter facade. In mock mode everything is deterministic seed data; point
                the app at the Harmony backend with <code className="font-mono">VITE_USE_MOCK_API=false</code>.
              </p>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader><CardTitle>Permissions</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-1">
              {ALL_PERMISSIONS.map((permission) => (
                <div key={permission} className="flex items-center gap-3 border-b border-border/60 py-2 last:border-0">
                  <span className="min-w-0 flex-1 text-xs text-muted">{labelled(permission)}</span>
                  {granted.has(permission) ? (
                    <span className="flex items-center gap-1.5 text-xs text-success">
                      <Check className="size-3.5" /> Granted
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-xs text-dim">
                      <Minus className="size-3.5" /> Denied
                    </span>
                  )}
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-dim">
              Permissions are derived from your backend role and re-evaluated server-side on every request.
            </p>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}