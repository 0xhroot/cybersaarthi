import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { UserRound, AtSign, LockKeyhole, ArrowRight, ShieldCheck } from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { Brand } from "@/components/layout/brand";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { useDocumentTitle } from "@/hooks/ui";

export default function RegisterPage() {
  useDocumentTitle("Request access");
  const navigate = useNavigate();
  const register = useAuthStore((s) => s.register);
  const status = useAuthStore((s) => s.status);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (status === "authenticated") return <Navigate to="/app" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!username.trim() || !email.trim() || !password || !confirm) {
      setError("Complete all fields to request an account.");
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
    <div className="grid min-h-screen place-items-center bg-background px-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-sm"
      >
        <Brand className="mb-10 justify-center" />

        <div className="text-center">
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-accent/80">Request access</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">Create your account</h1>
          <p className="mt-1.5 text-sm text-dim">An administrator will review and approve your request.</p>
        </div>

        <form onSubmit={onSubmit} className="mt-8 space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="reg-username">Username</Label>
            <div className="relative">
              <UserRound className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dim" />
              <Input
                id="reg-username"
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="pl-9"
                placeholder="e.g. newinvestigator"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="reg-email">Work email</Label>
            <div className="relative">
              <AtSign className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dim" />
              <Input
                id="reg-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="pl-9"
                placeholder="you@agency.gov"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="reg-password">Password</Label>
            <div className="relative">
              <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dim" />
              <Input
                id="reg-password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="pl-9"
                placeholder="At least 8 characters"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="reg-confirm">Confirm password</Label>
            <Input
              id="reg-confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Repeat password"
            />
          </div>

          {error ? (
            <p role="alert" className="rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical">
              {error}
            </p>
          ) : null}

          <Button type="submit" size="lg" className="w-full" loading={busy}>
            {busy ? "Requesting access…" : (
              <>
                Request access <ArrowRight className="size-4" />
              </>
            )}
          </Button>
        </form>

        <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-sm text-dim">
          <span>Already have an account?</span>
          <Link to="/login" className="text-accent hover:text-accent-strong">
            Sign in
          </Link>
        </p>

        <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-xs leading-relaxed text-dim">
          <ShieldCheck className="size-3.5 shrink-0 text-accent" />
          Accounts start inactive. You can sign in once an administrator approves your request.
        </p>
      </motion.div>
    </div>
  );
}