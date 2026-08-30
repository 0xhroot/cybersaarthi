import { Link, useParams } from "react-router-dom";
import { ArrowRight, Network, Users, Layers, Bell } from "lucide-react";
import { useAnalyticsSummary, useNetworkDna, usePriorities, useFindings, useTimeline } from "@/hooks/queries";
import { PageContainer } from "@/components/layout/page";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SeverityBadge, FindingStatusBadge, ProfileTierBadge, PriorityBadge } from "@/components/status";
import { Skeleton } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/error-state";
import { Progress } from "@/components/ui/loading";
import { useDocumentTitle } from "@/hooks/ui";
import { timeAgoShort } from "@/lib/utils";

function StatTile({ label, value, icon: Icon, accent }: { label: string; value: string | number; icon: typeof Network; accent: string }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg border bg-surface-2" style={{ color: accent, borderColor: "var(--color-border)" }}>
          <Icon className="size-4" />
        </span>
        <div className="min-w-0">
          <p className="tabular text-xl font-semibold tracking-tight text-foreground">{value}</p>
          <p className="truncate text-[11px] uppercase tracking-wider text-dim">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export default function CaseOverviewPage() {
  const { caseId = "" } = useParams();
  useDocumentTitle("Overview");

  const summary = useAnalyticsSummary(caseId);
  const dna = useNetworkDna(caseId);
  const priorities = usePriorities(caseId);
  const findings = useFindings(caseId, { limit: 5 });
  const timeline = useTimeline(caseId);

  const data = summary.data;

  return (
    <PageContainer>
      {summary.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[76px]" />
          ))}
        </div>
      ) : summary.isError ? (
        <Card>
          <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Entities" value={data?.entity_count ?? 0} icon={Users} accent="var(--color-info)" />
          <StatTile label="Relationships" value={data?.relationship_count ?? 0} icon={Network} accent="var(--color-accent)" />
          <StatTile label="Communities" value={data?.community_count ?? 0} icon={Layers} accent="var(--color-success)" />
          <StatTile label="Findings" value={findings.data?.total ?? 0} icon={Bell} accent="var(--color-critical)" />
        </div>
      )}

      <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {/* Findings by severity */}
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Findings by severity</CardTitle>
            <Link to={`/app/cases/${caseId}/findings`} className="text-xs text-accent hover:text-accent-strong">
              View all
            </Link>
          </CardHeader>
          <CardContent>
            {summary.isLoading ? (
              <Skeleton className="h-32" />
            ) : data ? (
              <div className="space-y-3">
                {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((severity) => {
                  const count = data.findings_by_severity[severity] ?? 0;
                  const total = Object.values(data.findings_by_severity).reduce((a, b) => a + b, 0) || 1;
                  return (
                    <div key={severity} className="flex items-center gap-3">
                      <div className="w-24 shrink-0">
                        <SeverityBadge value={severity} />
                      </div>
                      <div className="flex-1">
                        <Progress value={(count / total) * 100} tone={severity === "LOW" ? "info" : (severity.toLowerCase() as "critical" | "high" | "medium")} />
                      </div>
                      <span className="tabular w-8 text-right text-xs text-dim">{count}</span>
                    </div>
                  );
                })}
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* Recent findings */}
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Recent findings</CardTitle>
            <Link to={`/app/cases/${caseId}/findings`} className="text-xs text-accent hover:text-accent-strong">
              All
            </Link>
          </CardHeader>
          <CardContent>
            {findings.isLoading ? (
              <Skeleton className="h-32" />
            ) : (findings.data?.items ?? []).length === 0 ? (
              <p className="py-6 text-center text-xs text-dim">No findings recorded yet.</p>
            ) : (
              <div className="divide-y divide-border">
                {(findings.data?.items ?? []).map((f) => (
                  <Link
                    key={f.id}
                    to={`/app/cases/${caseId}/findings/${f.id}`}
                    className="flex items-center gap-3 py-2.5 transition-colors hover:bg-surface-2/70"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-foreground">{f.title}</p>
                      <p className="mt-0.5 text-[11px] text-dim">
                        {f.finding_type.replace("_", " ")} · {timeAgoShort(f.created_at)}
                      </p>
                    </div>
                    <SeverityBadge value={f.severity} />
                    <FindingStatusBadge value={f.status} />
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2 sm:grid-cols-1">
        {/* Network DNA */}
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Network DNA</CardTitle>
            <Link to={`/app/cases/${caseId}/analytics`} className="text-xs text-accent hover:text-accent-strong">
              Analytics
            </Link>
          </CardHeader>
          <CardContent>
            {dna.isLoading ? (
              <Skeleton className="h-40" />
            ) : dna.data?.length ? (
              <div className="space-y-2.5">
                {(dna.data ?? []).slice(0, 5).map((p) => (
                  <div key={p.entity_id} className="flex items-center gap-3">
                    <ProfileTierBadge value={p.tier} />
                    <span className="min-w-0 flex-1 truncate text-sm text-foreground">{p.display_value}</span>
                    <span className="tabular text-xs text-dim">{Math.round(p.overall_score * 100)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="py-6 text-center text-xs text-dim">Run analytics to build profiles.</p>
            )}
          </CardContent>
        </Card>

        {/* Priority queue */}
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Priority queue</CardTitle>
            <Link to={`/app/cases/${caseId}/analytics`} className="text-xs text-accent hover:text-accent-strong">
              Analytics
            </Link>
          </CardHeader>
          <CardContent>
            {priorities.isLoading ? (
              <Skeleton className="h-40" />
            ) : priorities.data?.length ? (
              <div className="space-y-2.5">
                {(priorities.data ?? []).slice(0, 5).map((p) => (
                  <div key={p.entity_id}>
                    <div className="flex items-center gap-3">
                      <PriorityBadge value={p.tier} />
                      <span className="min-w-0 flex-1 truncate text-sm text-foreground">{p.display_value}</span>
                    </div>
                    <div className="mt-1.5 ml-11">
                      <Progress value={(p.priority_score ?? 0) * 100} tone={p.tier === "CRITICAL" ? "critical" : p.tier === "HIGH" ? "high" : p.tier === "MEDIUM" ? "medium" : "info"} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="py-6 text-center text-xs text-dim">No priority queue yet.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent activity */}
      <div className="mt-5">
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Recent activity</CardTitle>
            <Link to={`/app/cases/${caseId}/timeline`} className="text-xs text-accent hover:text-accent-strong">
              <span className="inline-flex items-center gap-1">
                Full timeline <ArrowRight className="size-3.5" />
              </span>
            </Link>
          </CardHeader>
          <CardContent>
            {timeline.isLoading ? (
              <Skeleton className="h-24" />
            ) : (timeline.data ?? []).length === 0 ? (
              <p className="py-4 text-center text-xs text-dim">
                Timeline is only visible to roles with audit access.
              </p>
            ) : (
              <div className="divide-y divide-border">
                {(timeline.data ?? []).slice(0, 5).map((e) => (
                  <div key={e.id} className="flex items-start gap-3 py-2">
                    <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-accent/70" />
                    <p className="min-w-0 flex-1 truncate text-sm text-foreground">{e.action}</p>
                    <span className="shrink-0 text-[11px] text-dim">{timeAgoShort(e.created_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}