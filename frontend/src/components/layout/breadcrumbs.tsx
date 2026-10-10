import { Link, useLocation } from "react-router-dom";
import { ChevronRight, Home } from "lucide-react";
import { parsePathname } from "@/lib/breadcrumbs";
import { cn } from "@/lib/utils";

export function Breadcrumbs({ className }: { className?: string }) {
  const location = useLocation();
  const crumbs = parsePathname(location.pathname);

  if (crumbs.length <= 1) return null;

  return (
    <nav aria-label="Breadcrumb" className={cn("flex min-w-0 items-center gap-1.5 text-[11px]", className)}>
      <Link to="/app" className="inline-flex shrink-0 items-center gap-1 text-dim hover:text-foreground">
        <Home className="size-3" aria-hidden="true" />
        Home
      </Link>
      {crumbs.slice(1).map((crumb, i) => (
        <span key={`${crumb.label}-${i}`} className="flex min-w-0 items-center gap-1.5">
          <ChevronRight className="size-3 shrink-0 text-border-strong" aria-hidden="true" />
          {crumb.to ? (
            <Link to={crumb.to} className="truncate text-dim hover:text-foreground">
              {crumb.label}
            </Link>
          ) : (
            <span className="truncate font-medium text-muted" aria-current="page">
              {crumb.label}
            </span>
          )}
        </span>
      ))}
    </nav>
  );
}
