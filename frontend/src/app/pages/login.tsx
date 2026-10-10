import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight,
  Eye,
  EyeOff,
  FileSearch,
  Fingerprint,
  LockKeyhole,
  Network,
  ShieldCheck,
  UserRound,
} from "lucide-react";
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
  { username: "viewer", password: "viewer-dev-password", role: "Viewer" },
];

const CAPABILITIES = [
  { icon: Network, title: "Connected intelligence", text: "Bring cases, entities, evidence and relationships into one investigation workspace." },
  { icon: FileSearch, title: "Evidence with provenance", text: "Follow findings back to source records and retain a clear investigative trail." },
  { icon: ShieldCheck, title: "Role-aware access", text: "Access to investigative information is presented according to the signed-in profile." },
];

function fill(name: string) {
  const account = DEMO_ACCOUNTS.find((item) => item.username === name);
  return account ? { username: account.username, password: account.password } : null;
}

export default function LoginPage() {
  useDocumentTitle("Sign in");
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const status = useAuthStore((state) => state.status);
  const login = useAuthStore((state) => state.login);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (status === "authenticated") return <Navigate to="/app" replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!username.trim() || !password) {
      setError("Enter your username and password to continue.");
      return;
    }
    setBusy(true);
    try {
      await login(username.trim(), password);
      navigate(location.state?.from ?? "/app", { replace: true });
    } catch (err) {
      setError((err as { message?: string }).message ?? "Unable to sign in. Check your credentials and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f6f8fa] text-foreground lg:grid lg:grid-cols-[minmax(430px,0.9fr)_minmax(0,1.1fr)]">
      <section className="relative flex min-h-screen flex-col border-r border-border bg-surface">
        <div className="gov-top-rule" aria-hidden="true" />
        <div className="mx-auto flex w-full max-w-xl flex-1 flex-col px-6 py-7 sm:px-10 lg:px-14 xl:px-20">
          <div className="flex items-center justify-between">
            <Brand />
            <span className="hidden items-center gap-1.5 text-[11px] font-medium text-muted sm:flex">
              <span className="size-1.5 rounded-full bg-success" aria-hidden="true" /> Secure service
            </span>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
            className="my-auto py-14"
          >
            <div className="max-w-md">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">Investigation workspace</p>
              <h1 className="mt-3 text-3xl font-semibold tracking-[-0.025em] text-foreground sm:text-[2.15rem]">Sign in to CyberSaarthi</h1>
              <p className="mt-3 max-w-sm text-sm leading-6 text-muted">Access your assigned cases, evidence and investigation intelligence.</p>
            </div>

            <form onSubmit={onSubmit} className="mt-9 max-w-md space-y-5" noValidate>
              <div className="space-y-2">
                <Label htmlFor="username" className="text-sm text-foreground">Username</Label>
                <div className="relative">
                  <UserRound className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-dim" aria-hidden="true" />
                  <Input
                    id="username"
                    autoComplete="username"
                    autoFocus
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    className="h-11 rounded-lg bg-surface pl-10 shadow-sm focus:ring-2 focus:ring-accent/15"
                    placeholder="Enter your username"
                    aria-invalid={Boolean(error)}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="password" className="text-sm text-foreground">Password</Label>
                  <span className="text-[11px] text-muted">Keep your credentials confidential</span>
                </div>
                <div className="relative">
                  <LockKeyhole className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-dim" aria-hidden="true" />
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className="h-11 rounded-lg bg-surface pl-10 pr-11 shadow-sm focus:ring-2 focus:ring-accent/15"
                    placeholder="Enter your password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((visible) => !visible)}
                    className="absolute right-2 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
              </div>

              {error ? (
                <div role="alert" className="flex gap-3 rounded-lg border border-critical/25 bg-critical/5 px-3.5 py-3 text-sm text-critical">
                  <span className="mt-0.5 size-2 shrink-0 rounded-full bg-critical" aria-hidden="true" />
                  <span>{error}</span>
                </div>
              ) : null}

              <Button type="submit" size="lg" className="h-11 w-full rounded-lg" loading={busy}>
                {busy ? "Signing in…" : <>Sign in <ArrowRight className="size-4" /></>}
              </Button>
            </form>

            <p className="mt-6 max-w-md text-center text-sm text-muted sm:text-left">
              Need an account? <Link to="/register" className="font-semibold text-accent hover:text-accent-strong hover:underline">Request access</Link>
            </p>

            {isMockMode ? (
              <Card className="mt-8 max-w-md overflow-hidden border-dashed bg-surface-2 shadow-none">
                <div className="border-b border-border px-4 py-3">
                  <p className="text-xs font-semibold text-foreground">Development accounts</p>
                  <p className="mt-0.5 text-[11px] text-muted">Available only in mock mode.</p>
                </div>
                <div className="grid grid-cols-2 gap-px bg-border">
                  {DEMO_ACCOUNTS.map((account) => (
                    <button
                      key={account.username}
                      type="button"
                      onClick={() => {
                        const credentials = fill(account.username);
                        if (credentials) {
                          setUsername(credentials.username);
                          setPassword(credentials.password);
                          setError(null);
                        }
                      }}
                      className="flex items-center justify-between bg-surface px-3 py-2.5 text-left hover:bg-surface-2 focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent"
                    >
                      <span className="text-xs font-medium text-foreground">{account.role}</span>
                      <span className="font-mono text-[10px] text-muted">{account.username}</span>
                    </button>
                  ))}
                </div>
              </Card>
            ) : null}
          </motion.div>

          <footer className="border-t border-border pt-4 text-[11px] leading-5 text-muted">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <span>Authorized access only</span><span>•</span><span>Use of this system may be monitored</span>
            </div>
          </footer>
        </div>
      </section>

      <section className="relative hidden overflow-hidden bg-[#f0f4f7] lg:block" aria-label="Platform overview">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_20%,rgba(23,74,126,0.10),transparent_34%),radial-gradient(circle_at_20%_80%,rgba(22,133,74,0.07),transparent_30%)]" />
        <div className="absolute inset-0 opacity-50 [background-image:linear-gradient(rgba(23,74,126,0.055)_1px,transparent_1px),linear-gradient(90deg,rgba(23,74,126,0.055)_1px,transparent_1px)] [background-size:44px_44px]" />
        <div className="relative flex h-full flex-col justify-between p-12 xl:p-16">
          <div className="max-w-lg">
            <div className="inline-flex items-center gap-2 rounded-full border border-accent/15 bg-surface/80 px-3 py-1.5 text-[11px] font-semibold text-accent shadow-sm backdrop-blur">
              <ShieldCheck className="size-3.5" /> Secure investigative environment
            </div>
            <h2 className="mt-8 max-w-xl text-4xl font-semibold leading-[1.08] tracking-[-0.035em] text-foreground xl:text-5xl">One workspace for the investigative trail.</h2>
            <p className="mt-5 max-w-lg text-sm leading-7 text-muted">A structured workspace for connecting people, events, evidence and findings without losing the context behind each conclusion.</p>
          </div>

          <div className="grid max-w-2xl gap-3 sm:grid-cols-3">
            {CAPABILITIES.map((item, index) => (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.12 + index * 0.08, duration: 0.35 }}
                className="rounded-xl border border-border bg-surface/85 p-4 shadow-[0_12px_30px_rgba(25,45,65,0.06)] backdrop-blur"
              >
                <div className="grid size-9 place-items-center rounded-lg bg-accent-soft text-accent">
                  <item.icon className="size-4" />
                </div>
                <h3 className="mt-4 text-sm font-semibold text-foreground">{item.title}</h3>
                <p className="mt-1.5 text-xs leading-5 text-muted">{item.text}</p>
              </motion.div>
            ))}
          </div>

          <div className="flex max-w-xl items-start gap-3 border-t border-border/80 pt-5 text-xs leading-5 text-muted">
            <Fingerprint className="mt-0.5 size-4 shrink-0 text-accent" />
            <p><span className="font-semibold text-foreground">Security principle:</span> only use accounts and information you are authorized to access.</p>
          </div>
        </div>
      </section>
    </main>
  );
}
