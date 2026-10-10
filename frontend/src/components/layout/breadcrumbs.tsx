import { Link, useLocation } from "react-router-dom";
import { ChevronRight, Home } from "lucide-react";
import { cn } from "@/lib/utils";

interface Crumb {
  label: string;
  to?: string;
}

const LABELS: Record<string, string> = {
  app: "Workspace",
  cases: "Cases",
  entities: "Entities",
  evidence: "Evidence",
  graph: "Network Graph",
  analytics: "Analytics",
  hypotheses: "Hypotheses",
  findings: "Findings",
  victims: "Victims",
  devices: "Field Devices",
  iot: "IoT Devices",
  timeline: "Timeline",
  reports: "Reports",
  audit: "Audit Log",
  users: "User Management",
  settings: "Settings",
};

function humanize(segment: string) {
  return LABELS[segment] ?? segment.replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function parsePathname(pathname: string): Crumb[] {
  const segments = pathname.split("/").filter(Boolean);
  if (segments[0] !== "app") return [];

  const crumbs: Crumb[] = [{ label: "Workspace", to: "/app" }];
  let accum = "/app";

  for (let i = 1; i < segments.length; i += 1) {
    accum += `/${segments[i]}`;
    const isLast = i === segments.length - 1;
    crumbs.push({
      label: humanize(segments[i]),
      to: isLast ? undefined : accum,
    });
  }
  return crumbs;
}

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
