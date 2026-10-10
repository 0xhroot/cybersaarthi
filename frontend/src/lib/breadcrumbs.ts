/** Pure breadcrumb helpers shared by the shell and the Breadcrumbs component. */

export interface Crumb {
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

export function parsePathname(pathname: string): Crumb[] {
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

export function hasBreadcrumbs(pathname: string): boolean {
  return parsePathname(pathname).length > 1;
}
