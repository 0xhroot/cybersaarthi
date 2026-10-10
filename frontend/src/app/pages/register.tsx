import { useMemo, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Check, Eye, EyeOff, LockKeyhole, ShieldCheck, UserRound, AtSign } from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { Brand } from "@/components/layout/brand";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { useDocumentTitle } from "@/hooks/ui";

const REQUIREMENTS = [
  { key: "length", label: "At least 8 characters" },
  { key: "match", label: "Passwords match" },
];

export default function RegisterPage() {
  useDocumentTitle("Request access");
  const navigate = useNavigate();
  const register = useAuthStore((state) => state.register);
  const status = useAuthStore((state) => state.status);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const requirements = useMemo(() => ({
    length: password.length >= 8,
    match: password.length > 0 && password === confirm,
  }), [password, confirm]);

  if (status === "authenticated") return <Navigate to="/app" replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!username.trim() || !email.trim() || !password || !confirm) {
      setError("Complete all required fields to request an account.");
      return;
    }
    if (username.trim().length < 3) {
      setError("Username must be at least 3 characters.");
      return;
    }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) {
      setError("Enter a valid email address.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await register({ username: username.trim(), email: email.trim(), password });
      navigate("/pending", { replace: true });
    } catch (err) {
      setError((err as { message?: string }).message ?? "Unable to request an account. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f6f8fa] text-foreground">
      <div className="gov-top-rule" aria-hidden="true" />
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5 lg:px-8">
          <Brand />
          <Link to="/login" className="text-sm font-semibold text-accent hover:text-accent-strong hover:underline">Sign in</Link>
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl gap-12 px-6 py-10 lg:grid-cols-[1fr_420px] lg:px-8 lg:py-16">
        <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="max-w-xl">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">Access request</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.025em] sm:text-4xl">Create your account</h1>
          <p className="mt-4 max-w-lg text-sm leading-6 text-muted">Request access to the CyberSaarthi investigation workspace. An administrator will review your request before your account becomes active.</p>

          <div className="mt-10 space-y-4">
            {[
              ["01", "Submit your details", "Provide the minimum information required to create your account."],
              ["02", "Administrator review", "Your request is reviewed and a role is assigned according to your access requirements."],
              ["03", "Start investigating", "Once approved, sign in to access the areas permitted for your role."],
            ].map(([number, title, text]) => (
              <div key={number} className="flex gap-4 border-t border-border pt-4">
                <span className="font-mono text-xs font-semibold text-accent">{number}</span>
                <div><h2 className="text-sm font-semibold">{title}</h2><p className="mt-1 text-xs leading-5 text-muted">{text}</p></div>
              </div>
            ))}
          </div>
        </motion.section>

        <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="rounded-xl border border-border bg-surface p-6 shadow-[0_12px_35px_rgba(25,45,65,0.06)] sm:p-7">
          <form onSubmit={onSubmit} className="space-y-5" noValidate>
            <div>
              <h2 className="text-lg font-semibold">Account details</h2>
              <p className="mt-1 text-xs leading-5 text-muted">Fields marked with an asterisk are required.</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="reg-username" className="text-sm text-foreground">Username <span className="text-critical">*</span></Label>
              <div className="relative"><UserRound className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-dim" aria-hidden="true" /><Input id="reg-username" autoComplete="username" autoFocus value={username} onChange={(event) => setUsername(event.target.value)} className="h-11 rounded-lg pl-10" placeholder="Choose a username" /></div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="reg-email" className="text-sm text-foreground">Work email <span className="text-critical">*</span></Label>
              <div className="relative"><AtSign className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-dim" aria-hidden="true" /><Input id="reg-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} className="h-11 rounded-lg pl-10" placeholder="name@organisation.gov" /></div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="reg-password" className="text-sm text-foreground">Password <span className="text-critical">*</span></Label>
              <div className="relative"><LockKeyhole className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-dim" aria-hidden="true" /><Input id="reg-password" type={showPassword ? "text" : "password"} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} className="h-11 rounded-lg pl-10 pr-11" placeholder="Create a password" /><button type="button" onClick={() => setShowPassword((visible) => !visible)} className="absolute right-2 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-md text-muted hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button></div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="reg-confirm" className="text-sm text-foreground">Confirm password <span className="text-critical">*</span></Label>
              <div className="relative"><Input id="reg-confirm" type={showConfirm ? "text" : "password"} autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} className="h-11 rounded-lg pr-11" placeholder="Re-enter your password" /><button type="button" onClick={() => setShowConfirm((visible) => !visible)} className="absolute right-2 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-md text-muted hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" aria-label={showConfirm ? "Hide confirmation password" : "Show confirmation password"}>{showConfirm ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button></div>
            </div>

            <div className="rounded-lg bg-surface-2 p-3" aria-live="polite">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Password requirements</p>
              <div className="mt-2 space-y-1.5">
                {REQUIREMENTS.map((item) => {
                  const valid = requirements[item.key as keyof typeof requirements];
                  return <div key={item.key} className={`flex items-center gap-2 text-xs ${valid ? "text-success" : "text-muted"}`}><span className={`grid size-4 place-items-center rounded-full border ${valid ? "border-success bg-success text-on-accent" : "border-border bg-surface"}`}>{valid ? <Check className="size-2.5" /> : null}</span>{item.label}</div>;
                })}
              </div>
            </div>

            {error ? <div role="alert" className="rounded-lg border border-critical/25 bg-critical/5 px-3.5 py-3 text-sm text-critical">{error}</div> : null}

            <Button type="submit" size="lg" className="h-11 w-full rounded-lg" loading={busy}>{busy ? "Requesting access…" : <>Request access <ArrowRight className="size-4" /></>}</Button>
          </form>

          <div className="mt-5 flex gap-2 border-t border-border pt-4 text-[11px] leading-5 text-muted"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-accent" /><p>Accounts begin inactive. You can sign in after an administrator approves your request and assigns a role.</p></div>
        </motion.section>
      </div>
    </main>
  );
}
