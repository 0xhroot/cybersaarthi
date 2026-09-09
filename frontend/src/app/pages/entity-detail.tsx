import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Network, FileText, Link2 } from "lucide-react";
import { useEntity, useEntityEgo, useNetworkDna } from "@/hooks/queries";
import { PageContainer } from "@/components/layout/page";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EntityTypeBadge, ProfileTierBadge } from "@/components/status";
import { Skeleton } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/error-state";
import { RELATIONSHIP_TYPE_META } from "@/components/status";
import { formatPercent, shortId } from "@/lib/utils";
import { useDocumentTitle } from "@/hooks/ui";
import { Badge } from "@/components/ui/badge";
import type { RelationshipType } from "@/types/domain";

export default function EntityDetailPage() {
  const { caseId = "", entityId = "" } = useParams();
  useDocumentTitle("Entity");
  const entity = useEntity(caseId, entityId);
  const ego = useEntityEgo(caseId, entityId);
  const dna = useNetworkDna(caseId);

  const profile = (dna.data ?? []).find((p) => p.entity_id === entityId);

  if (entity.isError) {
    return (
      <PageContainer className="py-8">
        <Card><ErrorState error={entity.error} onRetry={() => void entity.refetch()} /></Card>
      </PageContainer>
    );
  }

  const record = entity.data;

  return (
    <PageContainer>
      <Link to={`/app/cases/${caseId}/entities`} className="inline-flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-foreground">
        <ArrowLeft className="size-3.5" /> Back to entities
      </Link>

      {entity.isLoading ? (
        <div className="mt-4 space-y-3">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-24 w-full max-w-2xl" />
        </div>
      ) : record ? (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold tracking-tight text-foreground">{record.display_value}</h1>
          <EntityTypeBadge value={record.entity_type} />
          {profile ? <ProfileTierBadge value={profile.tier} /> : null}
        </div>
      ) : null}

      <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="space-y-5">
          <Card>
            <CardHeader><CardTitle>Identity record</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-dim">Display value</p>
                  <p className="mt-0.5 text-foreground">{record?.display_value}</p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-dim">Canonical value</p>
                  <p className="mt-0.5 font-mono text-[13px] text-foreground">{record?.canonical_value}</p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-dim">Entity id</p>
                  <p className="mt-0.5 font-mono text-[11px] text-dim">{shortId(record?.id ?? "")}</p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-dim">Resolution confidence</p>
                  <p className="tabular mt-0.5 text-foreground">
                    {record?.confidence != null ? formatPercent(record.confidence) : "—"}
                  </p>
                </div>
              </div>

              {record?.context ? (
                <p className="rounded-md border border-border bg-surface-2 px-3 py-2 text-xs leading-relaxed text-muted">
                  {typeof record.context === "string" ? record.context : JSON.stringify(record.context)}
                </p>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Aliases</CardTitle></CardHeader>
            <CardContent>
              {(record?.aliases ?? []).length === 0 ? (
                <p className="py-4 text-center text-xs text-dim">No aliases recorded.</p>
              ) : (
                <div className="space-y-1.5">
                  {(record?.aliases ?? []).map((alias, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <span className="font-mono text-[13px] text-foreground">{alias.alias_value}</span>
                      <Badge>{alias.alias_type}</Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Position in network</CardTitle></CardHeader>
            <CardContent>
              {profile ? (
                <div className="space-y-3 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] uppercase tracking-wider text-dim">Tier</span>
                    <ProfileTierBadge value={profile.tier} />
                    <span className="tabular ml-auto text-xs text-muted">
                      network score {Math.round(profile.overall_score * 100)}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed text-dim">
                    {profile.explanation ?? "Profiled by structural role in the network."}
                  </p>
                  <div className="grid grid-cols-3 gap-2">
                    {Object.values(profile.features).slice(0, 6).map((feature) => (
                      <div key={feature.name} className="rounded-md border border-border bg-surface-2 px-2 py-1.5">
                        <p className="truncate text-[10px] uppercase tracking-wider text-dim">{feature.name}</p>
                        <p className="tabular text-sm text-foreground">{Math.round(feature.normalized * 100)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="py-4 text-center text-xs text-dim">
                  No structural profile yet — run analytics on this case.
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Connected entities</CardTitle>
            <Link to={`/app/cases/${caseId}/graph`} className="text-xs text-accent hover:text-accent-strong">
              Open in graph
            </Link>
          </CardHeader>
          <CardContent>
            {ego.isLoading ? (
              <Skeleton className="h-40" />
            ) : (ego.data?.nodes ?? []).length <= 1 ? (
              <p className="py-6 text-center text-xs text-dim">No connections recorded.</p>
            ) : (
              <div className="space-y-2">
                {(ego.data?.edges ?? []).map((edge) => {
                  const otherId = edge.source === entityId ? edge.target : edge.source;
                  const other = (ego.data?.nodes ?? []).find((n) => n.id === otherId);
                  return (
                    <div key={edge.id} className="flex items-center gap-2.5">
                      <span className="grid size-7 shrink-0 place-items-center rounded-md border border-info/25 bg-info/10 text-info">
                        <Link2 className="size-3.5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <Link
                          to={`/app/cases/${caseId}/entities/${otherId}`}
                          className="block truncate text-sm text-foreground hover:text-accent"
                        >
                          {other?.display_value ?? shortId(otherId)}
                        </Link>
                        <p className="text-[11px] capitalize text-dim">
                          {RELATIONSHIP_TYPE_META[edge.relationship_type as RelationshipType]?.label ?? edge.relationship_type}
                          {edge.confidence != null ? ` · ${formatPercent(edge.confidence, 0)}` : ""}
                        </p>
                      </div>
                      <FileText className="size-3.5 shrink-0 text-dim" />
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="mt-5">
        <Card>
          <CardContent className="flex items-center gap-3 bg-surface px-4 py-3">
            <Network className="size-4 shrink-0 text-dim" />
            <p className="text-xs leading-relaxed text-dim">
              Relationships shown here are extracted from ingested source records. Candidate or hypothesized
              links that are not yet recorded do not appear here — they live in{" "}
              <Link to={`/app/cases/${caseId}/hypotheses`} className="text-accent hover:text-accent-strong">
                hypotheses
              </Link>
              .
            </p>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}