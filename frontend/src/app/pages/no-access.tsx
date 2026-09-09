import { ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";

/** Shown when an authenticated user reaches a route their role cannot open (F03). */
export default function NoAccessPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-2 bg-background px-6 text-center text-foreground">
      <div className="grid size-12 place-items-center rounded-full border border-critical/30 bg-critical/10 text-critical">
        <ShieldAlert className="size-5" aria-hidden />
      </div>
      <p className="mt-1 text-sm font-medium">No access to this section</p>
      <p className="max-w-sm text-xs leading-relaxed text-dim">
        Your role does not permit viewing this area. Contact the case owner if
        you believe this is a mistake.
      </p>
      <Link to="/app" className="text-xs text-accent hover:text-accent-strong">
        Back to dashboard
      </Link>
    </div>
  );
}