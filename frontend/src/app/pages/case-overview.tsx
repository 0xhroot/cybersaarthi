import { Link, useParams } from "react-router-dom";
import { ArrowRight, Network, Users, Layers, Bell, UserPlus, Trash2, ShieldCheck, HeartHandshake } from "lucide-react";
import { useState } from "react";
import {
  useAnalyticsSummary,
  useNetworkDna,
  usePriorities,
  useFindings,
  useTimeline,
  useCaseMembers,
  useAddCaseMember,
  useRemoveCaseMember,
  useVictims,
} from "@/hooks/queries";
import { useCan } from "@/lib/permissions";
import { PageContainer } from "@/components/layout/page";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SeverityBadge, FindingStatusBadge, ProfileTierBadge, PriorityBadge } from "@/components/status";
import { Skeleton } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/error-state";
import { Progress } from "@/components/ui/loading";
import { useDocumentTitle } from "@/hooks/ui";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "@/components/ui/toast";
import { timeAgoShort, shortId } from "@/lib/utils";
import type { CaseMemberRole } from "@/types/domain";

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

function membersMeta(role: CaseMemberRole) {
  return role === "collaborator"
    ? { label: "Collaborator", tone: "info" as const }
    : { label: "Viewer", tone: "neutral" as const };
}

function CaseAccessCard({ caseId }: { caseId: string }) {
  const members = useCaseMembers(caseId);
  const addMember = useAddCaseMember(caseId);
  const removeMember = useRemoveCaseMember(caseId);
  const canManage = useCan("case.update");
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState<CaseMemberRole>("collaborator");

  const submitAdd = async () => {
    if (!userId.trim()) return;
    try {
      await addMember.mutateAsync({ user_id: userId.trim(), role });
      toast({ title: "Member added", description: "Access granted to this case." });
      setUserId("");
      setRole("collaborator");
    } catch (err) {
      toast({ title: "Add failed", description: (err as Error).message });
    }
  };

  const confirmRemove = async (memberId: string) => {
    try {
      await removeMember.mutateAsync(memberId);
      toast({ title: "Member removed", description: "Access revoked from this case." });
    } catch (err) {
      toast({ title: "Remove failed", description: (err as Error).message });
    }
  };

  const list = members.data?.items ?? [];

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="size-4" /> Case access
        </CardTitle>
      </CardHeader>
      <CardContent>
        {members.isLoading ? (
          <div className="space-y-2"><Skeleton className="h-8" /><Skeleton className="h-8" /></div>
        ) : members.isError ? (
          <ErrorState error={members.error} onRetry={() => void members.refetch()} />
        ) : (
          <div className="space-y-3">
            <div className="divide-y divide-border">
              {list.length === 0 ? (
                <p className="py-2 text-xs text-dim">No additional members yet.</p>
              ) : (
                list.map((m) => {
                  const meta = membersMeta(m.role);
                  return (
                    <div key={m.user_id} className="flex items-center gap-3 py-2">
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-mono text-xs text-foreground">{shortId(m.user_id)}</p>
                        <p className="text-[10px] text-dim">since {timeAgoShort(m.created_at)} · role {m.role}</p>
                      </div>
                      <Badge tone={meta.tone}>{meta.label}</Badge>
                      {canManage ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={removeMember.isPending}
                          onClick={() => void confirmRemove(m.user_id)}
                          aria-label="Remove member"
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      ) : null}
                    </div>
                  );
                })
              )}
            </div>

            {canManage ? (
              <div className="rounded-lg border border-border bg-surface-2 p-3">
                <p className="mb-2 text-[11px] uppercase tracking-wider text-dim">Grant access</p>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <input
                    value={userId}
                    onChange={(e) => setUserId(e.target.value)}
                    placeholder="User ID"
                    className="min-w-0 flex-1 rounded-lg border border-border-strong bg-surface px-3 py-1.5 text-xs text-foreground outline-none focus:border-accent"
                  />
                  <select
                    value={role}
                    onChange={(e) => setRole(e.target.value as CaseMemberRole)}
                    className="rounded-lg border border-border-strong bg-surface px-3 py-1.5 text-xs text-foreground outline-none focus:border-accent"
                  >
                    <option value="collaborator">Collaborator</option>
                    <option value="viewer">Viewer</option>
                  </select>
                  <Button size="sm" disabled={addMember.isPending || !userId.trim()} onClick={() => void submitAdd()}>
                    <UserPlus className="size-4" /> Add
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        )}
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
  const victims = useVictims(caseId, { limit: 1 });

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
        <div className="space-y-3">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Entities" value={data?.entity_count ?? 0} icon={Users} accent="var(--color-info)" />
            <StatTile label="Relationships" value={data?.relationship_count ?? 0} icon={Network} accent="var(--color-accent)" />
            <StatTile label="Communities" value={data?.community_count ?? 0} icon={Layers} accent="var(--color-success)" />
            <StatTile label="Findings" value={findings.data?.total ?? 0} icon={Bell} accent="var(--color-critical)" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Victims" value={victims.data?.total ?? 0} icon={HeartHandshake} accent="var(--color-success)" />
          </div>
        </div>
      )}

      <div className="mt-6">
        <CaseAccessCard caseId={caseId} />
      </div>

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