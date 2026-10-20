import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  BarChart3,
  BellRing,
  CheckCircle2,
  ChevronRight,
  Clock3,
  FileSearch,
  FileText,
  FolderKanban,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { api } from "@/api";
import { useCases } from "@/hooks/queries";
import { useAuthStore } from "@/stores/auth";
import { useCan } from "@/lib/permissions";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CaseStatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/loading";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDate } from "@/lib/utils";
import { useDocumentTitle } from "@/hooks/ui";

function buildCaseCountQuery(status: string) {
  return {
    queryKey: ["dashboard", "case-counts", status] as const,
    queryFn: async () => api.cases.list({ status, limit: 1 }).then((list) => list.total),
    staleTime: 60_000,
  };
}

function activityLabel(action: string) {
  return action
    .replace(/\./g, " · ")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function activityTone(action: string) {
  if (action.includes("finding")) return "high" as const;
  if (action.includes("evidence") || action.includes("ingestion")) return "info" as const;
  if (action.includes("auth")) return "success" as const;
  return "accent" as const;
}

function relativeTime(value: string) {
  const diff = Math.max(0, Date.now() - new Date(value).getTime());
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function DashboardPage() {
  useDocumentTitle("Dashboard");
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  const cases = useCases({ limit: 100 });
  const canCreate = useCan("case.create");
  const canAudit = useCan("audit.read");

  const openQuery = useQuery(buildCaseCountQuery("open"));
  const inProgressQuery = useQuery(buildCaseCountQuery("in_progress"));
  const closedQuery = useQuery(buildCaseCountQuery("closed"));
  const auditQuery = useQuery({
    queryKey: ["dashboard", "activity"],
    queryFn: () => api.audit.list({ limit: 8 }),
    enabled: canAudit,
    staleTime: 30_000,
  });

  const items = cases.data?.items ?? [];
  const activeCases = items
    .filter((item) => item.status === "open" || item.status === "in_progress")
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  const focusCase = activeCases[0] ?? items[0] ?? null;
  const totalCases = cases.data?.total ?? items.length;
  const openCount = openQuery.data ?? 0;
  const inProgressCount = inProgressQuery.data ?? 0;
  const closedCount = closedQuery.data ?? 0;
  const attentionCount = openCount + inProgressCount;
  const completion = totalCases > 0 ? Math.round((closedCount / totalCases) * 100) : 0;

  return (
    <PageContainer className="pb-10">
      <PageHeader
        eyebrow="Investigation command centre"
        title={`Good ${new Date().getHours() < 12 ? "morning" : new Date().getHours() < 18 ? "afternoon" : "evening"}, ${user?.username ?? "analyst"}`}
        description="See what needs attention, move into a case, and keep the investigative trail in one place."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={() => navigate("/app/cases")}>
              <Search className="size-4" /> Browse cases
            </Button>
            {canCreate ? (
              <Button onClick={() => navigate("/app/cases?new=1")}>
                <Plus className="size-4" /> New case
              </Button>
            ) : null}
          </div>
        }
      />

      <section className="mt-6 overflow-hidden rounded-xl border border-border bg-surface shadow-[0_10px_35px_rgba(24,33,43,0.06)]">
        <div className="relative grid lg:grid-cols-[1.45fr_0.55fr]">
          <div className="relative p-5 sm:p-7">
            <div className="absolute left-0 top-0 h-1 w-full bg-gradient-to-r from-accent via-[#f28c28] to-[#16824b]" />
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.16em] text-accent">
                  <Sparkles className="size-3.5" /> Current operational focus
                </div>
                <h2 className="mt-3 max-w-2xl text-xl font-bold tracking-tight text-foreground sm:text-2xl">
                  {focusCase ? focusCase.title : "No active investigation"}
                </h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
                  {focusCase?.description ?? "Create or open a case to begin building the investigative record."}
                </p>
              </div>
              {focusCase ? <CaseStatusBadge value={focusCase.status} /> : null}
            </div>

            {focusCase ? (
              <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-3 text-xs text-dim">
                <span className="font-mono text-muted">{focusCase.case_number}</span>
                <span>Updated {formatDate(focusCase.updated_at)}</span>
              </div>
            ) : null}

            <div className="mt-6 flex flex-wrap gap-2">
              {focusCase ? (
                <Button onClick={() => navigate(`/app/cases/${focusCase.id}`)}>
                  Open investigation <ArrowRight className="size-4" />
                </Button>
              ) : canCreate ? (
                <Button onClick={() => navigate("/app/cases?new=1")}>Create first case</Button>
              ) : null}
              <Button variant="ghost" onClick={() => navigate("/app/cases")}>
                View all cases
              </Button>
            </div>
          </div>

          <div className="border-t border-border bg-surface-2/60 p-5 lg:border-l lg:border-t-0 sm:p-7">
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-dim">Workspace pulse</p>
            <div className="mt-4 flex items-end gap-3">
              <span className="text-4xl font-bold tracking-tight text-foreground tabular">{attentionCount}</span>
              <span className="pb-1 text-xs text-muted">active case{attentionCount === 1 ? "" : "s"}</span>
            </div>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-surface-3">
              <div className="h-full bg-accent transition-all" style={{ width: `${Math.min(100, Math.max(8, completion))}%` }} />
            </div>
            {/* The per-status counts live once, in the KPI row below — the
                pulse states the register-level completion fact as a single
                line rather than repeating open/total as mini-cards. */}
            <div className="mt-2 flex justify-between text-[11px] text-dim">
              <span>Completion</span>
              <span className="tabular">{completion}% · {closedCount} of {totalCases} closed</span>
            </div>
          </div>
        </div>
      </section>

      {/* The one place per-status counts appear. "Active workload" used to be
          a fourth card here that only restated open + in-progress — the pulse
          headline already carries that number. */}
      <section className="mt-5 grid gap-3 sm:grid-cols-3">
        <MetricCard label="Open cases" value={openCount} detail="Awaiting investigation activity" icon={<FolderKanban className="size-4" />} tone="high" loading={openQuery.isLoading} />
        <MetricCard label="In progress" value={inProgressCount} detail="Currently being worked" icon={<Activity className="size-4" />} tone="info" loading={inProgressQuery.isLoading} />
        <MetricCard label="Closed" value={closedCount} detail="Completed or resolved" icon={<CheckCircle2 className="size-4" />} tone="success" loading={closedQuery.isLoading} />
      </section>

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.55fr)]">
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border pb-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Attention queue</CardTitle>
              <p className="mt-1 text-xs text-dim">Active cases ordered by most recent update.</p>
            </div>
            <Link to="/app/cases" className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:text-accent-strong">
              Open case register <ArrowRight className="size-3.5" />
            </Link>
          </CardHeader>
          <CardContent className="p-0">
            {cases.isLoading ? (
              <div className="space-y-3 p-4">{[1, 2, 3, 4].map((item) => <Skeleton key={item} className="h-16" />)}</div>
            ) : activeCases.length === 0 ? (
              <EmptyState title="No active cases" description="There are no open or in-progress cases requiring attention right now." />
            ) : (
              <div className="divide-y divide-border">
                {activeCases.slice(0, 6).map((item, index) => (
                  <button
                    key={item.id}
                    type="button"
                    className="group flex w-full items-center gap-4 px-4 py-4 text-left transition-colors hover:bg-surface-2 sm:px-5"
                    onClick={() => navigate(`/app/cases/${item.id}`)}
                  >
                    <div className="flex size-9 shrink-0 items-center justify-center rounded-md border border-border bg-surface-2 text-xs font-bold text-accent">
                      {String(index + 1).padStart(2, "0")}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[10px] text-dim">{item.case_number}</span>
                        <CaseStatusBadge value={item.status} />
                      </div>
                      <p className="mt-1 truncate text-sm font-semibold text-foreground">{item.title}</p>
                    </div>
                    <div className="hidden shrink-0 text-right sm:block">
                      <p className="text-[10px] uppercase tracking-wider text-dim">Updated</p>
                      <p className="mt-1 text-xs text-muted">{formatDate(item.updated_at)}</p>
                    </div>
                    <ChevronRight className="size-4 shrink-0 text-dim transition-transform group-hover:translate-x-0.5 group-hover:text-accent" />
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Quick launch</CardTitle>
              <p className="text-xs text-dim">Move directly to common investigative work.</p>
            </CardHeader>
            <CardContent className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
              <QuickAction icon={<FolderKanban className="size-4" />} label="Case register" description="Review all investigations" onClick={() => navigate("/app/cases")} />
              {focusCase ? <QuickAction icon={<FileSearch className="size-4" />} label="Evidence" description="Review the case record" onClick={() => navigate(`/app/cases/${focusCase.id}/evidence`)} /> : null}
              {focusCase ? <QuickAction icon={<BarChart3 className="size-4" />} label="Analytics" description="Inspect network signals" onClick={() => navigate(`/app/cases/${focusCase.id}/analytics`)} /> : null}
              {focusCase ? <QuickAction icon={<FileText className="size-4" />} label="Reports" description="Generate and download PDFs" onClick={() => navigate(`/app/cases/${focusCase.id}/reports`)} /> : null}
              {canAudit ? <QuickAction icon={<ShieldCheck className="size-4" />} label="Audit trail" description="Review recorded activity" onClick={() => navigate("/app/audit")} /> : null}
            </CardContent>
          </Card>
        </div>
      </div>

      {canAudit ? (
        <Card className="mt-5">
          <CardHeader className="border-b border-border pb-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Recent activity</CardTitle>
              <p className="mt-1 text-xs text-dim">Latest recorded actions from the audit trail.</p>
            </div>
            <Link to="/app/audit" className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:text-accent-strong">
              View audit log <ArrowRight className="size-3.5" />
            </Link>
          </CardHeader>
          <CardContent className="p-0">
            {auditQuery.isLoading ? (
              <div className="grid gap-3 p-4 md:grid-cols-2">{[1, 2, 3, 4].map((item) => <Skeleton key={item} className="h-14" />)}</div>
            ) : auditQuery.data?.items.length ? (
              <div className="grid divide-y divide-border md:grid-cols-2 md:divide-x md:divide-y-0">
                {auditQuery.data.items.slice(0, 8).map((event) => (
                  <div key={event.id} className="flex gap-3 border-b border-border p-4 last:border-b-0 md:nth-[odd]:border-b md:nth-[even]:border-b md:nth-[n+7]:border-b-0">
                    <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-surface-2">
                      <BellRing className="size-3.5 text-accent" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={activityTone(event.action)}>{activityLabel(event.action)}</Badge>
                        <span className="text-[10px] text-dim">{relativeTime(event.created_at)}</span>
                      </div>
                      <p className="mt-1 truncate text-xs text-muted">{String(event.metadata_?.filename ?? event.metadata_?.title ?? event.resource_type)}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-6 text-center text-sm text-muted">No recent audit activity.</div>
            )}
          </CardContent>
        </Card>
      ) : null}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4 text-[11px] text-dim">
        <div className="flex items-center gap-2"><Users className="size-3.5" /> Role-aware workspace</div>
        <div className="flex items-center gap-2"><Clock3 className="size-3.5" /> Data shown from the active application source</div>
      </div>
    </PageContainer>
  );
}

function MetricCard({
  label,
  value,
  detail,
  icon,
  tone,
  loading,
}: {
  label: string;
  value: number;
  detail: string;
  icon: React.ReactNode;
  tone: "accent" | "high" | "info" | "success";
  loading: boolean;
}) {
  if (loading) return <Skeleton className="h-[116px] rounded-xl" />;

  const iconClass = {
    accent: "bg-accent-soft text-accent",
    high: "bg-high/10 text-high",
    info: "bg-info/10 text-info",
    success: "bg-success/10 text-success",
  }[tone];

  return (
    <div className="group rounded-xl border border-border bg-surface p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-border-strong hover:shadow-[0_8px_24px_rgba(24,33,43,0.06)]">
      <div className="flex items-start justify-between gap-3">
        <div className={`grid size-9 place-items-center rounded-md ${iconClass}`}>{icon}</div>
        <span className="text-2xl font-bold tracking-tight tabular text-foreground">{value}</span>
      </div>
      <p className="mt-4 text-xs font-semibold text-foreground">{label}</p>
      <p className="mt-0.5 text-[11px] text-dim">{detail}</p>
    </div>
  );
}

function QuickAction({ icon, label, description, onClick }: { icon: React.ReactNode; label: string; description: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="group flex items-center gap-3 rounded-lg border border-transparent px-2.5 py-2.5 text-left transition-colors hover:border-border hover:bg-surface-2">
      <span className="grid size-8 shrink-0 place-items-center rounded-md bg-accent-soft text-accent">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-xs font-semibold text-foreground">{label}</span>
        <span className="mt-0.5 block truncate text-[10px] text-dim">{description}</span>
      </span>
      <ChevronRight className="size-3.5 shrink-0 text-dim transition-transform group-hover:translate-x-0.5" />
    </button>
  );
}
