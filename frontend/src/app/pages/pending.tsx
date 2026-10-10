import { Link } from "react-router-dom";
import { ArrowRight, Check, Clock3, Mail, ShieldCheck } from "lucide-react";
import { Brand } from "@/components/layout/brand";
import { useDocumentTitle } from "@/hooks/ui";

export default function PendingPage() {
  useDocumentTitle("Account pending approval");

  return (
    <main className="min-h-screen bg-[#f6f8fa] text-foreground">
      <div className="gov-top-rule" aria-hidden="true" />
      <header className="border-b border-border bg-surface">
        <div className="mx-auto max-w-6xl px-6 py-5 lg:px-8"><Brand /></div>
      </header>
      <div className="mx-auto flex max-w-3xl px-6 py-12 sm:py-16 lg:px-8">
        <section className="w-full rounded-xl border border-border bg-surface p-6 shadow-[0_12px_35px_rgba(25,45,65,0.06)] sm:p-9">
          <div className="flex flex-col gap-7 sm:flex-row sm:items-start">
            <div className="grid size-14 shrink-0 place-items-center rounded-full bg-amber-50 text-amber-700 ring-8 ring-amber-50/60"><Clock3 className="size-6" /></div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-accent">Access request submitted</p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">Your request is awaiting approval</h1>
              <p className="mt-3 max-w-xl text-sm leading-6 text-muted">An administrator needs to review your request and assign the appropriate role before your account can be activated.</p>
            </div>
          </div>

          <div className="mt-9 grid gap-0 border-y border-border sm:grid-cols-3">
            {[{ icon: Check, title: "Request received", text: "Completed" }, { icon: Clock3, title: "Administrator review", text: "Pending" }, { icon: ShieldCheck, title: "Account activation", text: "After approval" }].map((step, index) => (
              <div key={step.title} className={`flex gap-3 px-4 py-4 ${index > 0 ? "border-t border-border sm:border-l sm:border-t-0" : ""}`}>
                <step.icon className={`mt-0.5 size-4 shrink-0 ${index === 0 ? "text-success" : "text-accent"}`} />
                <div><p className="text-xs font-semibold">{step.title}</p><p className="mt-0.5 text-[11px] text-muted">{step.text}</p></div>
              </div>
            ))}
          </div>

          <div className="mt-7 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-border bg-surface-2 p-4"><Mail className="size-4 text-accent" /><h2 className="mt-3 text-sm font-semibold">What happens next?</h2><p className="mt-1.5 text-xs leading-5 text-muted">Once approved, use your registered credentials to sign in. Your available areas will depend on the role assigned to your account.</p></div>
            <div className="rounded-lg border border-border bg-surface-2 p-4"><ShieldCheck className="size-4 text-accent" /><h2 className="mt-3 text-sm font-semibold">Need urgent access?</h2><p className="mt-1.5 text-xs leading-5 text-muted">Contact the administrator responsible for CyberSaarthi access requests.</p></div>
          </div>

          <div className="mt-7 flex flex-wrap items-center gap-4 border-t border-border pt-5">
            <Link to="/login" className="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-4 text-sm font-semibold text-on-accent hover:bg-accent-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2">Back to sign in <ArrowRight className="size-4" /></Link>
          </div>
        </section>
      </div>
    </main>
  );
}
