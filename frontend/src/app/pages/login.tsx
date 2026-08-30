import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { LockKeyhole, UserRound, ArrowRight, Fingerprint, Network, FileSearch, ShieldCheck } from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { isMockMode } from "@/api";
import { Brand } from "@/components/layout/brand";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useDocumentTitle } from "@/hooks/ui";

const DEMO_ACCOUNTS = [
  { username: "admin", password: "admin-dev-password", role: "Administrator" },
  { username: "investigator", password: "investigator-dev-password", role: "Investigator" },
  { username: "analyst", password: "analyst-demo-password", role: "Analyst" },
  { username: "viewer", password: "viewer-demo-password", role: "Viewer" },
];

const CAPABILITIES = [
  { icon: Network, title: "Knowledge graph", text: "Explore every call, transfer, vehicle and association on a single canvas." },
  { icon: FileSearch, title: "Evidence-to-finding", text: "Trace a finding back to its source records and provenance." },
  { icon: ShieldCheck, title: "Role-scoped by design", text: "Every screen respects the permissions of the signed-in profile." },
];

function fill(name: string) {
  const matches = DEMO_ACCOUNTS.find((a) => a.username === name);
  return matches ? { username: matches.username, password: matches.password } : null;
}

export default function LoginPage() {
  useDocumentTitle("Sign in");
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const status = useAuthStore((s) => s.status);
  const login = useAuthStore((s) => s.login);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (status === "authenticated") return <Navigate to="/app" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!username.trim() || !password) {
      setError("Enter both a username and password.");
      return;
    }
    setBusy(true);
    try {
      await login(username.trim(), password);
      navigate(location.state?.from ?? "/app", { replace: true });
    } catch (err) {
      setError((err as { message?: string }).message ?? "Unable to sign in. Check your credentials.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="flex flex-col justify-center px-6 py-10 sm:px-12 lg:px-16"
      >
        <Brand className="mb-10" />

        <div className="max-w-sm">
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-accent/80">Investigation workspace</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">Sign in to continue</h1>
          <p className="mt-1.5 text-sm text-dim">Access your cases, evidence and network analysis.</p>

          <form onSubmit={onSubmit} className="mt-8 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="username">Username</Label>
              <div className="relative">
                <UserRound className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dim" />
                <Input
                  id="username"
                  autoComplete="username"
                  autoFocus
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="pl-9"
                  placeholder="e.g. investigator"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dim" />
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pl-9"
                  placeholder="••••••••"
                />
              </div>
            </div>

            {error ? (
              <p role="alert" className="rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical">
                {error}
              </p>
            ) : null}

            <Button type="submit" size="lg" className="w-full" loading={busy}>
              {busy ? "Signing in…" : (
                <>
                  Sign in <ArrowRight className="size-4" />
                </>
              )}
            </Button>
          </form>

          {isMockMode ? (
            <Card className="mt-8">
              <p className="px-4 pt-3 text-[11px] font-medium uppercase tracking-wider text-dim">
                Demo accounts — click to fill
              </p>
              <div className="p-2">
                {DEMO_ACCOUNTS.map((account) => (
                  <button
                    key={account.username}
                    type="button"
                    onClick={() => {
                      const creds = fill(account.username);
                      if (creds) {
                        setUsername(creds.username);
                        setPassword(creds.password);
                        setError(null);
                      }
                    }}
                    className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left transition-colors hover:bg-surface-2"
                  >
                    <span className="text-sm text-foreground">{account.role}</span>
                    <span className="font-mono text-[11px] text-dim">{account.username}</span>
                  </button>
                ))}
              </div>
            </Card>
          ) : null}
        </div>
      </motion.div>

      <div className="relative hidden overflow-hidden border-l border-border lg:block">
        <div className="grid-canvas absolute inset-0 opacity-60" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(214,161,78,0.12),transparent_55%)]" />
        <div className="relative z-10 flex h-full flex-col justify-end gap-8 p-12">
          {CAPABILITIES.map((c, i) => (
            <motion.div
              key={c.title}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 + i * 0.12, duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
              className="max-w-md"
            >
              <div className="mb-2 flex items-center gap-2">
                <c.icon className="size-4 text-accent" />
                <h3 className="text-sm font-medium text-foreground">{c.title}</h3>
              </div>
              <p className="text-sm leading-relaxed text-dim">{c.text}</p>
            </motion.div>
          ))}

          <div className="flex items-center gap-4 border-t border-border pt-6">
            <Fingerprint className="size-8 text-accent/40" />
            <p className="max-w-md text-xs leading-relaxed text-dim">
              Deterministic demo data — reload-safe, seeded offline. Switch to the live adapter with{" "}
              <code className="font-mono text-muted">VITE_USE_MOCK_API=false</code>.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}