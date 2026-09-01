import { Link } from "react-router-dom";
import { Hourglass, CheckCircle2 } from "lucide-react";
import { Brand } from "@/components/layout/brand";
import { useDocumentTitle } from "@/hooks/ui";

export default function PendingPage() {
  useDocumentTitle("Account pending approval");

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-6 text-center text-foreground">
      <Brand />
      <div className="grid size-12 place-items-center rounded-full border border-accent/30 bg-accent-soft text-accent-strong">
        <Hourglass className="size-5" aria-hidden />
      </div>
      <h1 className="text-xl font-semibold tracking-tight">Request received</h1>
      <p className="max-w-sm text-sm leading-relaxed text-dim">
        Your account is awaiting administrator approval. You will be able to sign
        in once an administrator activates it and assigns a role.
      </p>
      <div className="mt-2 flex max-w-sm items-start gap-2 rounded-md border border-border bg-surface px-3 py-2 text-left text-xs leading-relaxed text-muted">
        <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-success" />
        <span>
          You cannot sign in until your request is approved. Contact an administrator
          if you need access urgently.
        </span>
      </div>
      <Link to="/login" className="mt-1 text-sm text-accent hover:text-accent-strong">
        Back to sign in
      </Link>
    </div>
  );
}